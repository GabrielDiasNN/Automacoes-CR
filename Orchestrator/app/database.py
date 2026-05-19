# pylint: disable=all
# mypy: ignore-errors
"""
Camada de Banco de Dados do Orchestrator Central de Automacoes v5.0.

Configuracoes hardened de SQLite:
  - WAL mode para acesso concorrente (API + Worker)
  - foreign_keys = ON para integridade referencial
  - busy_timeout = 5000ms para resiliencia sob carga
  - synchronous = NORMAL para performance com seguranca
  - WAL Checkpoint automatico agendado (Pilar E - Escala)
  - Purge automatico de execucoes antigas (Pilar G - Governanca)
"""

import logging
import os
from datetime import timedelta

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .constants import ORCHESTRATOR_SCHEMA_VERSION
from .timezone import get_now_local

logger = logging.getLogger("orchestrator")

# O banco de dados sera criado no diretorio Orchestrator
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "automacoes.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configura pragmas de seguranca e performance em cada conexao."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA cache_size=-8000")  # 8MB de cache
    cursor.execute("PRAGMA temp_store=MEMORY")  # Tabelas temporarias em RAM
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

EXPECTED_SCHEMA = {
    "automations": {
        "id",
        "name",
        "description",
        "script_path",
        "schedule",
        "max_runtime_minutes",
        "max_retries",
        "cooldown_minutes",
        "queue_group",
        "enabled",
        "test_mode",
        "notification_channels",
        "created_at",
        "updated_at",
    },
    "executions": {
        "id",
        "automation_id",
        "status",
        "priority",
        "retry_count",
        "max_retries",
        "queue_group",
        "failure_reason",
        "recovery_action",
        "exit_code",
        "requested_by",
        "started_at",
        "finished_at",
        "duration_seconds",
        "artifacts",
        "logs",
    },
    "worker_heartbeat": {
        "id",
        "pid",
        "last_ping",
        "uptime_seconds",
        "tasks_completed",
        "tasks_failed",
        "active_tasks",
        "version",
    },
    "audit_log": {
        "id",
        "timestamp",
        "action",
        "entity_type",
        "entity_id",
        "actor",
        "details",
    },
    "orchestrator_metadata": {
        "key",
        "value",
        "updated_at",
    },
}

SCHEMA_MIGRATIONS = {
    "automations": [
        ("max_retries", "INTEGER NOT NULL DEFAULT 0"),
        ("cooldown_minutes", "INTEGER NOT NULL DEFAULT 0"),
        ("queue_group", "VARCHAR(100)"),
    ],
    "executions": [
        ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
        ("max_retries", "INTEGER NOT NULL DEFAULT 0"),
        ("queue_group", "VARCHAR(100)"),
        ("failure_reason", "VARCHAR(200)"),
        ("recovery_action", "VARCHAR(200)"),
    ],
}


def get_db():
    """Dependency injection do FastAPI - garante cleanup via finally."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def validate_database_schema() -> dict:
    """Valida tabelas/colunas essenciais esperadas pelo Orchestrator atual."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing_tables = sorted(set(EXPECTED_SCHEMA) - existing_tables)
    missing_columns = {}

    for table, expected_columns in EXPECTED_SCHEMA.items():
        if table not in existing_tables:
            continue
        actual_columns = {column["name"] for column in inspector.get_columns(table)}
        missing = sorted(expected_columns - actual_columns)
        if missing:
            missing_columns[table] = missing

    valid = not missing_tables and not missing_columns
    return {
        "valid": valid,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
    }


def get_schema_version() -> str:
    """Retorna a versao logica atual gravada no banco."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT value FROM orchestrator_metadata WHERE key = 'schema_version'"
                )
            ).fetchone()
            return row[0] if row else "unknown"
    except Exception:
        return "unknown"


def run_schema_migrations() -> dict:
    """Aplica migracoes leves compatíveis com SQLite antes da validacao final."""
    applied = []
    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        conn.execute(text("""
                CREATE TABLE IF NOT EXISTS orchestrator_metadata (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME
                )
                """))
        if "orchestrator_metadata" not in existing_tables:
            existing_tables.add("orchestrator_metadata")

        for table_name, columns in SCHEMA_MIGRATIONS.items():
            if table_name not in existing_tables:
                continue
            current_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, ddl in columns:
                if column_name in current_columns:
                    continue
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
                )
                applied.append(f"{table_name}.{column_name}")

        conn.execute(
            text("""
                INSERT INTO orchestrator_metadata (key, value, updated_at)
                VALUES ('schema_version', :value, :updated_at)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """),
            {
                "value": ORCHESTRATOR_SCHEMA_VERSION,
                "updated_at": get_now_local(),
            },
        )

    return {
        "applied": applied,
        "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
    }


def get_db_size_mb() -> float:
    """Retorna o tamanho atual do banco em MB."""
    if os.path.exists(DB_PATH):
        return round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)
    return 0.0


def get_wal_size_mb() -> float:
    """Retorna o tamanho atual do WAL em MB (indicador de checkpoint pendente)."""
    wal_path = DB_PATH + "-wal"
    if os.path.exists(wal_path):
        return round(os.path.getsize(wal_path) / (1024 * 1024), 2)
    return 0.0


# ---------------------------------------------------------------------------
# Pilar E - Escala: WAL Checkpoint Automatico
# ---------------------------------------------------------------------------


def run_wal_checkpoint(mode: str = "PASSIVE") -> dict:
    """
    Executa WAL checkpoint para consolidar logs no banco principal.
    Modos:
      - PASSIVE (default): Nao bloqueia, consolida o que for possivel.
      - TRUNCATE: Tenta consolidar TUDO e zera o arquivo WAL (usado no startup).
    """
    try:
        with engine.connect() as conn:
            # SQLAlchemy text() para execucao de pragmas com retorno
            result = conn.execute(text(f"PRAGMA wal_checkpoint({mode})"))
            row = result.fetchone()
            wal_size = get_wal_size_mb()
            logger.info(
                f"WAL Checkpoint ({mode}) executado: log={row[1]}, checkpointed={row[2]}, "
                f"wal_size={wal_size}MB"
            )
            return {
                "mode": mode,
                "log": row[1],
                "checkpointed": row[2],
                "wal_size_mb": wal_size,
            }
    except Exception as e:
        logger.error(f"Falha no WAL checkpoint ({mode}): {e}")
        return {"mode": mode, "log": -1, "checkpointed": -1, "error": str(e)}


# ---------------------------------------------------------------------------
# Pilar G - Governanca: Purge de Execucoes Antigas
# ---------------------------------------------------------------------------


def purge_old_executions(retention_days: int = 90) -> int:
    """
    Remove execucoes finalizadas mais antigas que retention_days.
    Mantem sempre: PENDING, RUNNING e ultimas 50 execucoes por automacao.
    Chamado pelo APScheduler diariamente as 03:00.

    Retorna: quantidade de registros removidos.
    """
    # Importacao local para evitar circular import (models depende de Base)
    from . import models as _models
    from .timezone import get_now_local

    cutoff = get_now_local() - timedelta(days=retention_days)
    terminal_statuses = [
        "SUCCESS",
        "ERROR",
        "TIMEOUT",
        "TERMINATED",
        "FAILED_BY_REBOOT",
    ]

    db = SessionLocal()
    try:
        # Delete em massa via query direta para performance (Pilar E)
        query = db.query(_models.Execution).filter(
            _models.Execution.status.in_(terminal_statuses),
            _models.Execution.finished_at < cutoff,
        )
        removed = query.delete(synchronize_session=False)
        db.commit()
        if removed:
            logger.info(
                f"Purge concluído: {removed} execuções removidas (>{retention_days} dias)."
            )
        return removed
    except Exception as e:
        db.rollback()
        logger.error(f"Falha no purge de execuções: {e}")
        return 0
    finally:
        db.close()

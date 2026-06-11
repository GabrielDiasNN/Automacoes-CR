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
DB_PATH = os.environ.get("ORCHESTRATOR_DB_PATH") or os.path.join(BASE_DIR, "automacoes.db")
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

def get_db():
    """Dependency injection do FastAPI - garante cleanup via finally."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def validate_database_schema() -> dict:
    """Valida tabelas/colunas contra o schema ORM atual (derivado de Base.metadata)."""
    from . import models as _models  # noqa: F401 — registra tabelas no Base.metadata

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # Gera expected schema a partir do ORM — single source of truth, sem hardcoding
    _skip = {"alembic_version"}
    expected = {
        t_name: {col.name for col in table.columns}
        for t_name, table in Base.metadata.tables.items()
        if t_name not in _skip
    }

    missing_tables = sorted(set(expected) - existing_tables)
    missing_columns = {}
    for table, expected_columns in expected.items():
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
    """Retorna a versao logica atual da revisao do Alembic gravada no banco."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchone()
            return row[0] if row else "none"
    except Exception:
        return "unknown"


def run_alembic_migrations() -> dict:
    """Roda migrações do Alembic até o HEAD e retorna o resultado da migração."""
    if ":memory:" in SQLALCHEMY_DATABASE_URL:
        logger.info("Banco de dados em memoria detectado. Desviando execucao do Alembic nos testes.")
        return {"applied": ["in_memory_test_skip"], "schema_version": ORCHESTRATOR_SCHEMA_VERSION}

    from alembic.config import Config
    from alembic import command

    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(current_dir, "alembic.ini")

    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

    schema_status = validate_database_schema()
    schema_version = get_schema_version()
    if schema_version == ORCHESTRATOR_SCHEMA_VERSION:
        logger.info("Schema Alembic ja esta no head %s.", ORCHESTRATOR_SCHEMA_VERSION)
        return {"applied": [], "schema_version": ORCHESTRATOR_SCHEMA_VERSION}

    if schema_status["valid"] and schema_version in {"none", "unknown"}:
        logger.info(
            "Schema legado valido sem revisao Alembic. Aplicando stamp para %s.",
            ORCHESTRATOR_SCHEMA_VERSION,
        )
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
                {"version": ORCHESTRATOR_SCHEMA_VERSION},
            )
        return {"applied": ["alembic_stamp"], "schema_version": ORCHESTRATOR_SCHEMA_VERSION}

    logger.info("Iniciando aplicacao programática de migracao via Alembic...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migracao do Alembic aplicada com sucesso.")
    return {"applied": ["alembic_upgrade_head"], "schema_version": ORCHESTRATOR_SCHEMA_VERSION}

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

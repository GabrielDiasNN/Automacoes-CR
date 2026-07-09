"""
Camada de Banco de Dados do Orchestrator Central de Automacoes v1.0.0.

Configuracoes hardened de SQLite:
  - WAL mode para acesso concorrente (API + Worker)
  - foreign_keys = ON para integridade referencial
  - busy_timeout = 5000ms para resiliencia sob carga
  - synchronous = NORMAL para performance com seguranca
  - WAL Checkpoint automatico agendado (Pilar E - Escala)
  - Purge automatico de execucoes antigas (Pilar G - Governanca)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from sqlalchemy import create_engine, event, func, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .constants import ORCHESTRATOR_SCHEMA_VERSION
from .timezone import get_now_local

logger = logging.getLogger("orchestrator")

# O banco de dados sera criado no diretorio Orchestrator
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("ORCHESTRATOR_DB_PATH") or os.path.join(
    BASE_DIR, "automacoes.db"
)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(
    dbapi_connection: Any, connection_record: Any  # pylint: disable=unused-argument
) -> None:
    """Configura pragmas de seguranca e performance em cada conexao.

    connection_record e exigido pela assinatura do evento SQLAlchemy "connect".
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA cache_size=-8000")  # 8MB de cache
    cursor.execute("PRAGMA temp_store=MEMORY")  # Tabelas temporarias em RAM
    cursor.close()


SessionLocal = sessionmaker(  # pylint: disable=invalid-name
    autocommit=False, autoflush=False, bind=engine
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency injection do FastAPI - garante cleanup via finally."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope(session_factory: Any = None) -> Generator[Session, None, None]:
    """Context manager para uso fora do FastAPI (worker, scheduler, jobs).

    Garante ``rollback`` em caso de excecao e ``close`` sempre, eliminando o
    risco de conexoes orfas do padrao manual ``db = SessionLocal(); try/finally``.
    Nao faz commit automatico: o chamador decide quando persistir, preservando a
    semantica de sessoes somente-leitura e dos commits explicitos existentes.
    """
    factory = session_factory or SessionLocal
    db = factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def validate_database_schema() -> dict[str, Any]:
    """Valida tabelas/colunas contra o schema ORM atual (derivado de Base.metadata)."""
    # Importacao local para evitar circular import (models depende de Base)
    from . import (  # noqa: F401, I001  # pylint: disable=import-outside-toplevel,cyclic-import
        models as _models,
    )

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
    missing_columns: dict[str, list[str]] = {}
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
            return str(row[0]) if row else "none"
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


def run_alembic_migrations() -> dict[str, Any]:
    """Roda migrações do Alembic até o HEAD e retorna o resultado da migração."""
    if ":memory:" in SQLALCHEMY_DATABASE_URL:
        logger.info(
            "Banco de dados em memoria detectado. Desviando execucao do Alembic nos testes."
        )
        return {
            "applied": ["in_memory_test_skip"],
            "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
        }

    # Importacao local: alembic e pesado e so e necessario neste caminho de codigo
    from alembic import command  # pylint: disable=import-outside-toplevel
    from alembic.config import Config  # pylint: disable=import-outside-toplevel

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
        with engine.begin() as conn:  # transacao atomica (HF-5/B3)
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
                {"version": ORCHESTRATOR_SCHEMA_VERSION},
            )
        # Verificacao pos-stamp: garante que o registro foi gravado corretamente
        actual = get_schema_version()
        if actual != ORCHESTRATOR_SCHEMA_VERSION:
            raise RuntimeError(
                f"Stamp Alembic falhou: esperado {ORCHESTRATOR_SCHEMA_VERSION}, obtido {actual}"
            )
        return {
            "applied": ["alembic_stamp"],
            "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
        }

    logger.info("Iniciando aplicacao programática de migracao via Alembic...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migracao do Alembic aplicada com sucesso.")
    return {
        "applied": ["alembic_upgrade_head"],
        "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
    }


def purge_old_snapshots(retention_days: int = 30) -> int:
    """Remove SystemHealthSnapshots mais antigos que retention_days (B5/2.4).

    Padrão 30 dias = ~8.640 registros retidos (snapshot a cada 5min).
    """
    # Importacao local para evitar circular import (models depende de Base)
    from . import models as _models  # pylint: disable=C0415,cyclic-import

    cutoff = get_now_local() - timedelta(days=retention_days)
    try:
        with session_scope() as db:
            removed = (
                db.query(_models.SystemHealthSnapshot)
                .filter(_models.SystemHealthSnapshot.timestamp < cutoff)
                .delete(synchronize_session=False)
            )
            db.commit()
        if removed:
            logger.info("Purge de snapshots: %d registros removidos.", removed)
        return int(removed)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Falha no purge de snapshots: %s", e)
        return 0


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


def run_wal_checkpoint(mode: str = "PASSIVE") -> dict[str, Any]:
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
            log_val: Any = row[1] if row is not None else -1
            checkpointed_val: Any = row[2] if row is not None else -1
            logger.info(
                "WAL Checkpoint (%s) executado: log=%s, checkpointed=%s, wal_size=%sMB",
                mode,
                log_val,
                checkpointed_val,
                wal_size,
            )
            return {
                "mode": mode,
                "log": log_val,
                "checkpointed": checkpointed_val,
                "wal_size_mb": wal_size,
            }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Falha no WAL checkpoint (%s): %s", mode, e)
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
    from . import models as _models  # pylint: disable=C0415,cyclic-import

    cutoff = get_now_local() - timedelta(days=retention_days)
    terminal_statuses = [
        "SUCCESS",
        "ERROR",
        "TIMEOUT",
        "TERMINATED",
        "FAILED_BY_REBOOT",
    ]

    try:
        with session_scope() as db:
            # Últimas 50 execuções de cada automação são preservadas mesmo
            # além da retenção (contrato operacional do purge).
            rank = (
                func.row_number()
                .over(
                    partition_by=_models.Execution.automation_id,
                    order_by=_models.Execution.started_at.desc(),
                )
                .label("rank")
            )
            ranked = db.query(_models.Execution.id.label("exec_id"), rank).subquery()
            keep_ids = db.query(ranked.c.exec_id).filter(ranked.c.rank <= 50)

            # Delete em massa via query direta para performance (Pilar E)
            query = db.query(_models.Execution).filter(
                _models.Execution.status.in_(terminal_statuses),
                _models.Execution.finished_at < cutoff,
                ~_models.Execution.id.in_(keep_ids),
            )
            removed = query.delete(synchronize_session=False)
            db.commit()
        if removed:
            logger.info(
                "Purge concluído: %d execuções removidas (>%d dias).",
                removed,
                retention_days,
            )
        return int(removed)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Falha no purge de execuções: %s", e)
        return 0

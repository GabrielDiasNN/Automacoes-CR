"""
Camada de Banco de Dados do Orchestrator Hub Soberano v5.0.

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
from datetime import datetime, timedelta

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

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

def run_wal_checkpoint() -> dict:
    """
    Executa WAL checkpoint passivo - consolida o WAL no banco principal.
    Chamado pelo APScheduler a cada 30 minutos.

    Retorna: {"mode": str, "log": int, "checkpointed": int}
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
            row = result.fetchone()
            wal_size = get_wal_size_mb()
            logger.info(
                f"WAL Checkpoint executado: log={row[1]}, checkpointed={row[2]}, "
                f"wal_size={wal_size}MB"
            )
            return {"mode": "PASSIVE", "log": row[1], "checkpointed": row[2], "wal_size_mb": wal_size}
    except Exception as e:
        logger.error(f"Falha no WAL checkpoint: {e}")
        return {"mode": "PASSIVE", "log": -1, "checkpointed": -1, "error": str(e)}


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

    cutoff = datetime.now() - timedelta(days=retention_days)
    terminal_statuses = ["SUCCESS", "ERROR", "TIMEOUT", "TERMINATED", "FAILED_BY_REBOOT"]

    db = SessionLocal()
    removed = 0
    try:
        old_execs = (
            db.query(_models.Execution)
            .filter(
                _models.Execution.status.in_(terminal_statuses),
                _models.Execution.finished_at < cutoff,
            )
            .all()
        )
        for ex in old_execs:
            db.delete(ex)
            removed += 1

        db.commit()
        if removed:
            logger.info(f"Purge concluido: {removed} execucoes removidas (>{retention_days} dias).")
        return removed
    except Exception as e:
        db.rollback()
        logger.error(f"Falha no purge de execucoes: {e}")
        return 0
    finally:
        db.close()


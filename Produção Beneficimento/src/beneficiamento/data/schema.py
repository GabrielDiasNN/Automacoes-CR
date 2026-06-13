"""Definicao declarativa e bootstrap do historico tipado do Beneficiamento."""
# pylint: disable=line-too-long

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..settings import DOMAIN_ROOT

HISTORICO_SCHEMA_VERSION = 2
TABLE_NAME = "fato_producao_historica"

# Colunas tipadas persistidas, na ordem de INSERT. A ultima (DADOS_COMPLETOS)
# guarda o payload original serializado e e usada apenas para auditoria/raw.
# Tuplas: (coluna, tipo SQL). PK composta: (NUMERO_OB, SEQ).
COLUMNS: tuple[tuple[str, str], ...] = (
    ("NUMERO_OB", "TEXT NOT NULL"),
    ("SEQ", "INTEGER NOT NULL"),
    ("DATA_FIM", "TEXT"),
    ("NUMERO_MAQUINA", "INTEGER"),
    ("NOME_MAQUINA", "TEXT"),
    ("CD_DS_FASE", "TEXT"),
    ("REDUZ", "TEXT"),
    ("CODIGO_ALTERNATIVO", "TEXT"),
    ("DESCR_ITEM", "TEXT"),
    ("ARTIGO", "TEXT"),
    ("DESCR_ARTIGO", "TEXT"),
    ("COR", "TEXT"),
    ("DESCR_COR", "TEXT"),
    ("QT_KG", "REAL"),
    ("QT_MT", "REAL"),
    ("ANO_MES", "TEXT"),
    ("ANO_SEM", "INTEGER"),
    ("OPERADOR_FINAL", "TEXT"),
    ("REPROCESSO", "INTEGER"),
    ("MIN_REAL", "REAL"),
    ("MIN_PREV", "REAL"),
    ("DESVIO_MIN", "REAL"),
    ("TURNO_ID", "TEXT"),
    ("TURNO_LABEL", "TEXT"),
    ("MAQUINA_KEY", "TEXT"),
    ("FASE_KEY", "TEXT"),
    ("CODIGO_KEY", "TEXT"),
    ("DADOS_COMPLETOS", "TEXT"),
)

# Colunas persistidas exceto a PK e o blob de auditoria -- usadas para projecao
# tipada em buscar/detail sem reparsear JSON.
COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in COLUMNS)

INDEXES: tuple[str, ...] = (
    f"CREATE INDEX IF NOT EXISTS idx_producao_numero_ob ON {TABLE_NAME}(NUMERO_OB);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_alternativo ON {TABLE_NAME}(CODIGO_ALTERNATIVO);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_reduz ON {TABLE_NAME}(REDUZ);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_data ON {TABLE_NAME}(DATA_FIM);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_anosem ON {TABLE_NAME}(ANO_SEM);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_anomes ON {TABLE_NAME}(ANO_MES);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_maquina ON {TABLE_NAME}(NUMERO_MAQUINA);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_turno_label ON {TABLE_NAME}(TURNO_LABEL);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_maquina_key ON {TABLE_NAME}(MAQUINA_KEY);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_fase_key ON {TABLE_NAME}(FASE_KEY);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_codigo_key ON {TABLE_NAME}(CODIGO_KEY);",
    f"CREATE INDEX IF NOT EXISTS idx_producao_data_maquina_fase ON {TABLE_NAME}(DATA_FIM, MAQUINA_KEY, FASE_KEY);",
)


def _create_table_sql() -> str:
    body = ",\n            ".join(f"{name} {sqltype}" for name, sqltype in COLUMNS)
    return (
        f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} (\n            {body},\n"
        "            PRIMARY KEY (NUMERO_OB, SEQ)\n        );"
    )


def resolve_db_path(override: Path | str | None = None) -> Path:
    """Resolve o caminho do banco; default em ``snapshots/beneficiamento_historico.db``."""
    if override:
        return Path(override).expanduser().resolve()
    folder = DOMAIN_ROOT / "snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "beneficiamento_historico.db"


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Pragmas de resiliencia/performance de I/O (WAL + synchronous NORMAL)."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")


def init_db(db_path: Path | str | None = None) -> Path:
    """Garante o schema tipado e os indices; idempotente e versionado."""
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        apply_pragmas(conn)
        current_version = int(conn.execute("PRAGMA user_version;").fetchone()[0] or 0)
        table_exists = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?;",
                (TABLE_NAME,),
            ).fetchone()
            is not None
        )
        if table_exists and current_version >= HISTORICO_SCHEMA_VERSION:
            for index_sql in INDEXES:
                conn.execute(index_sql)
            conn.commit()
            return path

        # O schema v2 troca o blob como fonte de consulta por colunas tipadas.
        # Bases antigas devem ser recarregadas pelo runner, evitando backfill
        # parcial e mantendo a migração determinística.
        if table_exists and current_version < HISTORICO_SCHEMA_VERSION:
            conn.execute(f"DROP TABLE {TABLE_NAME};")

        conn.execute(_create_table_sql())
        for index_sql in INDEXES:
            conn.execute(index_sql)
        conn.execute(f"PRAGMA user_version = {HISTORICO_SCHEMA_VERSION};")
        conn.commit()

    return path

"""Constroi o catalogo local do schema Oracle SGTPRD em SQLite.

Gera `docs/oracle-schema/schema.db` a partir do dicionario de dados Oracle
(ALL_OBJECTS, ALL_TAB_COLS, ALL_CONSTRAINTS, ALL_INDEXES, ALL_VIEWS, ...).
O objetivo e permitir que `Tools/oracle_catalog.py` responda perguntas de
schema (qual tabela, qual coluna, qual join) sem gastar tokens de sessao e
sem ir ao Oracle a cada consulta.

Usa `lib/python/oracle_extract.fetch_all()` — uma conexao nova por query,
igual aos 6 extratores de dominio — e nao uma conexao unica reusada para
todo o build. Medido nesta rede: a sessao Oracle e derrubada (ORA-00028 /
ORA-03113) apos ~3-6s de conexao continua, independente de atividade —
provavelmente um proxy/DAM corporativo na frente do listener. Cada query
deste script roda em 0.3-3s isoladamente, dentro da janela; encadear varias
na mesma conexao (testado e revertido) estoura o limite no meio do build.

Uso:
    .venv\\Scripts\\python Tools\\build_oracle_catalog.py
    .venv\\Scripts\\python Tools\\build_oracle_catalog.py --skip-view-source
    .venv\\Scripts\\python Tools\\build_oracle_catalog.py --owner SGTPRD --output docs\\oracle-schema\\schema.db

Requer .env com ORACLE_READONLY_USER/PASSWORD/CLIENT_LIB_DIR (mesmo
contrato dos 6 extratores de dominio) e Oracle Instant Client (Thick Mode).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib" / "python"))

try:
    from dotenv import load_dotenv
    from oracle_extract import (
        OracleCredentials,
        fetch_all,
        init_thick_mode,
        resolve_oracle_credentials,
    )
    from oracle_retry import make_oracle_retry
except ImportError as exc:
    print(f"[ERRO] Nao foi possivel importar dependencias: {exc}")
    print(
        "       Rode com o venv do projeto: .venv\\Scripts\\python Tools\\build_oracle_catalog.py"
    )
    sys.exit(1)

DEFAULT_OWNER = "SGTPRD"
DEFAULT_OUTPUT = ROOT / "docs" / "oracle-schema" / "schema.db"
EXEC_ID = f"oracle-catalog-build-{time.strftime('%Y%m%d-%H%M%S')}"


def _log(msg: str, level: str = "INFO", exec_id: str = EXEC_ID) -> None:
    print(f"[{level}] ({exec_id}) {msg}")


# Mesmo padrao dos 6 extratores de dominio (ex.: `OBs Paradas Fase/extract_obs.py`):
# a rede ate o Oracle e instavel o bastante (ORA-00028/ORA-03113 mesmo em queries
# de poucos segundos) para exigir circuit breaker + retry em toda chamada.
_oracle_retry = make_oracle_retry()


@_oracle_retry
def _fetch_all_retry(
    creds: OracleCredentials, sql: str, params: dict[str, Any], batch_size: int
) -> tuple[list[str], list[Any]]:
    return fetch_all(creds, sql, EXEC_ID, _log, params=params, batch_size=batch_size)


def _fetch(
    creds: OracleCredentials, sql: str, params: dict[str, Any], batch_size: int = 2000
) -> list[tuple[Any, ...]]:
    """Abre uma conexao dedicada (com retry), executa `sql` e fecha."""
    _, rows = _fetch_all_retry(creds, sql, params, batch_size)
    return [tuple(row) for row in rows]


# ─────────────────────────── Extracao: objetos + comentarios ─────────────────


def _extract_objects(creds: OracleCredentials, owner: str) -> list[tuple[Any, ...]]:
    objects = _fetch(
        creds,
        """
        SELECT o.object_name, o.object_type, o.status,
               t.num_rows, t.last_analyzed, c.comments
        FROM ALL_OBJECTS o
        LEFT JOIN ALL_TABLES t ON t.owner = o.owner AND t.table_name = o.object_name
        LEFT JOIN ALL_TAB_COMMENTS c ON c.owner = o.owner AND c.table_name = o.object_name
        WHERE o.owner = :owner
          AND o.object_type IN ('TABLE', 'VIEW', 'FUNCTION', 'PROCEDURE', 'PACKAGE', 'TRIGGER', 'SEQUENCE')
        """,
        {"owner": owner},
    )
    _log(f"Objetos: {len(objects)}")
    return objects


# ─────────────────────────── Extracao: colunas ────────────────────────────────


def _extract_columns(creds: OracleCredentials, owner: str) -> list[tuple[Any, ...]]:
    columns = _fetch(
        creds,
        """
        SELECT col.table_name, col.column_name, col.column_id, col.data_type,
               col.data_length, col.data_precision, col.data_scale, col.nullable,
               col.data_default, col.virtual_column, cc.comments
        FROM ALL_TAB_COLS col
        LEFT JOIN ALL_COL_COMMENTS cc
          ON cc.owner = col.owner AND cc.table_name = col.table_name AND cc.column_name = col.column_name
        WHERE col.owner = :owner AND col.hidden_column = 'NO'
        ORDER BY col.table_name, col.column_id
        """,
        {"owner": owner},
        batch_size=3000,
    )
    _log(f"Colunas: {len(columns)}")
    return columns


# ─────────────────────────── Extracao: constraints (PK/UNIQUE/FK) ────────────


def _extract_constraints(creds: OracleCredentials, owner: str) -> list[tuple[Any, ...]]:
    constraints = _fetch(
        creds,
        """
        SELECT c.table_name, c.constraint_name, c.constraint_type, c.status,
               r.table_name AS ref_table, c.r_constraint_name
        FROM ALL_CONSTRAINTS c
        LEFT JOIN ALL_CONSTRAINTS r ON r.owner = c.r_owner AND r.constraint_name = c.r_constraint_name
        WHERE c.owner = :owner AND c.constraint_type IN ('P', 'U', 'R')
        """,
        {"owner": owner},
    )
    _log(f"Constraints (P/U/R): {len(constraints)}")
    return constraints


def _extract_constraint_columns(
    creds: OracleCredentials, owner: str
) -> list[tuple[Any, ...]]:
    cons_cols = _fetch(
        creds,
        """
        SELECT cc.constraint_name, cc.table_name, cc.column_name, cc.position
        FROM ALL_CONS_COLUMNS cc
        JOIN ALL_CONSTRAINTS c ON c.owner = cc.owner AND c.constraint_name = cc.constraint_name
        WHERE cc.owner = :owner AND c.constraint_type IN ('P', 'U', 'R')
        """,
        {"owner": owner},
    )
    _log(f"Colunas de constraint: {len(cons_cols)}")
    return cons_cols


# ─────────────────────────── Extracao: indices ───────────────────────────────


def _extract_indexes(
    creds: OracleCredentials, owner: str
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    indexes = _fetch(
        creds,
        "SELECT table_name, index_name, uniqueness FROM ALL_INDEXES WHERE owner = :owner",
        {"owner": owner},
    )
    index_cols = _fetch(
        creds,
        """
        SELECT ic.index_name, ic.table_name, ic.column_name, ic.column_position
        FROM ALL_IND_COLUMNS ic
        WHERE ic.index_owner = :owner
        """,
        {"owner": owner},
        batch_size=3000,
    )
    _log(f"Indices: {len(indexes)} ({len(index_cols)} colunas de indice)")
    return indexes, index_cols


# ─────────────────────────── Extracao: dependencias e fonte de views ────────


def _extract_view_deps(creds: OracleCredentials, owner: str) -> list[tuple[Any, ...]]:
    deps = _fetch(
        creds,
        """
        SELECT name, referenced_name, referenced_type
        FROM ALL_DEPENDENCIES
        WHERE owner = :owner AND referenced_owner = :owner AND type = 'VIEW'
        """,
        {"owner": owner},
    )
    _log(f"Dependencias de views: {len(deps)}")
    return deps


def _extract_view_source(creds: OracleCredentials, owner: str) -> list[tuple[Any, ...]]:
    # TEXT e coluna LONG: nao pode ser combinada com funcoes/agregacoes no
    # SQL (ORA-00932), mas o SELECT direto funciona normalmente.
    sources = _fetch(
        creds,
        "SELECT view_name, text FROM ALL_VIEWS WHERE owner = :owner ORDER BY view_name",
        {"owner": owner},
        batch_size=200,
    )
    _log(f"Fonte de views: {len(sources)}")
    return sources


# ─────────────────────────── Escrita no SQLite ───────────────────────────────

_SCHEMA_DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE objects (
    object_name TEXT PRIMARY KEY,
    object_type TEXT NOT NULL,
    status TEXT,
    num_rows INTEGER,
    last_analyzed TEXT,
    comment TEXT
);

CREATE TABLE columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    position INTEGER,
    data_type TEXT,
    data_length INTEGER,
    data_precision INTEGER,
    data_scale INTEGER,
    nullable INTEGER,
    data_default TEXT,
    is_virtual INTEGER,
    comment TEXT,
    PRIMARY KEY (table_name, column_name)
);
CREATE INDEX idx_columns_table ON columns(table_name);

CREATE TABLE constraints (
    table_name TEXT NOT NULL,
    constraint_name TEXT NOT NULL,
    constraint_type TEXT,
    status TEXT,
    ref_table TEXT,
    ref_constraint_name TEXT,
    PRIMARY KEY (table_name, constraint_name)
);
CREATE INDEX idx_constraints_ref_table ON constraints(ref_table);

CREATE TABLE constraint_columns (
    constraint_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    position INTEGER,
    PRIMARY KEY (constraint_name, position)
);
CREATE INDEX idx_cons_cols_table ON constraint_columns(table_name);

CREATE TABLE indexes (
    table_name TEXT NOT NULL,
    index_name TEXT NOT NULL,
    uniqueness TEXT,
    PRIMARY KEY (table_name, index_name)
);

CREATE TABLE index_columns (
    index_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    position INTEGER,
    PRIMARY KEY (index_name, position)
);
CREATE INDEX idx_index_cols_table ON index_columns(table_name);

CREATE TABLE view_deps (
    view_name TEXT NOT NULL,
    referenced_name TEXT NOT NULL,
    referenced_type TEXT,
    PRIMARY KEY (view_name, referenced_name, referenced_type)
);
CREATE INDEX idx_view_deps_ref ON view_deps(referenced_name);

CREATE TABLE view_source (
    view_name TEXT PRIMARY KEY,
    text TEXT
);

CREATE VIRTUAL TABLE search_idx USING fts5(object_name, column_name, comment);
"""


@dataclass(frozen=True)
class IndexData:
    """Indices e suas colunas — agrupados para nao inflar `CatalogData`."""

    indexes: list[tuple[Any, ...]]
    columns: list[tuple[Any, ...]]


@dataclass(frozen=True)
class CatalogData:
    """Agrupa os resultados de extracao para reduzir a assinatura de `_write_catalog`."""

    objects: list[tuple[Any, ...]]
    columns: list[tuple[Any, ...]]
    constraints: list[tuple[Any, ...]]
    constraint_columns: list[tuple[Any, ...]]
    index_data: IndexData
    view_deps: list[tuple[Any, ...]]
    view_source: list[tuple[Any, ...]] | None


def _insert_objects_and_columns(conn: sqlite3.Connection, data: CatalogData) -> None:
    conn.executemany(
        "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?)",
        [
            (o[0], o[1], o[2], o[3], str(o[4]) if o[4] else None, o[5])
            for o in data.objects
        ],
    )
    conn.executemany(
        "INSERT INTO columns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                c[0],
                c[1],
                c[2],
                c[3],
                c[4],
                c[5],
                c[6],
                1 if c[7] == "Y" else 0,
                c[8],
                1 if c[9] == "YES" else 0,
                c[10],
            )
            for c in data.columns
        ],
    )


def _insert_constraints_and_indexes(
    conn: sqlite3.Connection, data: CatalogData
) -> None:
    conn.executemany(
        "INSERT INTO constraints VALUES (?, ?, ?, ?, ?, ?)", data.constraints
    )
    conn.executemany(
        "INSERT INTO constraint_columns VALUES (?, ?, ?, ?)", data.constraint_columns
    )
    conn.executemany("INSERT INTO indexes VALUES (?, ?, ?)", data.index_data.indexes)
    conn.executemany(
        "INSERT INTO index_columns VALUES (?, ?, ?, ?)", data.index_data.columns
    )
    conn.executemany("INSERT INTO view_deps VALUES (?, ?, ?)", data.view_deps)
    if data.view_source is not None:
        conn.executemany("INSERT INTO view_source VALUES (?, ?)", data.view_source)


def _insert_search_index(conn: sqlite3.Connection, data: CatalogData) -> None:
    conn.executemany(
        "INSERT INTO search_idx (object_name, column_name, comment) VALUES (?, '', ?)",
        [(o[0], o[5]) for o in data.objects if o[5]],
    )
    conn.executemany(
        "INSERT INTO search_idx (object_name, column_name, comment) VALUES (?, ?, ?)",
        [(c[0], c[1], c[10]) for c in data.columns],
    )


def _insert_meta(conn: sqlite3.Connection, owner: str, data: CatalogData) -> None:
    conn.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [
            ("owner", owner),
            ("extracted_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
            ("total_objects", str(len(data.objects))),
            ("total_columns", str(len(data.columns))),
            ("total_constraints", str(len(data.constraints))),
            ("total_indexes", str(len(data.index_data.indexes))),
            ("view_source_included", "1" if data.view_source is not None else "0"),
        ],
    )


def _write_catalog(output_path: Path, owner: str, data: CatalogData) -> None:
    tmp_path = output_path.with_suffix(".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    conn = sqlite3.connect(tmp_path)
    try:
        conn.executescript(_SCHEMA_DDL)
        _insert_objects_and_columns(conn, data)
        _insert_constraints_and_indexes(conn, data)
        _insert_search_index(conn, data)
        _insert_meta(conn, owner, data)
        conn.commit()
    finally:
        conn.close()

    os.replace(tmp_path, output_path)


# ────────────────────────────── Main ──────────────────────────────────────────


def _resolve_creds(owner: str) -> OracleCredentials:
    creds = resolve_oracle_credentials(_log, EXEC_ID)
    if creds is None:
        _log("Credenciais Oracle ausentes ou invalidas. Verifique .env.", "ERROR")
        sys.exit(1)
    init_thick_mode(creds, _log, EXEC_ID)
    _log(f"Credenciais OK (DSN: {creds.dsn}, owner: {owner}). Uma conexao por query.")
    return creds


def _extract_all(
    creds: OracleCredentials, owner: str, skip_view_source: bool
) -> CatalogData:
    index_data = IndexData(*_extract_indexes(creds, owner))
    return CatalogData(
        objects=_extract_objects(creds, owner),
        columns=_extract_columns(creds, owner),
        constraints=_extract_constraints(creds, owner),
        constraint_columns=_extract_constraint_columns(creds, owner),
        index_data=index_data,
        view_deps=_extract_view_deps(creds, owner),
        view_source=None if skip_view_source else _extract_view_source(creds, owner),
    )


def build_catalog(output_path: Path, owner: str, skip_view_source: bool) -> None:
    start = time.time()
    creds = _resolve_creds(owner)
    data = _extract_all(creds, owner, skip_view_source)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_catalog(output_path, owner, data)
    _log(f"Catalogo escrito em {output_path} ({round(time.time() - start, 1)}s).")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Constroi o catalogo local do schema Oracle SGTPRD"
    )
    parser.add_argument(
        "--owner", default=DEFAULT_OWNER, help=f"Schema owner (padrao: {DEFAULT_OWNER})"
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT), help="Caminho do schema.db de saida"
    )
    parser.add_argument(
        "--skip-view-source",
        action="store_true",
        help="Nao extrai o texto das views (build mais rapido)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    build_catalog(Path(args.output), args.owner, args.skip_view_source)
    return 0


if __name__ == "__main__":
    sys.exit(main())

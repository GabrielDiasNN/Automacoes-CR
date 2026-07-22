"""Leitura do historico por colunas tipadas e indices (sem reparse de JSON).

O blob ``DADOS_COMPLETOS`` so e lido quando ``include_raw`` e solicitado; o
caminho padrao projeta colunas tipadas, aproveitando os indices do schema.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..core import parse_iso_date
from .schema import COLUMN_NAMES, TABLE_NAME, init_db

# Projecao tipada padrao: tudo menos o blob de auditoria.
_TYPED_COLUMNS: tuple[str, ...] = tuple(
    c for c in COLUMN_NAMES if c != "DADOS_COMPLETOS"
)
_TYPED_SELECT = ", ".join(_TYPED_COLUMNS)

# Teto defensivo do LIMIT. No SQLite, LIMIT negativo significa "sem limite":
# clampar aqui impede dump completo da tabela mesmo se um chamador passar
# limit<=0 ou um valor absurdo (defesa em profundidade do endpoint /historico).
_MAX_HISTORICO_LIMIT = 5000


def _row_to_record(row: sqlite3.Row, *, include_raw: bool) -> dict[str, Any]:
    record = {column: row[column] for column in _TYPED_COLUMNS}
    # Espelha os rotulos legados de turno para compatibilidade de exibicao.
    record["TURNO_PROD"] = record.get("TURNO_ID")
    record["TURNO_DESC"] = record.get("TURNO_LABEL") or "Indefinido"
    if include_raw:
        raw = row["DADOS_COMPLETOS"]
        if raw:
            try:
                record["DADOS_COMPLETOS"] = json.loads(raw)
            except json.JSONDecodeError:
                record["DADOS_COMPLETOS"] = None
    return record


def _apply_filters(filtros: dict[str, Any]) -> tuple[str, list[Any]]:
    sql = " WHERE 1=1"
    params: list[Any] = []

    ob = filtros.get("ob")
    if ob:
        sql += " AND NUMERO_OB LIKE ?"
        params.append(f"{str(ob).strip()}%")

    alternativo = filtros.get("alternativo")
    if alternativo:
        sql += " AND (CODIGO_ALTERNATIVO = ? OR REDUZ = ?)"
        params.extend([str(alternativo).strip(), str(alternativo).strip()])

    inicio = parse_iso_date(filtros.get("dt_inicio"))
    if inicio:
        sql += " AND DATA_FIM >= ?"
        params.append(f"{inicio.isoformat()}T00:00:00")

    fim = parse_iso_date(filtros.get("dt_fim"))
    if fim:
        sql += " AND DATA_FIM < ?"
        params.append(f"{(fim + timedelta(days=1)).isoformat()}T00:00:00")

    ano_sem = filtros.get("ano_sem")
    if ano_sem:
        try:
            params.append(int(ano_sem))
            sql += " AND ANO_SEM = ?"
        except (TypeError, ValueError):
            pass

    ano_mes = filtros.get("ano_mes")
    if ano_mes:
        sql += " AND ANO_MES = ?"
        params.append(str(ano_mes).strip())

    return sql, params


def buscar_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
    limit: int = 500,
    *,
    include_raw: bool = False,
) -> list[dict[str, Any]]:
    """Busca rapida por OB/produto/periodo lendo colunas tipadas indexadas."""
    limit = max(1, min(int(limit), _MAX_HISTORICO_LIMIT))
    path = init_db(db_path)
    where_sql, params = _apply_filters(filtros)
    sql = (
        f"SELECT {_TYPED_SELECT}"
        + (", DADOS_COMPLETOS" if include_raw else "")
        + f" FROM {TABLE_NAME}{where_sql}"
        " ORDER BY DATA_FIM DESC, NUMERO_OB DESC, SEQ ASC LIMIT ?"
    )
    params.append(limit)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        return [
            _row_to_record(row, include_raw=include_raw) for row in cursor.fetchall()
        ]


def explicar_busca_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
    limit: int = 500,
) -> list[str]:
    """Retorna o ``EXPLAIN QUERY PLAN`` da busca tipada para validação operacional."""
    path = init_db(db_path)
    where_sql, params = _apply_filters(filtros)
    sql = (
        f"EXPLAIN QUERY PLAN SELECT {_TYPED_SELECT}"
        f" FROM {TABLE_NAME}{where_sql}"
        " ORDER BY DATA_FIM DESC, NUMERO_OB DESC, SEQ ASC LIMIT ?"
    )
    params.append(limit)
    with sqlite3.connect(path) as conn:
        return [str(row[3]) for row in conn.execute(sql, params).fetchall()]


def buscar_produtos(
    termo: str,
    db_path: Path | str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Autocomplete de produto: busca por codigo (CODIGO_KEY) ou descricao (DESCR_ITEM)."""
    path = init_db(db_path)
    termo_norm = termo.strip()
    if not termo_norm:
        return []
    like = f"%{termo_norm}%"
    sql = (
        "SELECT DISTINCT CODIGO_KEY AS codigo, DESCR_ITEM AS produto"
        f" FROM {TABLE_NAME}"
        " WHERE COALESCE(CODIGO_KEY, '') != ''"
        " AND (CODIGO_KEY LIKE ? OR DESCR_ITEM LIKE ?)"
        " ORDER BY produto LIMIT ?"
    )
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, [like, like, limit])
        return [
            {"codigo": row["codigo"], "produto": row["produto"] or "Sem descrição"}
            for row in cursor.fetchall()
        ]


def descrever_schema_historico(
    db_path: Path | str | None = None,
) -> dict[str, dict[str, str] | list[str]]:
    """Expoe metadados minimos do historico pela camada autorizada do dominio."""
    path = init_db(db_path)
    with sqlite3.connect(path) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        }
        indexes = [
            row[1]
            for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
        ]
    return {"columns": columns, "indexes": indexes}

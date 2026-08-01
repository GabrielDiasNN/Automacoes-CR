"""Utilitários compartilhados de query: filtros, janela de datas e dataset temporário.

Extraído de ``_queries`` para isolar as camadas comuns usadas tanto pelo
contrato de overview quanto pelo contrato de detail.
"""

# pylint: disable=line-too-long

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from ..core import normalize_shift, parse_iso_date, safe_strip
from ..data.schema import COLUMN_NAMES

# Projeção tipada usada no drill-down (tudo menos o blob de auditoria).
_DETAIL_TYPED: tuple[str, ...] = tuple(
    c for c in COLUMN_NAMES if c != "DADOS_COMPLETOS"
)
_DETAIL_SELECT = ", ".join(_DETAIL_TYPED)

# Aliases finos para preservar os nomes internos usados no módulo.
_parse_date = parse_iso_date
_safe_strip = safe_strip


def _normalize_request_filters(filtros: Mapping[str, Any]) -> dict[str, str]:
    """Normaliza e extrai os filtros de request para strings limpas."""
    return {
        "dt_inicio": _safe_strip(filtros.get("dt_inicio")),
        "dt_fim": _safe_strip(filtros.get("dt_fim")),
        "maquina": _safe_strip(filtros.get("maquina")),
        "fase": _safe_strip(filtros.get("fase")),
        "turno": _safe_strip(filtros.get("turno")),
        "alternativo": _safe_strip(filtros.get("alternativo")),
        "q": _safe_strip(filtros.get("q")),
        "ob": _safe_strip(filtros.get("ob")),
        "setor": _safe_strip(filtros.get("setor")),
        "grupo_fase": _safe_strip(filtros.get("grupo_fase")),
        "tipo_maquina": _safe_strip(filtros.get("tipo_maquina")),
        "reprocesso": _safe_strip(filtros.get("reprocesso")),
        "status": _safe_strip(filtros.get("status")),
    }


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Enriquece um registro com campos derivados de turno e produto."""
    turno_id, turno_label = normalize_shift(record)
    item = dict(record)
    item["TURNO_PROD"] = turno_id or item.get("TURNO_PROD")
    item["TURNO_DESC"] = turno_label or item.get("TURNO_DESC") or "Indefinido"
    item["CODIGO_OPERACIONAL"] = _safe_strip(
        item.get("CODIGO_ALTERNATIVO") or item.get("REDUZ")
    )
    item["PRODUTO_LABEL"] = _safe_strip(
        item.get("DESCR_ITEM")
        or item.get("CODIGO_ALTERNATIVO")
        or item.get("REDUZ")
        or "Sem produto"
    )
    return item


def _resolve_overview_window(
    cursor: sqlite3.Cursor, filtros: Mapping[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """Resolve a janela de datas efetiva para o overview (início, fim, max)."""
    normalized = _normalize_request_filters(filtros)
    requested_inicio = _parse_date(normalized.get("dt_inicio"))
    requested_fim = _parse_date(normalized.get("dt_fim"))

    cursor.execute(
        "SELECT MAX(substr(DATA_FIM, 1, 10)) AS max_data FROM fato_producao_historica WHERE DATA_FIM IS NOT NULL"
    )
    row = cursor.fetchone()
    max_data = _parse_date(row["max_data"] if row else None)
    if max_data is None and requested_inicio is None and requested_fim is None:
        return None, None, None

    effective_fim = requested_fim or max_data or requested_inicio
    effective_inicio = requested_inicio or (
        effective_fim - timedelta(days=29) if effective_fim else None
    )

    return (
        effective_inicio.isoformat() if effective_inicio else None,
        effective_fim.isoformat() if effective_fim else None,
        max_data.isoformat() if max_data else None,
    )


def _build_filtered_where(
    filtros: Mapping[str, Any], dt_inicio: str | None, dt_fim: str | None
) -> tuple[str, list[Any]]:
    """Monta a cláusula WHERE parametrizada a partir dos filtros de request."""
    where_clauses = ["1=1"]
    params: list[Any] = []
    normalized = _normalize_request_filters(filtros)

    if dt_inicio:
        where_clauses.append("DATA_FIM >= ?")
        params.append(f"{dt_inicio}T00:00:00")

    if dt_fim:
        dt_fim_bound = (
            datetime.strptime(dt_fim, "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()
        where_clauses.append("DATA_FIM < ?")
        params.append(f"{dt_fim_bound}T00:00:00")

    if normalized["maquina"]:
        where_clauses.append("MAQUINA_KEY = ?")
        params.append(normalized["maquina"])

    if normalized["fase"]:
        where_clauses.append("FASE_KEY = ?")
        params.append(normalized["fase"])

    if normalized["turno"]:
        where_clauses.append("TURNO_LABEL = ?")
        params.append(normalized["turno"])

    if normalized["alternativo"]:
        where_clauses.append("CODIGO_KEY = ?")
        params.append(normalized["alternativo"])

    if normalized["setor"]:
        where_clauses.append("SETOR_KEY = ?")
        params.append(normalized["setor"])

    if normalized["grupo_fase"]:
        where_clauses.append("GRUPO_FASE_KEY = ?")
        params.append(normalized["grupo_fase"])

    if normalized["tipo_maquina"]:
        where_clauses.append("TIPO_MAQ_KEY = ?")
        params.append(normalized["tipo_maquina"])

    if normalized["reprocesso"] in ("0", "1"):
        where_clauses.append("REPROCESSO = ?")
        params.append(int(normalized["reprocesso"]))

    if normalized["status"] in ("confirmada", "planejada"):
        where_clauses.append("STATUS_KEY = ?")
        params.append(normalized["status"])

    termo = normalized["q"]
    if termo:
        like = f"%{termo}%"
        where_clauses.append(
            "("
            "NUMERO_OB LIKE ? OR CODIGO_ALTERNATIVO LIKE ? OR REDUZ LIKE ? OR "
            "DESCR_ITEM LIKE ? OR ARTIGO LIKE ? OR DESCR_ARTIGO LIKE ? OR "
            "COR LIKE ? OR DESCR_COR LIKE ?"
            ")"
        )
        params.extend([like] * 8)

    return " AND ".join(where_clauses), params


def _build_filtered_dataset(
    cursor: sqlite3.Cursor, where_sql: str, params: list[Any]
) -> None:
    """Cria tabela temporária ``filtered_beneficiamento`` com índices."""
    cursor.execute("DROP TABLE IF EXISTS temp.filtered_beneficiamento;")
    cursor.execute(
        f"""
        CREATE TEMP TABLE filtered_beneficiamento AS
        SELECT
            NUMERO_OB,
            SEQ,
            DATA_FIM,
            NOME_MAQUINA,
            CODIGO_FASE,
            DESCR_FASE,
            DESCR_GRUPO_FASE,
            DESCR_SETOR_INDUST,
            DESCR_TIPO_MAQ,
            CODIGO_ALTERNATIVO,
            REDUZ,
            DESCR_ITEM,
            ARTIGO,
            DESCR_ARTIGO,
            COR,
            DESCR_COR,
            QT_KG,
            QT_MT,
            REPROCESSO,
            STATUS_FASE,
            DS_STATUS_FASE,
            MIN_REAL,
            MIN_PREV,
            DESVIO_MIN,
            TURNO_ID,
            COALESCE(TURNO_LABEL, 'Indefinido') AS TURNO_LABEL,
            MAQUINA_KEY,
            FASE_KEY,
            SETOR_KEY,
            GRUPO_FASE_KEY,
            TIPO_MAQ_KEY,
            STATUS_KEY,
            CODIGO_KEY
        FROM fato_producao_historica
        WHERE {where_sql}
        """,  # nosec B608
        params,
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_turno ON filtered_beneficiamento(TURNO_LABEL);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_fase ON filtered_beneficiamento(FASE_KEY);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_codigo ON filtered_beneficiamento(CODIGO_KEY);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_setor ON filtered_beneficiamento(SETOR_KEY);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_status ON filtered_beneficiamento(STATUS_KEY);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_tipo_maq ON filtered_beneficiamento(TIPO_MAQ_KEY);"
    )


def _fetch_filter_options(
    cursor: sqlite3.Cursor,
) -> dict[str, list[str]]:
    """Retorna listas de valores distintos para os filtros de UI."""
    queries = {
        "maquinas": """
            SELECT DISTINCT MAQUINA_KEY AS value
            FROM filtered_beneficiamento
            WHERE COALESCE(MAQUINA_KEY, '') != ''
            ORDER BY value
            LIMIT 160
        """,
        "fases": """
            SELECT DISTINCT FASE_KEY AS value
            FROM filtered_beneficiamento
            WHERE COALESCE(FASE_KEY, '') != ''
            ORDER BY value
            LIMIT 160
        """,
        "turnos": """
            SELECT DISTINCT TURNO_LABEL AS value
            FROM filtered_beneficiamento
            ORDER BY value
            LIMIT 20
        """,
        "setores": """
            SELECT DISTINCT SETOR_KEY AS value
            FROM filtered_beneficiamento
            WHERE COALESCE(SETOR_KEY, '') != ''
            ORDER BY value
            LIMIT 60
        """,
        "grupos_fase": """
            SELECT DISTINCT GRUPO_FASE_KEY AS value
            FROM filtered_beneficiamento
            WHERE COALESCE(GRUPO_FASE_KEY, '') != ''
            ORDER BY value
            LIMIT 60
        """,
        "tipos_maquina": """
            SELECT DISTINCT TIPO_MAQ_KEY AS value
            FROM filtered_beneficiamento
            WHERE COALESCE(TIPO_MAQ_KEY, '') != ''
            ORDER BY value
            LIMIT 60
        """,
    }
    options: dict[str, list[str]] = {
        "maquinas": [],
        "fases": [],
        "turnos": [],
        "setores": [],
        "grupos_fase": [],
        "tipos_maquina": [],
    }
    for key, sql in queries.items():
        cursor.execute(sql)
        options[key] = [str(row["value"]) for row in cursor.fetchall() if row["value"]]
    return options

"""Orquestrador do contrato público de drill-down histórico."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import round_or_zero, safe_strip
from ..data.schema import TABLE_NAME, init_db
from ._queries import (_DETAIL_SELECT, _build_filtered_where, _build_trace,
                       _detail_raw_records, _detail_row_to_record,
                       _normalize_request_filters, _resolve_overview_window,
                       _summary_from_records)


def _target_filter(
    target_type: str,
    filtros: dict[str, Any],
    normalized: dict[str, str],
) -> tuple[str, list[Any], str]:
    if target_type == "produto":
        codigo = normalized["alternativo"] or safe_strip(filtros.get("codigo"))
        return "CODIGO_KEY = ?", [codigo], codigo or "Produto"
    if target_type == "maquina_fase":
        return (
            "MAQUINA_KEY = ? AND FASE_KEY = ?",
            [normalized["maquina"], normalized["fase"]],
            f"{normalized['maquina']} / {normalized['fase']}",
        )
    if target_type == "fase":
        return "FASE_KEY = ?", [normalized["fase"]], normalized["fase"] or "Fase"
    if target_type == "turno":
        return (
            "TURNO_LABEL = ?",
            [normalized["turno"]],
            normalized["turno"] or "Turno",
        )
    if target_type == "ob":
        return "NUMERO_OB LIKE ?", [f"{normalized['ob']}%"], normalized["ob"] or "OB"
    return "1=1", [], target_type


def obter_detail_historico(  # pylint: disable=too-many-locals
    filtros: dict[str, Any], db_path: Path | str | None = None
) -> dict[str, Any]:
    """Retorna o drill-down operacional paginado para clique na UI."""
    path = init_db(db_path)
    limit = max(1, min(int(filtros.get("limit") or 50), 200))
    page = max(1, int(filtros.get("page") or 1))
    target_type = safe_strip(filtros.get("target_type")) or "produto"
    include_raw = str(filtros.get("include_raw") or "").lower() == "true"

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        dt_inicio, dt_fim, _ = _resolve_overview_window(cursor, filtros)
        where_sql, params = _build_filtered_where(filtros, dt_inicio, dt_fim)
        target_sql, target_params, target_label = _target_filter(
            target_type, filtros, _normalize_request_filters(filtros)
        )
        where_sql = f"{where_sql} AND {target_sql}"
        params.extend(target_params)

        total = int(
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLE_NAME} WHERE {where_sql}",
                params,
            ).fetchone()["total"]
            or 0
        )
        raw_select = ", DADOS_COMPLETOS" if include_raw else ""
        rows = cursor.execute(
            f"""
            SELECT {_DETAIL_SELECT}{raw_select}
            FROM {TABLE_NAME}
            WHERE {where_sql}
            ORDER BY DATA_FIM DESC, NUMERO_OB DESC, SEQ ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, (page - 1) * limit],
        ).fetchall()
        records = [_detail_row_to_record(row) for row in rows]

    curated = [
        {
            "ob": item.get("NUMERO_OB"),
            "seq": item.get("SEQ"),
            "data_fim": item.get("DATA_FIM"),
            "fase": item.get("CD_DS_FASE"),
            "maquina": safe_strip(item.get("NOME_MAQUINA")),
            "turno": item.get("TURNO_DESC") or "Indefinido",
            "alternativo": safe_strip(item.get("CODIGO_ALTERNATIVO")),
            "reduz": safe_strip(item.get("REDUZ")),
            "produto": safe_strip(item.get("DESCR_ITEM")),
            "artigo": safe_strip(item.get("ARTIGO") or item.get("DESCR_ARTIGO")),
            "cor": safe_strip(item.get("DESCR_COR") or item.get("COR")),
            "kg": round_or_zero(item.get("QT_KG")),
            "mt": round_or_zero(item.get("QT_MT")),
            "min_real": round_or_zero(item.get("MIN_REAL")),
            "min_prev": round_or_zero(item.get("MIN_PREV")),
            "desvio_min": round_or_zero(item.get("DESVIO_MIN")),
            "reprocesso": int(item.get("REPROCESSO") or 0),
        }
        for item in records
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {"effective": dict(filtros, dt_inicio=dt_inicio, dt_fim=dt_fim)},
        "target": {"type": target_type, "label": target_label},
        "summary": _summary_from_records(target_type, records),
        "records": curated,
        "trace": _build_trace(records),
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, (total + limit - 1) // limit),
        },
        "raw_records": _detail_raw_records(records) if include_raw else [],
    }


__all__ = ["obter_detail_historico"]

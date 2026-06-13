"""Orquestrador do contrato público de overview histórico."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..data.schema import init_db
from ._queries import (
    _build_filtered_dataset,
    _build_filtered_where,
    _build_fases_criticas,
    _build_gargalos,
    _build_overview_kpis,
    _build_overview_series,
    _build_produtos,
    _build_tingimento,
    _build_turnos,
    _fetch_filter_options,
    _normalize_request_filters,
    _resolve_overview_window,
)


def obter_overview_historico(  # pylint: disable=too-many-locals
    filtros: dict[str, Any], db_path: Path | str | None = None
) -> dict[str, Any]:
    """Monta o contrato operacional V1 sem abrir Oracle."""
    path = init_db(db_path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        normalized = _normalize_request_filters(filtros)
        dt_inicio, dt_fim, max_data_fim = _resolve_overview_window(cursor, filtros)
        where_sql, params = _build_filtered_where(filtros, dt_inicio, dt_fim)
        _build_filtered_dataset(cursor, where_sql, params)

        fases, kpis = _build_overview_kpis(cursor)
        rankings = {
            "gargalos": _build_gargalos(cursor),
            "fases_criticas": _build_fases_criticas(cursor),
            "produtos_principais": _build_produtos(cursor),
        }
        series = _build_overview_series(cursor)
        turnos = _build_turnos(cursor)
        tingimento = _build_tingimento(cursor)
        filter_options = _fetch_filter_options(cursor)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "effective": {
                "dt_inicio": dt_inicio,
                "dt_fim": dt_fim,
                "maquina": normalized["maquina"] or None,
                "fase": normalized["fase"] or None,
                "turno": normalized["turno"] or None,
                "alternativo": normalized["alternativo"] or None,
                "q": normalized["q"] or None,
            }
        },
        "health": {
            "status": "healthy" if fases > 0 else "no_data",
            "source": "sqlite_historico",
            "max_data_fim": max_data_fim,
            "records": fases,
            "findings": (
                []
                if fases > 0
                else ["Nenhum registro encontrado para o recorte filtrado."]
            ),
        },
        "kpis": kpis,
        "rankings": rankings,
        "series": series,
        "filter_options": filter_options,
        "turnos": turnos,
        "tingimento": tingimento,
        "interaction": {
            "detail_endpoint": "/api/beneficiamento/detail",
            "clickable_targets": ["produto", "maquina_fase", "fase", "turno", "ob"],
        },
    }

__all__ = ["obter_overview_historico"]

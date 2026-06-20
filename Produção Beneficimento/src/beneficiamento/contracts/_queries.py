# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments,useless-import-alias
"""Implementação compartilhada dos contratos históricos baseados em SQLite.

Os pontos públicos ficam em ``contracts.overview``, ``contracts.detail`` e
``contracts.analytics``. Este módulo re-exporta os builders dos sub-módulos
especializados e preserva as implementações legadas ``obter_*`` para
compatibilidade interna.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import round_or_zero as _round
from ..data.schema import init_db
from ._queries_common import (
    _DETAIL_SELECT as _DETAIL_SELECT,
    _DETAIL_TYPED as _DETAIL_TYPED,
    _build_filtered_dataset as _build_filtered_dataset,
    _build_filtered_where as _build_filtered_where,
    _fetch_filter_options as _fetch_filter_options,
    _normalize_record as _normalize_record,
    _normalize_request_filters as _normalize_request_filters,
    _parse_date as _parse_date,
    _resolve_overview_window as _resolve_overview_window,
    _safe_strip as _safe_strip,
)
from ._queries_detail import (
    _build_trace as _build_trace,
    _detail_raw_records as _detail_raw_records,
    _detail_row_to_record as _detail_row_to_record,
    _summary_from_records as _summary_from_records,
)
from ._queries_overview import (
    _build_fases_criticas as _build_fases_criticas,
    _build_gargalos as _build_gargalos,
    _build_overview_kpis as _build_overview_kpis,
    _build_overview_series as _build_overview_series,
    _build_produtos as _build_produtos,
    _build_tingimento as _build_tingimento,
    _build_turnos as _build_turnos,
)


# --- Implementações legadas (não usadas pelo roteador; preservadas para compat) ---


def obter_overview_historico(
    filtros: dict[str, Any], db_path: Path | str | None = None
) -> dict[str, Any]:
    """Monta o contrato operacional V1 do Beneficiamento sem abrir Oracle."""
    path = init_db(db_path)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        normalized = _normalize_request_filters(filtros)
        dt_inicio, dt_fim, max_data_fim = _resolve_overview_window(cursor, filtros)
        where_sql, params = _build_filtered_where(filtros, dt_inicio, dt_fim)
        _build_filtered_dataset(cursor, where_sql, params)

        fases, kpis = _build_overview_kpis(cursor)
        gargalos = _build_gargalos(cursor)
        fases_criticas = _build_fases_criticas(cursor)
        produtos = _build_produtos(cursor)
        series = _build_overview_series(cursor)
        turnos = _build_turnos(cursor)
        tingimento = _build_tingimento(cursor)
        filter_options = _fetch_filter_options(cursor)

    status = "healthy" if fases > 0 else "no_data"
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
            "status": status,
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
        "rankings": {
            "gargalos": gargalos,
            "fases_criticas": fases_criticas,
            "produtos_principais": produtos,
        },
        "series": series,
        "filter_options": filter_options,
        "turnos": turnos,
        "tingimento": tingimento,
        "interaction": {
            "detail_endpoint": "/api/beneficiamento/detail",
            "clickable_targets": ["produto", "maquina_fase", "fase", "turno", "ob"],
        },
    }


def obter_detail_historico(
    filtros: dict[str, Any], db_path: Path | str | None = None
) -> dict[str, Any]:
    """Retorna o drill-down operacional para clique na UI."""
    path = init_db(db_path)
    limit = max(1, min(int(filtros.get("limit") or 50), 200))
    page = max(1, int(filtros.get("page") or 1))
    offset = (page - 1) * limit
    target_type = _safe_strip(filtros.get("target_type")) or "produto"
    include_raw = str(filtros.get("include_raw") or "").lower() == "true"

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        dt_inicio, dt_fim, _max_data_fim = _resolve_overview_window(cursor, filtros)
        where_sql, params = _build_filtered_where(filtros, dt_inicio, dt_fim)
        normalized = _normalize_request_filters(filtros)

        if target_type == "produto":
            codigo = normalized["alternativo"] or _safe_strip(filtros.get("codigo"))
            where_sql = f"{where_sql} AND CODIGO_KEY = ?"
            params.append(codigo)
            target_label = codigo or "Produto"
        elif target_type == "maquina_fase":
            where_sql = f"{where_sql} AND MAQUINA_KEY = ? AND FASE_KEY = ?"
            params.extend([normalized["maquina"], normalized["fase"]])
            target_label = f"{normalized['maquina']} / {normalized['fase']}"
        elif target_type == "fase":
            where_sql = f"{where_sql} AND FASE_KEY = ?"
            params.append(normalized["fase"])
            target_label = normalized["fase"] or "Fase"
        elif target_type == "turno":
            where_sql = f"{where_sql} AND TURNO_LABEL = ?"
            params.append(normalized["turno"])
            target_label = normalized["turno"] or "Turno"
        elif target_type == "ob":
            where_sql = f"{where_sql} AND NUMERO_OB LIKE ?"
            params.append(f"{normalized['ob']}%")
            target_label = normalized["ob"] or "OB"
        else:
            target_label = target_type

        cursor.execute(
            f"SELECT COUNT(*) AS total FROM fato_producao_historica WHERE {where_sql}",
            params,
        )
        total = int(cursor.fetchone()["total"] or 0)

        raw_select = ", DADOS_COMPLETOS" if include_raw else ""
        cursor.execute(
            f"""
            SELECT {_DETAIL_SELECT}{raw_select}
            FROM fato_producao_historica
            WHERE {where_sql}
            ORDER BY DATA_FIM DESC, NUMERO_OB DESC, SEQ ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        records = [_detail_row_to_record(row) for row in cursor.fetchall()]
        raw_records = _detail_raw_records(records) if include_raw else []

        summary = _summary_from_records(target_type, records)
        trace = _build_trace(records)

        curated = [
            {
                "ob": item.get("NUMERO_OB"),
                "seq": item.get("SEQ"),
                "data_fim": item.get("DATA_HORA_FIM") or item.get("DATA_FIM"),
                "fase": item.get("CD_DS_FASE"),
                "maquina": _safe_strip(item.get("NOME_MAQUINA")),
                "turno": item.get("TURNO_DESC") or "Indefinido",
                "alternativo": _safe_strip(item.get("CODIGO_ALTERNATIVO")),
                "reduz": _safe_strip(item.get("REDUZ")),
                "produto": _safe_strip(item.get("DESCR_ITEM")),
                "artigo": _safe_strip(item.get("ARTIGO") or item.get("DESCR_ARTIGO")),
                "cor": _safe_strip(item.get("DESCR_COR") or item.get("COR")),
                "kg": _round(item.get("QT_KG")),
                "mt": _round(item.get("QT_MT")),
                "min_real": _round(item.get("MIN_REAL")),
                "min_prev": _round(item.get("MIN_PREV")),
                "desvio_min": _round(item.get("DESVIO_MIN")),
                "reprocesso": int(item.get("REPROCESSO") or 0),
            }
            for item in records
        ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "effective": {
                "dt_inicio": dt_inicio,
                "dt_fim": dt_fim,
                "maquina": filtros.get("maquina"),
                "fase": filtros.get("fase"),
                "turno": filtros.get("turno"),
                "alternativo": filtros.get("alternativo"),
                "q": filtros.get("q"),
                "ob": filtros.get("ob"),
            }
        },
        "target": {"type": target_type, "label": target_label},
        "summary": summary,
        "records": curated,
        "trace": trace,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, (total + limit - 1) // limit),
        },
        "raw_records": raw_records,
    }


def obter_analytics_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Compatibilidade legada: deriva o contrato antigo do overview V0."""
    overview_filters = {
        "dt_inicio": filtros.get("dt_inicio"),
        "dt_fim": filtros.get("dt_fim"),
        "maquina": filtros.get("maquina"),
        "fase": filtros.get("fase"),
        "turno": filtros.get("turno"),
        "alternativo": filtros.get("alternativo"),
        "q": filtros.get("busca") or filtros.get("ob") or filtros.get("alternativo"),
    }
    overview = obter_overview_historico(overview_filters, db_path=db_path)
    kpis = overview.get("kpis", {})
    rankings = overview.get("rankings", {})
    filter_options = overview.get("filter_options", {})

    maquinas = []
    for item in rankings.get("gargalos", []):
        maquinas.append(
            {
                "maquina": item.get("maquina") or "Sem máquina",
                "kg_total": item.get("kg_total") or 0.0,
                "mt_total": item.get("mt_total") or 0.0,
                "total_fases": item.get("fases_concluidas") or 0,
                "min_real": item.get("desvio_min") or 0.0,
                "min_setup": 0.0,
                "min_processo": item.get("desvio_min") or 0.0,
            }
        )

    produtos = [
        {
            "reduz": item.get("codigo") or "-",
            "produto": item.get("produto") or "Sem descrição",
            "artigo": item.get("artigo") or "Sem artigo",
            "kg_total": item.get("kg_total") or 0.0,
            "mt_total": item.get("mt_total") or 0.0,
            "taxa_reprocesso": item.get("reprocesso_kg_pct") or 0.0,
            "produtividade_kgh": item.get("produtividade_kg_h") or 0.0,
        }
        for item in rankings.get("produtos_principais", [])
    ]

    fases = [
        {
            "fase": item.get("fase") or "Sem fase",
            "kg_total": item.get("kg_total") or 0.0,
            "mt_total": 0.0,
            "total_fases": item.get("fases_concluidas") or 0,
            "reprocesso_percent": item.get("reprocesso_kg_pct") or 0.0,
            "efic_tempo": item.get("eficiencia_tempo_pct") or 0.0,
        }
        for item in rankings.get("fases_criticas", [])
    ]

    return {
        "geral": {
            "ob_distintas": kpis.get("ob_distintas") or 0,
            "total_fases": kpis.get("fases_concluidas") or 0,
            "maquinas_distintas": len(filter_options.get("maquinas", [])),
            "total_operadores": 0,
            "kg_total": kpis.get("kg_total") or 0.0,
            "mt_total": kpis.get("mt_total") or 0.0,
            "min_real_total": 0.0,
            "min_prev_total": 0.0,
            "desvio_min_total": kpis.get("desvio_tempo_min") or 0.0,
            "efic_tempo_media": kpis.get("eficiencia_tempo_pct") or 0.0,
            "taxa_reprocesso": kpis.get("reprocesso_kg_pct") or 0.0,
            "produtividade_kgh": kpis.get("produtividade_kg_h") or 0.0,
        },
        "operadores": [],
        "maquinas": maquinas,
        "produtos": produtos,
        "turnos": [
            {"turno": value, "kg_total": 0.0}
            for value in filter_options.get("turnos", [])
        ],
        "fases": fases,
        "artigos": [],
        "cores": [],
    }

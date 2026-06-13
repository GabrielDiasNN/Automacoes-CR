"""Contrato público da visão analítica histórica."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .overview import obter_overview_historico


def obter_analytics_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Deriva o contrato analítico legado a partir do overview SQL."""
    overview = obter_overview_historico(
        {
            "dt_inicio": filtros.get("dt_inicio"),
            "dt_fim": filtros.get("dt_fim"),
            "maquina": filtros.get("maquina"),
            "fase": filtros.get("fase"),
            "turno": filtros.get("turno"),
            "alternativo": filtros.get("alternativo"),
            "q": filtros.get("busca")
            or filtros.get("ob")
            or filtros.get("alternativo"),
        },
        db_path=db_path,
    )
    kpis = overview.get("kpis", {})
    rankings = overview.get("rankings", {})
    options = overview.get("filter_options", {})
    return {
        "geral": {
            "ob_distintas": kpis.get("ob_distintas") or 0,
            "total_fases": kpis.get("fases_concluidas") or 0,
            "maquinas_distintas": len(options.get("maquinas", [])),
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
        "maquinas": [
            {
                "maquina": item.get("maquina") or "Sem máquina",
                "kg_total": item.get("kg_total") or 0.0,
                "mt_total": item.get("mt_total") or 0.0,
                "total_fases": item.get("fases_concluidas") or 0,
                "min_real": item.get("desvio_min") or 0.0,
                "min_setup": 0.0,
                "min_processo": item.get("desvio_min") or 0.0,
            }
            for item in rankings.get("gargalos", [])
        ],
        "produtos": [
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
        ],
        "turnos": [
            {"turno": value, "kg_total": 0.0} for value in options.get("turnos", [])
        ],
        "fases": [
            {
                "fase": item.get("fase") or "Sem fase",
                "kg_total": item.get("kg_total") or 0.0,
                "mt_total": 0.0,
                "total_fases": item.get("fases_concluidas") or 0,
                "reprocesso_percent": item.get("reprocesso_kg_pct") or 0.0,
                "efic_tempo": item.get("eficiencia_tempo_pct") or 0.0,
            }
            for item in rankings.get("fases_criticas", [])
        ],
        "artigos": [],
        "cores": [],
    }


__all__ = ["obter_analytics_historico"]

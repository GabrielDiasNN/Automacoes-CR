"""Painel dedicado de Tingimento (fase real CODIGO_FASE = 40).

Escopo fixo — independente dos filtros gerais do overview — pensado para
controle de reprocesso (relativizado ao KG produzido), setup e eficiência
de tempo especificamente da tinturaria. Reconstruido do zero (o antigo
bloco fixo por bucket textual foi removido em favor de fase real por
setor/fase no overview geral); este modulo cobre a analise aprofundada
que o overview geral nao tem espaco para.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..core import parse_iso_date
from ..core import round_or_zero as _round
from ..core import safe_strip as _safe_strip
from ..data.schema import init_db

_CODIGO_FASE_TINGIMENTO = 40

# Abaixo desta contagem de fases, percentuais de reprocesso por maquina/cor
# sao estatisticamente instaveis e devem ser sinalizados como tal na UI.
_AMOSTRA_MINIMA = 20


def _resolve_window(
    cursor: sqlite3.Cursor, filtros: dict[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """Janela de datas efetiva, calculada apenas sobre linhas de Tingimento."""
    requested_inicio = parse_iso_date(_safe_strip(filtros.get("dt_inicio")))
    requested_fim = parse_iso_date(_safe_strip(filtros.get("dt_fim")))

    cursor.execute(
        "SELECT MAX(substr(DATA_FIM, 1, 10)) AS max_data FROM fato_producao_historica"
        " WHERE CODIGO_FASE = ? AND DATA_FIM IS NOT NULL",
        (_CODIGO_FASE_TINGIMENTO,),
    )
    row = cursor.fetchone()
    max_data = parse_iso_date(row["max_data"] if row else None)
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


def _build_where(dt_inicio: str | None, dt_fim: str | None) -> tuple[str, list[Any]]:
    where = ["CODIGO_FASE = ?"]
    params: list[Any] = [_CODIGO_FASE_TINGIMENTO]
    if dt_inicio:
        where.append("DATA_FIM >= ?")
        params.append(f"{dt_inicio}T00:00:00")
    if dt_fim:
        fim_bound = (
            datetime.strptime(dt_fim, "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()
        where.append("DATA_FIM < ?")
        params.append(f"{fim_bound}T00:00:00")
    return " AND ".join(where), params


def _build_resumo(
    cursor: sqlite3.Cursor, where_sql: str, params: list[Any]
) -> tuple[int, dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            COUNT(*) AS fases,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(QT_MT, 0)) AS mt_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real_total,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev_total,
            SUM(COALESCE(MIN_SETUP, 0)) AS min_setup_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg,
            SUM(CASE WHEN REPROCESSO = 1 THEN 1 ELSE 0 END) AS fases_reprocessadas
        FROM fato_producao_historica
        WHERE {where_sql}
        """,
        params,
    )
    row = cursor.fetchone()
    fases = int(row["fases"] or 0)
    kg_total = float(row["kg_total"] or 0.0)
    min_real = float(row["min_real_total"] or 0.0)
    min_prev = float(row["min_prev_total"] or 0.0)
    min_setup = float(row["min_setup_total"] or 0.0)
    reprocesso_kg = float(row["reprocesso_kg"] or 0.0)
    resumo = {
        "ob_distintas": int(row["ob_distintas"] or 0),
        "fases": fases,
        "kg_total": _round(kg_total),
        "mt_total": _round(row["mt_total"]),
        "eficiencia_tempo_pct": _round(
            (min_prev / min_real * 100.0) if min_real > 0 else 0.0
        ),
        "reprocesso_kg_pct": _round(
            (reprocesso_kg / kg_total * 100.0) if kg_total > 0 else 0.0
        ),
        "fases_reprocessadas": int(row["fases_reprocessadas"] or 0),
        "setup_medio_min": _round((min_setup / fases) if fases > 0 else 0.0),
        "desvio_medio_min": _round(
            ((min_real - min_prev) / fases) if fases > 0 else 0.0
        ),
        "produtividade_kg_h": _round(
            (kg_total * 60.0 / min_real) if min_real > 0 else 0.0
        ),
    }
    return fases, resumo


def _build_series(
    cursor: sqlite3.Cursor, where_sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT
            substr(DATA_FIM, 1, 10) AS dia,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg
        FROM fato_producao_historica
        WHERE {where_sql} AND DATA_FIM IS NOT NULL
        GROUP BY dia
        ORDER BY dia
        LIMIT 90
        """,
        params,
    )
    serie = []
    for item in cursor.fetchall():
        min_real = float(item["min_real"] or 0.0)
        min_prev = float(item["min_prev"] or 0.0)
        kg_dia = float(item["kg_total"] or 0.0)
        serie.append(
            {
                "date": item["dia"],
                "kg_total": _round(kg_dia),
                "eficiencia_tempo_pct": _round(
                    (min_prev / min_real * 100.0) if min_real > 0 else 0.0
                ),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_dia * 100.0)
                    if kg_dia > 0
                    else 0.0
                ),
            }
        )
    return serie


def _build_por_maquina(
    cursor: sqlite3.Cursor, where_sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT
            COALESCE(MAQUINA_KEY, 'Sem máquina') AS maquina,
            COUNT(*) AS fases,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev,
            SUM(COALESCE(MIN_SETUP, 0)) AS min_setup,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg
        FROM fato_producao_historica
        WHERE {where_sql}
        GROUP BY maquina
        ORDER BY kg_total DESC
        LIMIT 15
        """,
        params,
    )
    itens = []
    for item in cursor.fetchall():
        fases_maq = int(item["fases"] or 0)
        kg_maq = float(item["kg_total"] or 0.0)
        min_real = float(item["min_real"] or 0.0)
        min_prev = float(item["min_prev"] or 0.0)
        itens.append(
            {
                "maquina": item["maquina"],
                "fases": fases_maq,
                "kg_total": _round(kg_maq),
                "eficiencia_tempo_pct": _round(
                    (min_prev / min_real * 100.0) if min_real > 0 else 0.0
                ),
                "setup_medio_min": _round(
                    (float(item["min_setup"] or 0.0) / fases_maq)
                    if fases_maq > 0
                    else 0.0
                ),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_maq * 100.0)
                    if kg_maq > 0
                    else 0.0
                ),
                "amostra_insuficiente": fases_maq < _AMOSTRA_MINIMA,
            }
        )
    return itens


def _build_por_cor(
    cursor: sqlite3.Cursor, where_sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT
            TRIM(COALESCE(DESCR_COR, COR, 'Sem cor')) AS cor,
            COUNT(*) AS fases,
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg
        FROM fato_producao_historica
        WHERE {where_sql}
        GROUP BY cor
        ORDER BY kg_total DESC
        LIMIT 15
        """,
        params,
    )
    itens = []
    for item in cursor.fetchall():
        fases_cor = int(item["fases"] or 0)
        kg_cor = float(item["kg_total"] or 0.0)
        itens.append(
            {
                "cor": item["cor"],
                "fases": fases_cor,
                "ob_distintas": int(item["ob_distintas"] or 0),
                "kg_total": _round(kg_cor),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_cor * 100.0)
                    if kg_cor > 0
                    else 0.0
                ),
                "amostra_insuficiente": fases_cor < _AMOSTRA_MINIMA,
            }
        )
    return itens


def _build_por_turno(
    cursor: sqlite3.Cursor, where_sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT
            COALESCE(TURNO_LABEL, 'Indefinido') AS turno,
            COUNT(*) AS fases,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev,
            SUM(COALESCE(MIN_SETUP, 0)) AS min_setup
        FROM fato_producao_historica
        WHERE {where_sql}
        GROUP BY turno
        ORDER BY turno
        """,
        params,
    )
    itens = []
    for item in cursor.fetchall():
        fases_turno = int(item["fases"] or 0)
        min_real = float(item["min_real"] or 0.0)
        min_prev = float(item["min_prev"] or 0.0)
        itens.append(
            {
                "turno": item["turno"],
                "fases": fases_turno,
                "kg_total": _round(item["kg_total"]),
                "eficiencia_tempo_pct": _round(
                    (min_prev / min_real * 100.0) if min_real > 0 else 0.0
                ),
                "setup_medio_min": _round(
                    (float(item["min_setup"] or 0.0) / fases_turno)
                    if fases_turno > 0
                    else 0.0
                ),
            }
        )
    return itens


def obter_tingimento_historico(  # pylint: disable=too-many-locals
    filtros: dict[str, Any], db_path: Path | str | None = None
) -> dict[str, Any]:
    """Monta o painel dedicado de Tingimento (escopo fixo CODIGO_FASE=40)."""
    path = init_db(db_path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        dt_inicio, dt_fim, max_data_fim = _resolve_window(cursor, filtros)
        where_sql, params = _build_where(dt_inicio, dt_fim)

        fases, resumo = _build_resumo(cursor, where_sql, params)
        series = _build_series(cursor, where_sql, params)
        por_maquina = _build_por_maquina(cursor, where_sql, params)
        por_cor = _build_por_cor(cursor, where_sql, params)
        por_turno = _build_por_turno(cursor, where_sql, params)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {"effective": {"dt_inicio": dt_inicio, "dt_fim": dt_fim}},
        "health": {
            "status": "healthy" if fases > 0 else "no_data",
            "max_data_fim": max_data_fim,
            "records": fases,
        },
        "resumo": resumo,
        "series": {"diaria": series},
        "rankings": {
            "por_maquina": por_maquina,
            "por_cor": por_cor,
            "por_turno": por_turno,
        },
    }


__all__ = ["obter_tingimento_historico"]

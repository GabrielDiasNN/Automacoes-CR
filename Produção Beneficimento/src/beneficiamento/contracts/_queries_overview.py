"""Builders SQL específicos do contrato de overview histórico do Beneficiamento.

Extraído de ``_queries`` para isolar os builders de KPI, séries e rankings
usados exclusivamente pelo contrato de overview (``contracts.overview``).
Consome os utilitários compartilhados de ``_queries_common``.
"""

# pylint: disable=too-many-locals

from __future__ import annotations

import sqlite3
from typing import Any

from ..core import round_or_zero as _round
from ..core import safe_strip as _safe_strip


def _build_turnos(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    """Agrega KPIs de produção por turno a partir da tabela temporária filtrada."""
    cursor.execute(
        """
        SELECT
            TURNO_ID AS turno_id,
            TURNO_LABEL AS turno_label,
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(QT_MT, 0)) AS mt_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real_total,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg
        FROM filtered_beneficiamento
        GROUP BY turno_id, turno_label
        ORDER BY kg_total DESC, fases_concluidas DESC
        LIMIT 12
        """,
    )
    items: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        kg_total = float(row["kg_total"] or 0.0)
        min_real = float(row["min_real_total"] or 0.0)
        min_prev = float(row["min_prev_total"] or 0.0)
        fases = int(row["fases_concluidas"] or 0)
        items.append(
            {
                "turno_id": _safe_strip(row["turno_id"]) or None,
                "turno_label": row["turno_label"] or "Indefinido",
                "ob_distintas": int(row["ob_distintas"] or 0),
                "fases_concluidas": fases,
                "kg_total": _round(kg_total),
                "mt_total": _round(row["mt_total"]),
                "eficiencia_tempo_pct": _round(
                    (min_prev / min_real * 100.0) if min_real > 0 else 0.0
                ),
                "reprocesso_kg_pct": _round(
                    (float(row["reprocesso_kg"] or 0.0) / kg_total * 100.0)
                    if kg_total > 0
                    else 0.0
                ),
                "produtividade_kg_h": _round(
                    (kg_total * 60.0 / min_real) if min_real > 0 else 0.0
                ),
                "min_real_medio": _round((min_real / fases) if fases > 0 else 0.0),
                "desvio_medio_min": _round(
                    ((min_real - min_prev) / fases) if fases > 0 else 0.0
                ),
            }
        )
    return items


def _build_tingimento(cursor: sqlite3.Cursor) -> dict[str, Any]:
    """Monta painel completo de Tingimento: resumo, série diária e rankings."""
    ting_where = "FASE_KEY = '03 - TINGIMENTO'"
    cursor.execute(
        f"""
        SELECT
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(QT_MT, 0)) AS mt_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real_total,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg,
            SUM(CASE WHEN REPROCESSO = 1 THEN 1 ELSE 0 END) AS reprocesso_fases
        FROM filtered_beneficiamento
        WHERE {ting_where}
        """,
    )
    row = cursor.fetchone()
    fases = int(row["fases_concluidas"] or 0)
    kg_total = float(row["kg_total"] or 0.0)
    mt_total = float(row["mt_total"] or 0.0)
    min_real = float(row["min_real_total"] or 0.0)
    min_prev = float(row["min_prev_total"] or 0.0)
    summary = {
        "ob_distintas": int(row["ob_distintas"] or 0),
        "fases_concluidas": fases,
        "kg_total": _round(kg_total),
        "mt_total": _round(mt_total),
        "kg_medio_fase": _round((kg_total / fases) if fases > 0 else 0.0),
        "mt_medio_fase": _round((mt_total / fases) if fases > 0 else 0.0),
        "min_real_medio": _round((min_real / fases) if fases > 0 else 0.0),
        "min_prev_medio": _round((min_prev / fases) if fases > 0 else 0.0),
        "desvio_medio_min": _round(
            ((min_real - min_prev) / fases) if fases > 0 else 0.0
        ),
        "eficiencia_media_pct": _round(
            (min_prev / min_real * 100.0) if min_real > 0 else 0.0
        ),
        "reprocesso_kg_pct": _round(
            (float(row["reprocesso_kg"] or 0.0) / kg_total * 100.0)
            if kg_total > 0
            else 0.0
        ),
        "reprocesso_fases_pct": _round(
            (float(row["reprocesso_fases"] or 0.0) / fases * 100.0)
            if fases > 0
            else 0.0
        ),
    }

    cursor.execute(
        f"""
        SELECT
            substr(DATA_FIM, 1, 10) AS dia,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            AVG(COALESCE(MIN_REAL, 0)) AS min_real_medio,
            AVG(COALESCE(MIN_PREV, 0)) AS min_prev_medio,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg
        FROM filtered_beneficiamento
        WHERE {ting_where} AND DATA_FIM IS NOT NULL
        GROUP BY dia
        ORDER BY dia
        LIMIT 90
        """,
    )
    series: dict[str, list[dict[str, Any]]] = {"diaria": []}
    for item in cursor.fetchall():
        min_real_day = float(item["min_real_medio"] or 0.0)
        min_prev_day = float(item["min_prev_medio"] or 0.0)
        kg_day = float(item["kg_total"] or 0.0)
        series["diaria"].append(
            {
                "date": item["dia"],
                "kg_total": _round(kg_day),
                "eficiencia_media_pct": _round(
                    (min_prev_day / min_real_day * 100.0) if min_real_day > 0 else 0.0
                ),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_day * 100.0)
                    if kg_day > 0
                    else 0.0
                ),
            }
        )

    cursor.execute(
        f"""
        SELECT
            CODIGO_KEY AS alternativo,
            TRIM(COALESCE(DESCR_ITEM, 'Sem descrição')) AS produto,
            COUNT(*) AS fases_concluidas,
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            AVG(COALESCE(MIN_REAL, 0)) AS min_real_medio,
            AVG(COALESCE(MIN_PREV, 0)) AS min_prev_medio,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg
        FROM filtered_beneficiamento
        WHERE {ting_where}
        GROUP BY alternativo, produto
        ORDER BY kg_total DESC
        LIMIT 12
        """,
    )
    por_alternativo = []
    for item in cursor.fetchall():
        kg_item = float(item["kg_total"] or 0.0)
        min_real_item = float(item["min_real_medio"] or 0.0)
        min_prev_item = float(item["min_prev_medio"] or 0.0)
        por_alternativo.append(
            {
                "alternativo": item["alternativo"] or "Sem código",
                "produto": item["produto"] or "Sem descrição",
                "fases_concluidas": int(item["fases_concluidas"] or 0),
                "ob_distintas": int(item["ob_distintas"] or 0),
                "kg_total": _round(kg_item),
                "eficiencia_media_pct": _round(
                    (min_prev_item / min_real_item * 100.0)
                    if min_real_item > 0
                    else 0.0
                ),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_item * 100.0)
                    if kg_item > 0
                    else 0.0
                ),
            }
        )

    cursor.execute(
        f"""
        SELECT
            COALESCE(MAQUINA_KEY, 'Sem máquina') AS maquina,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            AVG(COALESCE(MIN_REAL, 0)) AS min_real_medio,
            AVG(COALESCE(MIN_PREV, 0)) AS min_prev_medio
        FROM filtered_beneficiamento
        WHERE {ting_where}
        GROUP BY maquina
        ORDER BY kg_total DESC
        LIMIT 10
        """,
    )
    por_maquina = []
    for item in cursor.fetchall():
        min_real_item = float(item["min_real_medio"] or 0.0)
        min_prev_item = float(item["min_prev_medio"] or 0.0)
        por_maquina.append(
            {
                "maquina": item["maquina"] or "Sem máquina",
                "fases_concluidas": int(item["fases_concluidas"] or 0),
                "kg_total": _round(item["kg_total"]),
                "eficiencia_media_pct": _round(
                    (min_prev_item / min_real_item * 100.0)
                    if min_real_item > 0
                    else 0.0
                ),
                "desvio_medio_min": _round(min_real_item - min_prev_item),
            }
        )

    return {
        "summary": summary,
        "series": series,
        "rankings": {"por_alternativo": por_alternativo, "por_maquina": por_maquina},
    }


def _build_overview_kpis(cursor: sqlite3.Cursor) -> tuple[int, dict[str, Any]]:
    """Retorna (total_fases, kpis) com métricas globais do período filtrado."""
    cursor.execute("""
        SELECT
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(QT_MT, 0)) AS mt_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real_total,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg,
            SUM(CASE WHEN REPROCESSO = 1 THEN 1 ELSE 0 END) AS fases_reprocessadas
        FROM filtered_beneficiamento
        """)
    row = cursor.fetchone()
    fases = int(row["fases_concluidas"] or 0)
    kg_total = float(row["kg_total"] or 0.0)
    min_real = float(row["min_real_total"] or 0.0)
    min_prev = float(row["min_prev_total"] or 0.0)
    reprocesso_kg = float(row["reprocesso_kg"] or 0.0)
    fases_reprocessadas = int(row["fases_reprocessadas"] or 0)
    return fases, {
        "ob_distintas": int(row["ob_distintas"] or 0),
        "fases_concluidas": fases,
        "kg_total": _round(kg_total),
        "mt_total": _round(row["mt_total"]),
        "eficiencia_tempo_pct": _round(
            (min_prev / min_real * 100.0) if min_real > 0 else 0.0
        ),
        "reprocesso_kg_pct": _round(
            (reprocesso_kg / kg_total * 100.0)
            if kg_total > 0
            else ((fases_reprocessadas / fases * 100.0) if fases > 0 else 0.0)
        ),
        "desvio_tempo_min": _round(min_real - min_prev),
        "produtividade_kg_h": _round(
            (kg_total * 60.0 / min_real) if min_real > 0 else 0.0
        ),
    }


def _build_gargalos(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    """Retorna top-10 combinações máquina/fase por score de gargalo."""
    cursor.execute("""
        SELECT
            COALESCE(MAQUINA_KEY, 'Sem máquina') AS maquina,
            COALESCE(FASE_KEY, 'Sem fase') AS fase,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(QT_MT, 0)) AS mt_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev
        FROM filtered_beneficiamento
        GROUP BY maquina, fase
        HAVING fases_concluidas > 0
        ORDER BY kg_total DESC
        LIMIT 20
        """)
    gargalos = []
    for item in cursor.fetchall():
        item_min_real = float(item["min_real"] or 0.0)
        item_min_prev = float(item["min_prev"] or 0.0)
        item_efic = (
            (item_min_prev / item_min_real * 100.0) if item_min_real > 0 else 0.0
        )
        item_desvio = item_min_real - item_min_prev
        kg_item = float(item["kg_total"] or 0.0)
        score = max(item_desvio, 0.0) * max(100.0 - item_efic, 0.0) / 100.0
        score += min(kg_item / 1000.0, 50.0)
        gargalos.append(
            {
                "maquina": item["maquina"],
                "fase": item["fase"],
                "fases_concluidas": int(item["fases_concluidas"] or 0),
                "kg_total": _round(kg_item),
                "mt_total": _round(item["mt_total"]),
                "desvio_min": _round(item_desvio),
                "eficiencia_tempo_pct": _round(item_efic),
                "score": _round(score),
            }
        )
    gargalos.sort(key=lambda value: value["score"], reverse=True)
    return gargalos[:10]


def _build_fases_criticas(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    """Retorna top-12 fases por volume de kg, com eficiência e reprocesso."""
    cursor.execute("""
        SELECT
            COALESCE(FASE_KEY, 'Sem fase') AS fase,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev
        FROM filtered_beneficiamento
        GROUP BY fase
        ORDER BY kg_total DESC
        LIMIT 12
        """)
    fases_criticas = []
    for item in cursor.fetchall():
        kg_item = float(item["kg_total"] or 0.0)
        min_real_item = float(item["min_real"] or 0.0)
        min_prev_item = float(item["min_prev"] or 0.0)
        fases_criticas.append(
            {
                "fase": item["fase"],
                "fases_concluidas": int(item["fases_concluidas"] or 0),
                "kg_total": _round(kg_item),
                "eficiencia_tempo_pct": _round(
                    (min_prev_item / min_real_item * 100.0)
                    if min_real_item > 0
                    else 0.0
                ),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_item * 100.0)
                    if kg_item > 0
                    else 0.0
                ),
            }
        )
    return fases_criticas


def _build_produtos(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    """Retorna top-20 produtos por volume de kg com KPIs de produtividade."""
    cursor.execute("""
        SELECT
            COALESCE(CODIGO_KEY, 'Sem código') AS codigo,
            TRIM(COALESCE(DESCR_ITEM, 'Sem descrição')) AS produto,
            TRIM(COALESCE(ARTIGO, DESCR_ARTIGO, 'Sem artigo')) AS artigo,
            TRIM(COALESCE(DESCR_COR, COR, 'Sem cor')) AS cor,
            COUNT(DISTINCT NUMERO_OB) AS ob_distintas,
            COUNT(*) AS fases_concluidas,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(QT_MT, 0)) AS mt_total,
            SUM(CASE WHEN REPROCESSO = 1 THEN COALESCE(QT_KG, 0) ELSE 0 END) AS reprocesso_kg,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real
        FROM filtered_beneficiamento
        GROUP BY codigo, produto, artigo, cor
        ORDER BY kg_total DESC
        LIMIT 20
        """)
    produtos = []
    for item in cursor.fetchall():
        kg_item = float(item["kg_total"] or 0.0)
        min_real_item = float(item["min_real"] or 0.0)
        produtos.append(
            {
                "codigo": item["codigo"],
                "produto": item["produto"],
                "artigo": item["artigo"],
                "cor": item["cor"],
                "ob_distintas": int(item["ob_distintas"] or 0),
                "fases_concluidas": int(item["fases_concluidas"] or 0),
                "kg_total": _round(kg_item),
                "mt_total": _round(item["mt_total"]),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_item * 100.0)
                    if kg_item > 0
                    else 0.0
                ),
                "produtividade_kg_h": _round(
                    (kg_item * 60.0 / min_real_item) if min_real_item > 0 else 0.0
                ),
            }
        )
    return produtos


def _build_overview_series(cursor: sqlite3.Cursor) -> dict[str, list[dict[str, Any]]]:
    """Retorna séries temporais diárias de volume e eficiência."""
    cursor.execute("""
        SELECT
            substr(DATA_FIM, 1, 10) AS dia,
            SUM(COALESCE(QT_KG, 0)) AS kg_total,
            SUM(COALESCE(MIN_REAL, 0)) AS min_real,
            SUM(COALESCE(MIN_PREV, 0)) AS min_prev
        FROM filtered_beneficiamento
        WHERE DATA_FIM IS NOT NULL
        GROUP BY dia
        ORDER BY dia
        LIMIT 90
        """)
    volume_diario = []
    eficiencia_diaria = []
    for item in cursor.fetchall():
        item_min_real = float(item["min_real"] or 0.0)
        item_min_prev = float(item["min_prev"] or 0.0)
        volume_diario.append(
            {"date": item["dia"], "kg_total": _round(item["kg_total"])}
        )
        eficiencia_diaria.append(
            {
                "date": item["dia"],
                "eficiencia_tempo_pct": _round(
                    (item_min_prev / item_min_real * 100.0)
                    if item_min_real > 0
                    else 0.0
                ),
            }
        )
    return {
        "volume_diario": volume_diario,
        "eficiencia_diaria": eficiencia_diaria,
    }

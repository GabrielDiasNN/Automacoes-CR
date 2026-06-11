# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
"""Contratos operacionais V1 de Beneficiamento baseados em SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .historico_db import init_db


def _round(value: float | int | None, digits: int = 2) -> float:
    if value is None:
        return 0.0
    return round(float(value), digits)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_strip(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_request_filters(filtros: Mapping[str, Any]) -> dict[str, str]:
    return {
        "dt_inicio": _safe_strip(filtros.get("dt_inicio")),
        "dt_fim": _safe_strip(filtros.get("dt_fim")),
        "maquina": _safe_strip(filtros.get("maquina")),
        "fase": _safe_strip(filtros.get("fase")),
        "turno": _safe_strip(filtros.get("turno")),
        "alternativo": _safe_strip(filtros.get("alternativo")),
        "q": _safe_strip(filtros.get("q")),
        "ob": _safe_strip(filtros.get("ob")),
    }


def _normalize_turno_values(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    turno_id = _safe_strip(payload.get("TURNO_PROD") or payload.get("turno") or payload.get("TURNO"))
    turno_label = _safe_strip(payload.get("TURNO_DESC"))
    if not turno_label and turno_id:
        turno_label = f"TURNO {turno_id}"
    return (turno_id or None, turno_label or None)


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    turno_id, turno_label = _normalize_turno_values(record)
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
    where_clauses = ["1=1"]
    params: list[Any] = []
    normalized = _normalize_request_filters(filtros)

    if dt_inicio:
        where_clauses.append("DATA_FIM >= ?")
        params.append(f"{dt_inicio}T00:00:00")

    if dt_fim:
        dt_fim_bound = (datetime.strptime(dt_fim, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
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


def _build_filtered_dataset(cursor: sqlite3.Cursor, where_sql: str, params: list[Any]) -> None:
    cursor.execute("DROP TABLE IF EXISTS temp.filtered_beneficiamento;")
    cursor.execute(
        f"""
        CREATE TEMP TABLE filtered_beneficiamento AS
        SELECT
            NUMERO_OB,
            SEQ,
            DATA_FIM,
            NOME_MAQUINA,
            CD_DS_FASE,
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
            MIN_REAL,
            MIN_PREV,
            DESVIO_MIN,
            TURNO_ID,
            COALESCE(TURNO_LABEL, 'Indefinido') AS TURNO_LABEL,
            MAQUINA_KEY,
            FASE_KEY,
            CODIGO_KEY,
            DADOS_COMPLETOS
        FROM fato_producao_historica
        WHERE {where_sql}
        """,
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


def _fetch_filter_options(
    cursor: sqlite3.Cursor,
) -> dict[str, list[str]]:
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
        "alternativos": """
            SELECT DISTINCT CODIGO_KEY AS value
            FROM filtered_beneficiamento
            WHERE COALESCE(CODIGO_KEY, '') != ''
            ORDER BY value
            LIMIT 160
        """,
    }
    options: dict[str, list[str]] = {
        "maquinas": [],
        "fases": [],
        "turnos": [],
        "alternativos": [],
    }
    for key, sql in queries.items():
        cursor.execute(sql)
        options[key] = [str(row["value"]) for row in cursor.fetchall() if row["value"]]
    return options


def _build_turnos(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
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
                "eficiencia_tempo_pct": _round((min_prev / min_real * 100.0) if min_real > 0 else 0.0),
                "reprocesso_kg_pct": _round(
                    (float(row["reprocesso_kg"] or 0.0) / kg_total * 100.0) if kg_total > 0 else 0.0
                ),
                "produtividade_kg_h": _round((kg_total * 60.0 / min_real) if min_real > 0 else 0.0),
                "min_real_medio": _round((min_real / fases) if fases > 0 else 0.0),
                "desvio_medio_min": _round(((min_real - min_prev) / fases) if fases > 0 else 0.0),
            }
        )
    return items


def _build_tingimento(cursor: sqlite3.Cursor) -> dict[str, Any]:
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
        "desvio_medio_min": _round(((min_real - min_prev) / fases) if fases > 0 else 0.0),
        "eficiencia_media_pct": _round((min_prev / min_real * 100.0) if min_real > 0 else 0.0),
        "reprocesso_kg_pct": _round(
            (float(row["reprocesso_kg"] or 0.0) / kg_total * 100.0) if kg_total > 0 else 0.0
        ),
        "reprocesso_fases_pct": _round(
            (float(row["reprocesso_fases"] or 0.0) / fases * 100.0) if fases > 0 else 0.0
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
                "eficiencia_media_pct": _round((min_prev_day / min_real_day * 100.0) if min_real_day > 0 else 0.0),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_day * 100.0) if kg_day > 0 else 0.0
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
                "eficiencia_media_pct": _round((min_prev_item / min_real_item * 100.0) if min_real_item > 0 else 0.0),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_item * 100.0) if kg_item > 0 else 0.0
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
                "eficiencia_media_pct": _round((min_prev_item / min_real_item * 100.0) if min_real_item > 0 else 0.0),
                "desvio_medio_min": _round(min_real_item - min_prev_item),
            }
        )

    return {"summary": summary, "series": series, "rankings": {"por_alternativo": por_alternativo, "por_maquina": por_maquina}}


def _build_overview_kpis(cursor: sqlite3.Cursor) -> tuple[int, dict[str, Any]]:
    cursor.execute(
        """
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
        """
    )
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
        "eficiencia_tempo_pct": _round((min_prev / min_real * 100.0) if min_real > 0 else 0.0),
        "reprocesso_kg_pct": _round(
            (reprocesso_kg / kg_total * 100.0)
            if kg_total > 0
            else ((fases_reprocessadas / fases * 100.0) if fases > 0 else 0.0)
        ),
        "desvio_tempo_min": _round(min_real - min_prev),
        "produtividade_kg_h": _round((kg_total * 60.0 / min_real) if min_real > 0 else 0.0),
    }


def _build_gargalos(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cursor.execute(
        """
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
        """
    )
    gargalos = []
    for item in cursor.fetchall():
        item_min_real = float(item["min_real"] or 0.0)
        item_min_prev = float(item["min_prev"] or 0.0)
        item_efic = (item_min_prev / item_min_real * 100.0) if item_min_real > 0 else 0.0
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
    cursor.execute(
        """
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
        """
    )
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
                "eficiencia_tempo_pct": _round((min_prev_item / min_real_item * 100.0) if min_real_item > 0 else 0.0),
                "reprocesso_kg_pct": _round(
                    (float(item["reprocesso_kg"] or 0.0) / kg_item * 100.0) if kg_item > 0 else 0.0
                ),
            }
        )
    return fases_criticas


def _build_produtos(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cursor.execute(
        """
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
        """
    )
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
                    (float(item["reprocesso_kg"] or 0.0) / kg_item * 100.0) if kg_item > 0 else 0.0
                ),
                "produtividade_kg_h": _round((kg_item * 60.0 / min_real_item) if min_real_item > 0 else 0.0),
            }
        )
    return produtos


def _build_overview_series(cursor: sqlite3.Cursor) -> dict[str, list[dict[str, Any]]]:
    cursor.execute(
        """
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
        """
    )
    volume_diario = []
    eficiencia_diaria = []
    for item in cursor.fetchall():
        item_min_real = float(item["min_real"] or 0.0)
        item_min_prev = float(item["min_prev"] or 0.0)
        volume_diario.append({"date": item["dia"], "kg_total": _round(item["kg_total"])})
        eficiencia_diaria.append(
            {
                "date": item["dia"],
                "eficiencia_tempo_pct": _round((item_min_prev / item_min_real * 100.0) if item_min_real > 0 else 0.0),
            }
        )
    return {
        "volume_diario": volume_diario,
        "eficiencia_diaria": eficiencia_diaria,
    }


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
            "findings": [] if fases > 0 else ["Nenhum registro encontrado para o recorte filtrado."],
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


def _summary_from_records(target_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    kg_total = sum(float(item.get("QT_KG") or 0.0) for item in records)
    mt_total = sum(float(item.get("QT_MT") or 0.0) for item in records)
    min_real = sum(float(item.get("MIN_REAL") or 0.0) for item in records)
    min_prev = sum(float(item.get("MIN_PREV") or 0.0) for item in records)
    reprocesso_kg = sum(
        float(item.get("QT_KG") or 0.0) for item in records if int(item.get("REPROCESSO") or 0) == 1
    )
    fases = len(records)
    obs = len({str(item.get("NUMERO_OB") or "").strip() for item in records if item.get("NUMERO_OB")})
    turnos = sorted({item.get("TURNO_DESC") or "Indefinido" for item in records})
    return {
        "target_type": target_type,
        "ob_distintas": obs,
        "fases_concluidas": fases,
        "kg_total": _round(kg_total),
        "mt_total": _round(mt_total),
        "eficiencia_tempo_pct": _round((min_prev / min_real * 100.0) if min_real > 0 else 0.0),
        "reprocesso_kg_pct": _round((reprocesso_kg / kg_total * 100.0) if kg_total > 0 else 0.0),
        "produtividade_kg_h": _round((kg_total * 60.0 / min_real) if min_real > 0 else 0.0),
        "turnos": turnos,
    }


def _build_trace(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        numero_ob = _safe_strip(item.get("NUMERO_OB")) or "Sem OB"
        grouped.setdefault(numero_ob, []).append(item)

    trace: list[dict[str, Any]] = []
    for numero_ob, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda row: (
                str(row.get("DATA_HORA_FIM") or row.get("DATA_FIM") or ""),
                int(row.get("SEQ") or 0),
            ),
        )
        trace.append(
            {
                "ob": numero_ob,
                "fases": [
                    {
                        "seq": int(row.get("SEQ") or 0),
                        "data_fim": row.get("DATA_HORA_FIM") or row.get("DATA_FIM"),
                        "fase": row.get("CD_DS_FASE"),
                        "maquina": _safe_strip(row.get("NOME_MAQUINA")),
                        "turno": row.get("TURNO_DESC") or "Indefinido",
                        "kg": _round(row.get("QT_KG")),
                        "min_real": _round(row.get("MIN_REAL")),
                        "reprocesso": int(row.get("REPROCESSO") or 0),
                    }
                    for row in ordered
                ],
            }
        )
    trace.sort(key=lambda item: item["ob"], reverse=True)
    return trace


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

        cursor.execute(
            f"""
            SELECT DADOS_COMPLETOS
            FROM fato_producao_historica
            WHERE {where_sql}
            ORDER BY DATA_FIM DESC, NUMERO_OB DESC, SEQ ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        records = []
        for row in cursor.fetchall():
            raw = row["DADOS_COMPLETOS"]
            if not raw:
                continue
            try:
                records.append(_normalize_record(json.loads(raw)))
            except json.JSONDecodeError:
                continue

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
        "raw_records": records if include_raw else [],
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
        maquinas.append({
            "maquina": item.get("maquina") or "Sem máquina",
            "kg_total": item.get("kg_total") or 0.0,
            "mt_total": item.get("mt_total") or 0.0,
            "total_fases": item.get("fases_concluidas") or 0,
            "min_real": item.get("desvio_min") or 0.0,
            "min_setup": 0.0,
            "min_processo": item.get("desvio_min") or 0.0,
        })

    produtos = [{
        "reduz": item.get("codigo") or "-",
        "produto": item.get("produto") or "Sem descrição",
        "artigo": item.get("artigo") or "Sem artigo",
        "kg_total": item.get("kg_total") or 0.0,
        "mt_total": item.get("mt_total") or 0.0,
        "taxa_reprocesso": item.get("reprocesso_kg_pct") or 0.0,
        "produtividade_kgh": item.get("produtividade_kg_h") or 0.0,
    } for item in rankings.get("produtos_principais", [])]

    fases = [{
        "fase": item.get("fase") or "Sem fase",
        "kg_total": item.get("kg_total") or 0.0,
        "mt_total": 0.0,
        "total_fases": item.get("fases_concluidas") or 0,
        "reprocesso_percent": item.get("reprocesso_kg_pct") or 0.0,
        "efic_tempo": item.get("eficiencia_tempo_pct") or 0.0,
    } for item in rankings.get("fases_criticas", [])]

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
        "turnos": [{"turno": value, "kg_total": 0.0} for value in filter_options.get("turnos", [])],
        "fases": fases,
        "artigos": [],
        "cores": [],
    }

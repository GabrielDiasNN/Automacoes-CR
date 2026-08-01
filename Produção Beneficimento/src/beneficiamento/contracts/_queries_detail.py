"""Builders SQL específicos do contrato de drill-down histórico do Beneficiamento.

Extraído de ``_queries`` para isolar os builders de detalhe/drill-down
usados exclusivamente pelo contrato de detail (``contracts.detail``).
Consome os utilitários compartilhados de ``_queries_common``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..core import round_or_zero as _round, safe_strip as _safe_strip
from ._queries_common import _DETAIL_TYPED, _normalize_record


def _summary_from_records(
    target_type: str, records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Calcula KPIs agregados a partir de uma lista de registros em memória."""
    kg_total = sum(float(item.get("QT_KG") or 0.0) for item in records)
    mt_total = sum(float(item.get("QT_MT") or 0.0) for item in records)
    min_real = sum(float(item.get("MIN_REAL") or 0.0) for item in records)
    min_prev = sum(float(item.get("MIN_PREV") or 0.0) for item in records)
    reprocesso_kg = sum(
        float(item.get("QT_KG") or 0.0)
        for item in records
        if int(item.get("REPROCESSO") or 0) == 1
    )
    fases = len(records)
    obs = len(
        {
            str(item.get("NUMERO_OB") or "").strip()
            for item in records
            if item.get("NUMERO_OB")
        }
    )
    turnos = sorted({item.get("TURNO_DESC") or "Indefinido" for item in records})
    return {
        "target_type": target_type,
        "ob_distintas": obs,
        "fases_concluidas": fases,
        "kg_total": _round(kg_total),
        "mt_total": _round(mt_total),
        "eficiencia_tempo_pct": _round(
            (min_prev / min_real * 100.0) if min_real > 0 else 0.0
        ),
        "reprocesso_kg_pct": _round(
            (reprocesso_kg / kg_total * 100.0) if kg_total > 0 else 0.0
        ),
        "produtividade_kg_h": _round(
            (kg_total * 60.0 / min_real) if min_real > 0 else 0.0
        ),
        "turnos": turnos,
    }


def _build_trace(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa registros por OB e monta o trace cronológico de fases."""
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
                        "fase": row.get("DESCR_FASE"),
                        "setor": row.get("DESCR_SETOR_INDUST"),
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


def _detail_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    """Converte uma linha tipada em registro, espelhando os rótulos de turno."""
    record = {column: row[column] for column in _DETAIL_TYPED}
    record["TURNO_PROD"] = record.get("TURNO_ID")
    record["TURNO_DESC"] = record.get("TURNO_LABEL") or "Indefinido"
    # `row` é `sqlite3.Row`, não dict: `in row` itera os VALORES, não as chaves.
    # A correção automática do SIM118 inverteria a semântica silenciosamente.
    if "DADOS_COMPLETOS" in row.keys():  # noqa: SIM118
        record["__raw__"] = row["DADOS_COMPLETOS"]
    return record


def _detail_raw_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstrói os payloads originais a partir do blob (apenas em include_raw)."""
    raw_records: list[dict[str, Any]] = []
    for record in records:
        raw = record.get("__raw__")
        if not raw:
            continue
        try:
            raw_records.append(_normalize_record(json.loads(raw)))
        except json.JSONDecodeError:
            continue
    return raw_records

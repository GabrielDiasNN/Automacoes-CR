"""Agregacoes analiticas dos snapshots do Beneficiamento."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements,unused-import,trailing-whitespace,line-too-long

from __future__ import annotations

import statistics
from typing import Any


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def safe_text(value: Any) -> str:
    if value is None:
        return "SEM_VALOR"
    text = str(value).strip()
    return text or "SEM_VALOR"


def first_available_float(record: dict[str, Any], fields: tuple[str, ...]) -> float:
    for field in fields:
        if record.get(field) is not None:
            return to_float(record.get(field))
    return 0.0


def average_or_none(values: list[float], scale: int) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(statistics.fmean(usable), scale)


def attach_share_pct(items: list[dict[str, Any]], total_kg: float) -> None:
    for item in items:
        item["share_kg_pct"] = (
            round((to_float(item.get("kg_total")) / total_kg) * 100, 2)
            if total_kg
            else 0.0
        )


def aggregate_group(
    records: list[dict[str, Any]], key_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for record in records:
        key = tuple(safe_text(record.get(field)) for field in key_fields)
        group = groups.setdefault(
            key,
            {
                "rows": 0,
                "ob_set": set(),
                "maquinas": set(),
                "kg_total": 0.0,
                "mt_total": 0.0,
                "min_prev_total": 0.0,
                "min_real_total": 0.0,
                "carga_prev_grupo_total": 0.0,
                "rendimento_values": [],
                "efic_values": [],
            },
        )
        group["rows"] += 1
        ob_value = safe_text(record.get("NUMERO_OB"))
        if ob_value != "SEM_VALOR":
            group["ob_set"].add(ob_value)
        group["maquinas"].add(safe_text(record.get("NUMERO_MAQUINA")))
        group["kg_total"] += to_float(record.get("QT_KG"))
        group["mt_total"] += to_float(record.get("QT_MT"))
        group["min_prev_total"] += to_float(record.get("MIN_PREV"))
        group["min_real_total"] += to_float(record.get("MIN_REAL"))
        group["carga_prev_grupo_total"] += to_float(record.get("CARGA_PREV_GRUPO"))
        group["rendimento_values"].append(
            first_available_float(record, ("RENDIMENTO_MEDIO", "RENDIMENTO"))
        )
        group["efic_values"].append(
            first_available_float(record, ("EFIC_CARGA_MEDIA", "EFIC_CARGA", "EFIC_PROC_LINHA"))
        )

    summaries: list[dict[str, Any]] = []
    for key, group in groups.items():
        desvio_total = group["min_real_total"] - group["min_prev_total"]
        summary: dict[str, Any] = dict(zip(key_fields, key))
        summary.update(
            {
                "linhas": group["rows"],
                "ob_distintas": len(group["ob_set"]),
                "maquinas_distintas": len(group["maquinas"]),
                "kg_total": round(group["kg_total"], 2),
                "mt_total": round(group["mt_total"], 2),
                "min_prev_total": round(group["min_prev_total"], 2),
                "min_real_total": round(group["min_real_total"], 2),
                "carga_prev_grupo_total": round(group["carga_prev_grupo_total"], 2),
                "desvio_min_total": round(desvio_total, 2),
                "desvio_min_abs_total": round(abs(desvio_total), 2),
                "rendimento_medio_ponderado": average_or_none(group["rendimento_values"], 4),
                "efic_carga_media_ponderada": average_or_none(
                    group["efic_values"], 2
                ),
            }
        )
        summaries.append(summary)

    summaries.sort(key=lambda item: (-item["kg_total"], -item["linhas"], str(item)))
    return summaries


def build_fato_producao(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fato: dict[Any, dict[str, Any]] = {}
    for r in records:
        maq_cod = safe_text(r.get("NUMERO_MAQUINA"))
        maq_nom = safe_text(r.get("DESCR_MAQ") or r.get("NOME_MAQUINA"))
        fase_cod = safe_text(r.get("FASE") or r.get("CD_DS_FASE") or r.get("CD_FASE"))
        fase_nom = safe_text(r.get("DESCR_FASE") or r.get("CD_DS_FASE") or r.get("DESCR_FASE"))
        turno = safe_text(r.get("TURNO_PROD"))
        reduz = safe_text(r.get("REDUZ") or r.get("CODIGO_REDUZIDO"))
        produto = safe_text(r.get("DESCR_ITEM"))
        artigo_cod = safe_text(r.get("ARTIGO"))
        artigo_nom = safe_text(r.get("DESCR_ARTIGO"))
        cor_nom = safe_text(r.get("DESCR_COR"))
        
        key = (maq_cod, maq_nom, fase_cod, fase_nom, turno, reduz, produto, artigo_cod, artigo_nom, cor_nom)
        
        group = fato.setdefault(key, {
            "maq_cod": maq_cod,
            "maq_nom": maq_nom,
            "fase_cod": fase_cod,
            "fase_nom": fase_nom,
            "turno": turno,
            "reduz": reduz,
            "produto": produto,
            "artigo_cod": artigo_cod,
            "artigo_nom": artigo_nom,
            "cor_nom": cor_nom,
            "kg": 0.0,
            "mt": 0.0,
            "linhas": 0,
            "efic_carga_soma": 0.0,
            "rendimento_soma": 0.0,
        })
        
        # Obter volumes de forma flexível considerando as chaves do snapshot detalhado/anual
        group["kg"] += to_float(r.get("QUANT_PROD") or r.get("QT_KG") or r.get("QUILOS") or r.get("kg_total"))
        group["mt"] += to_float(r.get("METROS") or r.get("QT_MT") or r.get("mt_total"))
        group["linhas"] += 1
        group["efic_carga_soma"] += to_float(r.get("EFIC_CARGA") or r.get("efic_carga_media_ponderada"))
        group["rendimento_soma"] += to_float(r.get("RENDIMENTO") or r.get("rendimento_medio_ponderado"))
        
    result = []
    for key, g in fato.items():
        g["kg"] = round(g["kg"], 2)
        g["mt"] = round(g["mt"], 2)
        g["efic_carga_media"] = round(g["efic_carga_soma"] / g["linhas"], 2) if g["linhas"] else 0.0
        g["rendimento_medio"] = round(g["rendimento_soma"] / g["linhas"], 4) if g["linhas"] else 0.0
        del g["efic_carga_soma"]
        del g["rendimento_soma"]
        result.append(g)
        
    result.sort(key=lambda x: -x["kg"])
    return result


def build_analytics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = len(records)
    total_kg = sum(to_float(record.get("QT_KG")) for record in records)
    total_mt = sum(to_float(record.get("QT_MT")) for record in records)
    total_carga_prev = sum(to_float(record.get("CARGA_PREV_GRUPO")) for record in records)
    total_min_prev = sum(to_float(record.get("MIN_PREV")) for record in records)
    total_min_real = sum(to_float(record.get("MIN_REAL")) for record in records)
    rendimento_values = [
        first_available_float(record, ("RENDIMENTO_MEDIO", "RENDIMENTO"))
        for record in records
    ]
    efic_values = [
        first_available_float(record, ("EFIC_CARGA_MEDIA", "EFIC_CARGA", "EFIC_PROC_LINHA"))
        for record in records
    ]

    per_machine = aggregate_group(records, ("NUMERO_MAQUINA", "NOME_MAQUINA"))
    per_phase = aggregate_group(records, ("CD_DS_FASE",))
    per_turno = aggregate_group(records, ("TURNO_PROD", "TURNO_DESC"))
    attach_share_pct(per_machine, total_kg)
    attach_share_pct(per_phase, total_kg)
    attach_share_pct(per_turno, total_kg)

    def top_n(items: list[dict[str, Any]], field: str, limit: int = 5) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: to_float(item.get(field)), reverse=True)[:limit]

    return {
        "geral": {
            "linhas": total_rows,
            "ob_distintas": len(
                {
                    safe_text(record.get("NUMERO_OB"))
                    for record in records
                    if safe_text(record.get("NUMERO_OB")) != "SEM_VALOR"
                }
            ),
            "maquinas_distintas": len(
                {safe_text(record.get("NUMERO_MAQUINA")) for record in records}
            ),
            "fases_distintas": len({safe_text(record.get("CD_DS_FASE")) for record in records}),
            "turnos_distintos": len({safe_text(record.get("TURNO_PROD")) for record in records}),
            "kg_total": round(total_kg, 2),
            "mt_total": round(total_mt, 2),
            "carga_prev_grupo_total": round(total_carga_prev, 2),
            "min_prev_total": round(total_min_prev, 2),
            "min_real_total": round(total_min_real, 2),
            "desvio_min_total": round(total_min_real - total_min_prev, 2),
            "desvio_min_abs_total": round(abs(total_min_real - total_min_prev), 2),
            "rendimento_medio_ponderado": average_or_none(rendimento_values, 4),
            "efic_carga_media_ponderada": average_or_none(efic_values, 2),
        },
        "por_maquina": per_machine,
        "por_fase": per_phase,
        "por_turno": per_turno,
        "destaques": {
            "maquinas_por_kg": top_n(per_machine, "kg_total"),
            "fases_por_kg": top_n(per_phase, "kg_total"),
            "turnos_por_kg": top_n(per_turno, "kg_total"),
            "maquinas_por_desvio_min_abs": top_n(per_machine, "desvio_min_abs_total"),
            "fases_por_desvio_min_abs": top_n(per_phase, "desvio_min_abs_total"),
        },
        "fato_producao": build_fato_producao(records),
    }

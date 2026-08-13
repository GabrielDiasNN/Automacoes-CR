# {
#   "version": "2.5.0",
#   "description": "Le obs_result.json + config.json, aplica threshold por fase, gera message.txt"
# }
import json
import os
import sys
from datetime import datetime
from typing import Any

# import-error e wrong-import-position: import de lib/python via sys.path.insert()
# dinamico abaixo, que o pylint nao resolve em tempo de analise estatica.
# pylint: disable=broad-exception-caught, import-error, wrong-import-position
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
from obp_config import (
    FaseConfig,
    _filter_obs,
    _load_config,
    fmt_dias,
    fmt_kg,
    group_obs_by_phase,
    normalize_fase,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "obs_result.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")


def _build_ob_lines(ob: dict[str, Any]) -> list[str]:
    kanban = ob.get("PLACA_KANBAN") or "S/Kanban"
    if kanban == "SEM KANBAN":
        kanban = "S/Kanban"
    alternativo = ob.get("ALTERNATIVO") or ""
    produto = (ob.get("DS_ITEM") or "—").title()
    dias = fmt_dias(ob["_dias_float"])
    urgente = ob["_dias_float"] >= float(ob["_threshold"]) * 2
    urgencia = " ⚠️" if urgente else ""
    num_ob = ob.get("NUMERO_OB", "—")
    pecas = ob.get("QT_PECAS") or 0
    kilos_raw = ob.get("QT_KILOS_REAL") or 0
    prod_line = f"  {alternativo} · {produto}" if alternativo else f"  {produto}"
    return [
        f"  *OB {num_ob}* · {kanban} · *{dias} dias*{urgencia}",
        prod_line,
        f"  {pecas} pcs · {fmt_kg(kilos_raw)} kg",
        "",
    ]


def _build_fase_section(obs_fase: list[dict[str, Any]]) -> tuple[list[str], float]:
    fase_norm = normalize_fase(obs_fase[0].get("FASE_ATUAL") or "Indefinida")
    count = len(obs_fase)
    lines = ["", f"🔸 *{fase_norm}* — {count} {'OB' if count == 1 else 'OBs'}", ""]
    kg = 0.0
    for ob in obs_fase:
        lines.extend(_build_ob_lines(ob))
        try:
            kg += float(ob.get("QT_KILOS_REAL") or 0)
        except (TypeError, ValueError):
            pass
    return lines, kg


def _group_and_sort(
    filtradas: list[dict[str, Any]],
    max_obs: int,
    phase_order: list[int],
) -> list[tuple[int, list[dict[str, Any]]]]:
    grupos_ordenados = group_obs_by_phase(filtradas, phase_order)
    for _, obs_fase in grupos_ordenados:
        del obs_fase[max_obs:]
    return grupos_ordenados


def build_message(
    obs: list[dict[str, Any]],
    fases_monitoradas: dict[str, FaseConfig],
    max_obs: int,
    phase_filters: dict[str, Any] | None = None,
    phase_order: list[int] | None = None,
) -> str:
    phase_filters = phase_filters or {}
    phase_order = phase_order or []
    data_hora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    filtradas = _filter_obs(obs, fases_monitoradas, phase_filters)

    if not filtradas:
        return (
            f"✅ *OBs Paradas na Fase*\n📅 {data_hora}\n\n"
            "Nenhuma OB excedeu o threshold configurado neste momento."
        )

    grupos_ordenados = _group_and_sort(filtradas, max_obs, phase_order)
    lines = [
        "🔴 *OBs Paradas na Fase*",
        f"📅 {data_hora}",
        "──────────────────────────",
    ]
    kg_total = 0.0
    for _, obs_fase in grupos_ordenados:
        fase_lines, kg = _build_fase_section(obs_fase)
        lines.extend(fase_lines)
        kg_total += kg

    n_fases = len(grupos_ordenados)
    exibidas_total = sum(len(obs_fase) for _, obs_fase in grupos_ordenados)
    lines.append("──────────────────────────")
    lines.append(
        f"📊 *{len(filtradas)} OBs críticas* · {n_fases} "
        f"{'fase' if n_fases == 1 else 'fases'} · {fmt_kg(kg_total)} kg"
        + (
            f" _(exibindo {exibidas_total} de {len(filtradas)}, até {max_obs} por fase)_"
            if exibidas_total < len(filtradas)
            else ""
        )
    )
    return "\n".join(lines)


def main() -> None:
    if not os.path.exists(RESULT_FILE):
        print(
            "[ERROR] obs_result.json nao encontrado. Execute extract_obs.py primeiro.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(RESULT_FILE, "r", encoding="utf-8") as f:
        result = json.load(f)

    fases_monitoradas, max_obs, phase_filters, phase_order = _load_config(CONFIG_FILE)
    obs = result.get("rows", [])
    message = build_message(obs, fases_monitoradas, max_obs, phase_filters, phase_order)

    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        f.write(message)

    print(f"[OK] message.txt gerado ({len(message)} chars).")
    sys.exit(0)


if __name__ == "__main__":
    main()

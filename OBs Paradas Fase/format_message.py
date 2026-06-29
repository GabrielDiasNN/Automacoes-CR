# pylint: disable=broad-exception-caught
# {
#   "version": "2.1.0",
#   "description": "Le obs_result.json + config.json, aplica threshold por fase, gera message.txt"
# }
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE  = os.path.join(SCRIPT_DIR, "obs_result.json")
CONFIG_FILE  = os.path.join(SCRIPT_DIR, "config.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")

DEFAULT_KEYWORDS: dict[str, float] = {
    "REVIS":       3,
    "AMACIANTE":   0.25,
    "HIDRO":       1,
    "SECADOR":     1,
    "ABRIDOR":     1,
    "RAMA":        1,
    "FELPAGEM":    1,
    "CONFERENCIA": 0.5,
    "COMPACTA":    1,
    "BRILHO":      1,
    "CQ":          1,
    "EXPEDICAO":   1,
}
DEFAULT_MAX_OBS = 10

_PREFIX_RE = re.compile(r"^[A-Z0-9]{2,5}-")


def normalize_fase(fase: str) -> str:
    """Remove prefixo Oracle (ex: 'RMC-', 'EXP-') e aplica Title Case."""
    return _PREFIX_RE.sub("", fase.strip()).title()


def get_threshold(fase: str, thresholds: dict[str, float]) -> float | None:
    """Retorna o threshold para a fase (matching por keyword), ou None se não monitorada."""
    fase_upper = fase.upper()
    for keyword, dias in thresholds.items():
        if keyword.upper() in fase_upper:
            return dias
    return None


def fmt_dias(dias: Any) -> str:
    try:
        return f"{float(dias):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(dias)


def fmt_kg(kilos: Any) -> str:
    try:
        return f"{float(kilos):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(kilos)


def _phase_sort_key(fase_norm: str, ordem: list[str]) -> tuple[int, str]:
    upper = fase_norm.upper()
    for i, keyword in enumerate(ordem):
        if keyword.upper() in upper:
            return (i, fase_norm)
    return (len(ordem), fase_norm)


def _filter_obs(
    obs: list[dict[str, Any]],
    thresholds: dict[str, float],
    phase_filters: dict[str, Any],
) -> list[dict[str, Any]]:
    filtradas: list[dict[str, Any]] = []
    for ob in obs:
        fase = ob.get("FASE_ATUAL") or ""
        threshold = get_threshold(fase, thresholds)
        if threshold is None:
            continue
        try:
            dias = float(ob.get("DIAS_PARADO") or 0)
        except (TypeError, ValueError):
            continue
        if dias < threshold:
            continue
        threshold = _apply_phase_filter(ob, fase.upper(), phase_filters, threshold)
        if threshold is None:
            continue
        filtradas.append({**ob, "_threshold": threshold, "_dias_float": dias})
    return filtradas


def _apply_phase_filter(
    ob: dict[str, Any],
    fase_upper: str,
    phase_filters: dict[str, Any],
    threshold: float,
) -> float | None:
    for keyword, regras in phase_filters.items():
        if keyword.upper() not in fase_upper:
            continue
        for campo, valor_esperado in regras.items():
            raw = ob.get(campo)
            try:
                val: Any = int(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                val = raw
            if val != valor_esperado:
                return None
        break
    return threshold


def _build_ob_lines(ob: dict[str, Any]) -> list[str]:
    kanban = ob.get("PLACA_KANBAN") or "S/Kanban"
    if kanban == "SEM KANBAN":
        kanban = "S/Kanban"
    alternativo = ob.get("ALTERNATIVO") or ""
    produto     = (ob.get("DS_ITEM") or "—").title()
    dias        = fmt_dias(ob["_dias_float"])
    urgente     = ob["_dias_float"] >= float(ob["_threshold"]) * 2
    urgencia    = " ⚠️" if urgente else ""
    num_ob      = ob.get("NUMERO_OB", "—")
    pecas       = ob.get("QT_PECAS") or 0
    kilos_raw   = ob.get("QT_KILOS_REAL") or 0
    prod_line   = f"  {alternativo} · {produto}" if alternativo else f"  {produto}"
    return [
        f"  *OB {num_ob}* · {kanban} · *{dias} dias*{urgencia}",
        prod_line,
        f"  {pecas} pcs · {fmt_kg(kilos_raw)} kg",
        "",
    ]


def _build_fase_section(fase_norm: str, obs_fase: list[dict[str, Any]]) -> tuple[list[str], float]:
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
    phase_order: list[str],
) -> list[tuple[str, list[dict[str, Any]]]]:
    filtradas.sort(key=lambda x: x["_dias_float"], reverse=True)
    exibidas: list[dict[str, Any]] = filtradas[:max_obs]
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ob in exibidas:
        grupos[normalize_fase(ob.get("FASE_ATUAL") or "Indefinida")].append(ob)
    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda kv: (
            _phase_sort_key(kv[0], phase_order)[0],
            -max(o["_dias_float"] for o in kv[1]),
        ),
    )
    for _, obs_fase in grupos_ordenados:
        obs_fase.sort(key=lambda o: o["_dias_float"], reverse=True)
    return grupos_ordenados


def build_message(
    obs: list[dict[str, Any]],
    thresholds: dict[str, float],
    max_obs: int,
    phase_filters: dict[str, Any] | None = None,
    phase_order: list[str] | None = None,
) -> str:
    phase_filters = phase_filters or {}
    phase_order   = phase_order or []
    data_hora     = datetime.now().strftime("%d/%m/%Y às %H:%M")
    filtradas = _filter_obs(obs, thresholds, phase_filters)

    if not filtradas:
        return (
            f"✅ *OBs Paradas na Fase*\n📅 {data_hora}\n\n"
            "Nenhuma OB excedeu o threshold configurado neste momento."
        )

    grupos_ordenados = _group_and_sort(filtradas, max_obs, phase_order)
    lines = ["🔴 *OBs Paradas na Fase*", f"📅 {data_hora}", "──────────────────────────"]
    kg_total = 0.0
    for fase_norm, obs_fase in grupos_ordenados:
        fase_lines, kg = _build_fase_section(fase_norm, obs_fase)
        lines.extend(fase_lines)
        kg_total += kg

    n_fases = len(grupos_ordenados)
    lines.append("──────────────────────────")
    lines.append(
        f"📊 *{len(filtradas)} OBs críticas* · {n_fases} "
        f"{'fase' if n_fases == 1 else 'fases'} · {fmt_kg(kg_total)} kg"
        + (f" _(top {max_obs} de {len(filtradas)})_" if len(filtradas) > max_obs else "")
    )
    return "\n".join(lines)


def _load_config() -> tuple[dict[str, float], int, dict[str, Any], list[str]]:
    thresholds: dict[str, float] = DEFAULT_KEYWORDS.copy()
    max_obs    = DEFAULT_MAX_OBS
    phase_filters: dict[str, Any] = {}
    phase_order: list[str] = []
    if not os.path.exists(CONFIG_FILE):
        return thresholds, max_obs, phase_filters, phase_order
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        thresholds    = {k.upper(): v for k, v in cfg.get("threshold_por_fase", {}).items()}
        max_obs       = int(cfg.get("max_obs_por_mensagem", DEFAULT_MAX_OBS))
        phase_filters = {k.upper(): v for k, v in cfg.get("filtros_por_fase", {}).items()}
        phase_order   = [k.upper() for k in cfg.get("ordem_fases", [])]
    except Exception as e:
        print(f"[WARN] Falha ao ler config.json, usando defaults: {e}", file=sys.stderr)
    return thresholds, max_obs, phase_filters, phase_order


def main() -> None:
    if not os.path.exists(RESULT_FILE):
        print("[ERROR] obs_result.json nao encontrado. Execute extract_obs.py primeiro.", file=sys.stderr)
        sys.exit(1)

    with open(RESULT_FILE, "r", encoding="utf-8") as f:
        result = json.load(f)

    thresholds, max_obs, phase_filters, phase_order = _load_config()
    obs = result.get("rows", [])
    message = build_message(obs, thresholds, max_obs, phase_filters, phase_order)

    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        f.write(message)

    print(f"[OK] message.txt gerado ({len(message)} chars).")
    sys.exit(0)


if __name__ == "__main__":
    main()

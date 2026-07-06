# pylint: disable=broad-exception-caught
# {
#   "version": "2.5.0",
#   "description": "Le obs_result.json + config.json, aplica threshold por fase, gera message.txt"
# }
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE  = os.path.join(SCRIPT_DIR, "obs_result.json")
CONFIG_FILE  = os.path.join(SCRIPT_DIR, "config.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")

def _join_responsavel(numeros: list[Any]) -> str:
    return " @".join(str(x).strip() for x in numeros if str(x).strip())


def _resolve_contato(contato: Any) -> str:
    """Resolve uma entrada de 'contatos': objeto {nome, numero}, lista desses, ou string legada."""
    if isinstance(contato, list):
        return _join_responsavel(
            [c.get("numero", "") if isinstance(c, dict) else c for c in contato]
        )
    if isinstance(contato, dict):
        return str(contato.get("numero", "")).strip()
    return str(contato).strip()


@dataclass
class FaseConfig:
    descricao: str
    threshold_dias: float
    responsavel: str
    ativo: bool = True


# Contatos reais (nome/numero) nunca ficam no codigo-fonte nem no config.json —
# vivem só no .env local (nao versionado), lido via os.environ pelo run.ps1/Lib-Config.psm1.
# Sem .env configurado, o fallback abaixo fica vazio e a mensagem sai sem mencao.
_LIDER_1_TURNO         = os.environ.get("OBP_CONTATO_LIDER_1_TURNO", "")
_LIDER_RESERVA_1_TURNO = os.environ.get("OBP_CONTATO_LIDER_RESERVA_1_TURNO", "")
_LIDER_2_TURNO         = os.environ.get("OBP_CONTATO_LIDER_2_TURNO", "")
_LIDER_RESERVA_2_TURNO = os.environ.get("OBP_CONTATO_LIDER_RESERVA_2_TURNO", "")
_LIDER_3_TURNO         = os.environ.get("OBP_CONTATO_LIDER_3_TURNO", "")
_LIDER_RESERVA_3_TURNO = os.environ.get("OBP_CONTATO_LIDER_RESERVA_3_TURNO", "")
_EQUIPE_QUALIDADE = _join_responsavel(
    os.environ.get("OBP_CONTATO_EQUIPE_CQ", "").split(",")
)

DEFAULT_FASES_MONITORADAS: dict[str, FaseConfig] = {
    "20":  FaseConfig("RMC-REVISÃO MALHA CRUA", 3, _LIDER_3_TURNO),
    "25":  FaseConfig("CDP-CONFERENCIA DE PESO", 0.5, _EQUIPE_QUALIDADE, ativo=False),
    "26":  FaseConfig("IVF-INVERSÃO P/FELPAGEM", 1, _LIDER_3_TURNO),
    "45":  FaseConfig("CDC-CONFERENCIA DE COR", 0.5, _LIDER_RESERVA_3_TURNO),
    "46":  FaseConfig("PPA-PREPARAÇÃO AMACIANTE", 0.25, _LIDER_1_TURNO),
    "50":  FaseConfig("HID-HIDRO UMIDO", 1, _LIDER_1_TURNO),
    "55":  FaseConfig("HIS-HIDRO SECO", 1, _LIDER_1_TURNO),
    "60":  FaseConfig("SEC-SECADOR", 1, _LIDER_1_TURNO),
    "65":  FaseConfig("FEL-FELPAGEM", 1, _LIDER_RESERVA_1_TURNO),
    "70":  FaseConfig("CLB-CALANDRA DE BRILHO", 1, _LIDER_RESERVA_1_TURNO),
    "80":  FaseConfig("CLC-CALANDRA DE COMPACTACAO", 1, _LIDER_RESERVA_1_TURNO),
    "90":  FaseConfig("ABR-ABRIDOR", 1, _LIDER_2_TURNO),
    "100": FaseConfig("RAU-RAMAR UMIDO", 1, _LIDER_2_TURNO),
    "110": FaseConfig("RAS-RAMAR SECO", 1, _LIDER_2_TURNO),
    "150": FaseConfig("EXP-EXPEDICAO ACABADO", 1, _LIDER_RESERVA_2_TURNO),
    "160": FaseConfig("CDQ-CONTROLE DE QUALIDADE", 1, _EQUIPE_QUALIDADE),
    "165": FaseConfig("CDF-CONFERÊNCIA DE FELPA", 1, _EQUIPE_QUALIDADE),
}
DEFAULT_PHASE_ORDER: list[int] = [20, 46, 50, 55, 60, 90, 100, 110, 26, 65, 25, 45, 80, 70, 160, 165, 150]
DEFAULT_MAX_OBS = 10

_PREFIX_RE = re.compile(r"^[A-Z0-9]{2,5}-")


def normalize_fase(fase: str) -> str:
    """Remove prefixo Oracle (ex: 'RMC-', 'EXP-') e aplica Title Case."""
    return _PREFIX_RE.sub("", fase.strip()).title()


def _codigo_fase_key(ob: dict[str, Any]) -> str | None:
    """Normaliza CODIGO_FASE (int/float/str vindos do Oracle) para a chave usada em fases_monitoradas."""
    raw = ob.get("CODIGO_FASE")
    if raw is None:
        return None
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return None


def get_fase_config(
    codigo_key: str | None, fases_monitoradas: dict[str, FaseConfig]
) -> FaseConfig | None:
    if codigo_key is None:
        return None
    return fases_monitoradas.get(codigo_key)


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


def _phase_sort_key(codigo_fase: int, ordem: list[int]) -> int:
    return ordem.index(codigo_fase) if codigo_fase in ordem else len(ordem)


def _apply_phase_filter(
    ob: dict[str, Any], codigo_key: str | None, phase_filters: dict[str, Any]
) -> bool:
    """Retorna True se o OB deve ser ignorado (filtro não satisfeito)."""
    regras = phase_filters.get(codigo_key) if codigo_key is not None else None
    if not regras:
        return False
    for campo, valor_esperado in regras.items():
        raw = ob.get(campo)
        try:
            val: Any = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            val = raw
        if val != valor_esperado:
            return True
    return False


def _filter_obs(
    obs: list[dict[str, Any]],
    fases_monitoradas: dict[str, FaseConfig],
    phase_filters: dict[str, Any],
) -> list[dict[str, Any]]:
    filtradas: list[dict[str, Any]] = []
    for ob in obs:
        codigo_key = _codigo_fase_key(ob)
        cfg = get_fase_config(codigo_key, fases_monitoradas)
        if cfg is None or not cfg.ativo:
            continue
        try:
            dias = float(ob.get("DIAS_PARADO") or 0)
        except (TypeError, ValueError):
            continue
        if dias < cfg.threshold_dias:
            continue
        if _apply_phase_filter(ob, codigo_key, phase_filters):
            continue
        filtradas.append({**ob, "_threshold": cfg.threshold_dias, "_dias_float": dias})
    return filtradas


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
    filtradas.sort(key=lambda x: x["_dias_float"], reverse=True)
    exibidas: list[dict[str, Any]] = filtradas[:max_obs]
    grupos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ob in exibidas:
        codigo = int(float(ob.get("CODIGO_FASE") or 0))
        grupos[codigo].append(ob)
    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda kv: (
            _phase_sort_key(kv[0], phase_order),
            -max(o["_dias_float"] for o in kv[1]),
        ),
    )
    for _, obs_fase in grupos_ordenados:
        obs_fase.sort(key=lambda o: o["_dias_float"], reverse=True)
    return grupos_ordenados


def build_message(
    obs: list[dict[str, Any]],
    fases_monitoradas: dict[str, FaseConfig],
    max_obs: int,
    phase_filters: dict[str, Any] | None = None,
    phase_order: list[int] | None = None,
) -> str:
    phase_filters = phase_filters or {}
    phase_order   = phase_order or []
    data_hora     = datetime.now().strftime("%d/%m/%Y às %H:%M")
    filtradas = _filter_obs(obs, fases_monitoradas, phase_filters)

    if not filtradas:
        return (
            f"✅ *OBs Paradas na Fase*\n📅 {data_hora}\n\n"
            "Nenhuma OB excedeu o threshold configurado neste momento."
        )

    grupos_ordenados = _group_and_sort(filtradas, max_obs, phase_order)
    lines = ["🔴 *OBs Paradas na Fase*", f"📅 {data_hora}", "──────────────────────────"]
    kg_total = 0.0
    for _, obs_fase in grupos_ordenados:
        fase_lines, kg = _build_fase_section(obs_fase)
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


def _load_contatos_from_env() -> dict[str, str]:
    """Mesmas chaves de referencia de 'responsavel' em fases_monitoradas, valor lido do .env."""
    return {
        "lider_1_turno": _LIDER_1_TURNO,
        "lider_reserva_1_turno": _LIDER_RESERVA_1_TURNO,
        "lider_2_turno": _LIDER_2_TURNO,
        "lider_reserva_2_turno": _LIDER_RESERVA_2_TURNO,
        "lider_3_turno": _LIDER_3_TURNO,
        "lider_reserva_3_turno": _LIDER_RESERVA_3_TURNO,
        "equipe_cq": _EQUIPE_QUALIDADE,
    }


def _load_config() -> tuple[dict[str, FaseConfig], int, dict[str, Any], list[int]]:
    fases_monitoradas = dict(DEFAULT_FASES_MONITORADAS)
    max_obs = DEFAULT_MAX_OBS
    phase_filters: dict[str, Any] = {}
    phase_order = list(DEFAULT_PHASE_ORDER)
    if not os.path.exists(CONFIG_FILE):
        return fases_monitoradas, max_obs, phase_filters, phase_order
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        max_obs = int(cfg.get("max_obs_por_mensagem", DEFAULT_MAX_OBS))
        phase_filters = {
            str(k): v for k, v in cfg.get("filtros_por_codigo_fase", {}).items()
        }
        phase_order = [int(c) for c in cfg.get("ordem_codigos_fase", DEFAULT_PHASE_ORDER)]
        contatos = _load_contatos_from_env()
        fases_cfg = cfg.get("fases_monitoradas")
        if fases_cfg:
            fases_monitoradas = {}
            for codigo, dados in fases_cfg.items():
                resp_ref = dados.get("responsavel", "")
                responsavel = (
                    contatos[resp_ref]
                    if isinstance(resp_ref, str) and resp_ref in contatos
                    else _resolve_contato(resp_ref)
                )
                fases_monitoradas[str(codigo)] = FaseConfig(
                    descricao=str(dados.get("descricao", "")),
                    threshold_dias=float(dados.get("threshold_dias", 1)),
                    responsavel=responsavel,
                    ativo=bool(dados.get("ativo", True)),
                )
    except Exception as e:
        print(f"[WARN] Falha ao ler config.json, usando defaults: {e}", file=sys.stderr)
    return fases_monitoradas, max_obs, phase_filters, phase_order


def main() -> None:
    if not os.path.exists(RESULT_FILE):
        print("[ERROR] obs_result.json nao encontrado. Execute extract_obs.py primeiro.", file=sys.stderr)
        sys.exit(1)

    with open(RESULT_FILE, "r", encoding="utf-8") as f:
        result = json.load(f)

    fases_monitoradas, max_obs, phase_filters, phase_order = _load_config()
    obs = result.get("rows", [])
    message = build_message(obs, fases_monitoradas, max_obs, phase_filters, phase_order)

    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        f.write(message)

    print(f"[OK] message.txt gerado ({len(message)} chars).")
    sys.exit(0)


if __name__ == "__main__":
    main()

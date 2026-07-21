# pylint: disable=broad-exception-caught
# {
#   "version": "1.7.0",
#   "description": "Le obs_result.json + config.json, gera images PNG por fase e phase_cards.json"
# }
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE     = os.path.join(SCRIPT_DIR, "obs_result.json")
CONFIG_FILE     = os.path.join(SCRIPT_DIR, "config.json")
IMAGES_DIR      = os.path.join(SCRIPT_DIR, "images")
MANIFEST_FILE   = os.path.join(SCRIPT_DIR, "phase_cards.json")
SEEN_STATE_FILE = os.path.join(SCRIPT_DIR, "obs_seen_state.json")

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
_LIDER_CQ              = os.environ.get("OBP_CONTATO_LIDER_CQ", "")
_EQUIPE_QUALIDADE = _join_responsavel(
    os.environ.get("OBP_CONTATO_EQUIPE_CQ", "").split(",")
)

DEFAULT_FASES_MONITORADAS: dict[str, FaseConfig] = {
    "20":  FaseConfig("RMC-REVISÃO MALHA CRUA", 1, _LIDER_3_TURNO),
    "25":  FaseConfig("CDP-CONFERENCIA DE PESO", 0.5, _EQUIPE_QUALIDADE, ativo=False),
    "26":  FaseConfig("IVF-INVERSÃO P/FELPAGEM", 1, _LIDER_3_TURNO),
    "45":  FaseConfig("CDC-CONFERENCIA DE COR", 0.1, _LIDER_RESERVA_3_TURNO),
    "46":  FaseConfig("PPA-PREPARAÇÃO AMACIANTE", 1, _LIDER_1_TURNO),
    "47":  FaseConfig("UMM-UMEDECIMENTO DE MALHA", 0.5, _LIDER_RESERVA_3_TURNO),
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
    "160": FaseConfig("CDQ-CONTROLE DE QUALIDADE", 1, _LIDER_CQ),
    "165": FaseConfig("CDF-CONFERÊNCIA DE FELPA", 0.1, _EQUIPE_QUALIDADE),
}
DEFAULT_PHASE_ORDER: list[int] = [20, 46, 47, 50, 55, 60, 90, 100, 110, 26, 65, 25, 45, 80, 70, 160, 165, 150]
DEFAULT_MAX_OBS = 10
MAX_OBS_PER_PHASE = 15   # limite por fase para evitar cards com altura > 5000px (WhatsApp)
MAX_CARD_HEIGHT   = 4800

_PREFIX_RE = re.compile(r"^[A-Z0-9]{2,5}-")

# ── Cores do card ─────────────────────────────────────────────────────────────
BG_COLOR      = (30,  30,  46)
HEADER_COLOR  = (245, 158, 11)
HEADER_TEXT   = (30,  30,  46)
TEXT_MAIN     = (236, 234, 228)
TEXT_DIM      = (160, 160, 180)
ACCENT_URGENT = (239,  68,  68)
DIVIDER_COLOR = (60,  60,  80)
FOOTER_BG     = (20,  20,  36)
DOT_NEW       = (34, 197,  94)
DOT_PERM      = (110, 110, 130)

CARD_W        = 800
PAD           = 28
HEADER_H      = 72
OB_ROW_H      = 42
FOOTER_H      = 52
DOT_RADIUS    = 4
DOT_GAP       = 8
URGENCY_ICON_SIZE = 7
URGENCY_ICON_W    = 20


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    windir = os.environ.get("WINDIR", "C:/Windows")
    font_name = "arialbd.ttf" if bold else "arial.ttf"
    candidates = [
        os.path.join(windir, "Fonts", font_name),
        os.path.join(windir, "Fonts", "Arial.ttf"),
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()  # type: ignore[return-value]


def normalize_fase(fase: str) -> str:
    clean = _PREFIX_RE.sub("", fase.strip()).upper().strip()

    mapeamentos = {
        "EXPEDICAO ACABADO": "Expedição Acabado",
        "RAMAR UMIDO": "Ramar Úmido",
        "CALANDRA DE COMPACTACAO": "Calandra de Compactação",
        "CONFERENCIA": "Conferência",
        "REVISAO MALHA CRUA": "Revisão Malha Crua",
        "REVISAO": "Revisão",
        "PRODUCAO": "Produção",
        "COMPACTACAO": "Compactação",
    }

    if clean in mapeamentos:
        return mapeamentos[clean]

    return clean.title()


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


def fmt_entrega(dt_entrega: Any) -> str:
    if not dt_entrega:
        return "—"
    try:
        return datetime.fromisoformat(str(dt_entrega)).strftime("%d/%m")
    except ValueError:
        return "—"


def _phase_sort_key(codigo_fase: int, ordem: list[int]) -> int:
    return ordem.index(codigo_fase) if codigo_fase in ordem else len(ordem)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Quebra texto em linhas que cabem em max_width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


# ── Helpers de desenho ────────────────────────────────────────────────────────

def _draw_header(draw: ImageDraw.ImageDraw, phase_display: str, n_obs: int, font: ImageFont.FreeTypeFont) -> None:
    draw.rectangle([(0, 0), (CARD_W, HEADER_H)], fill=HEADER_COLOR)
    label = f"  {phase_display}  —  {n_obs} {'OB' if n_obs == 1 else 'OBs'} paradas"
    draw.text((PAD, (HEADER_H - 22) // 2), label, font=font, fill=HEADER_TEXT)


def _draw_urgency_icon(draw: ImageDraw.ImageDraw, x: float, y_center: float) -> None:
    """Desenha um triangulo de alerta com primitivas do PIL.

    Evita depender do glifo Unicode "⚠", ausente na fonte usada para o texto
    (renderiza como retangulo vazio). Mesma logica da bolinha nova/permanente.
    """
    size = URGENCY_ICON_SIZE
    top = (x + size, y_center - size)
    left = (x, y_center + size * 0.8)
    right = (x + size * 2, y_center + size * 0.8)
    draw.polygon([top, left, right], fill=ACCENT_URGENT)
    draw.rectangle(
        [x + size - 1, y_center - size * 0.55, x + size + 1, y_center + size * 0.15],
        fill=BG_COLOR,
    )
    draw.ellipse(
        [x + size - 1, y_center + size * 0.35, x + size + 1, y_center + size * 0.55],
        fill=BG_COLOR,
    )


def _ob_display_data(ob: dict[str, Any], threshold: float) -> tuple[float, bool, str, str, str, str, str]:
    """Extrai (dias, urgente, kanban, alternativo, produto, cliente, entrega) de um OB."""
    dias    = float(ob.get("_dias_float", 0))
    thr     = float(ob.get("_threshold", threshold))
    urgente = dias >= thr * 2
    kanban  = ob.get("PLACA_KANBAN") or "S/Kanban"
    if kanban == "SEM KANBAN":
        kanban = "S/Kanban"
    cliente_raw = ob.get("NOME_CLIENTE") or "—"
    cliente = cliente_raw if len(cliente_raw) <= 40 else cliente_raw[:39] + "…"
    entrega = fmt_entrega(ob.get("DT_ENTREGA"))
    return dias, urgente, kanban, ob.get("ALTERNATIVO") or "", (ob.get("DS_ITEM") or "—").upper(), cliente, entrega


def _load_seen_obs(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(str(n) for n in data.get("numero_obs", []))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_seen_obs(path: str, numero_obs: set[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"numero_obs": sorted(numero_obs), "updated_at": datetime.now().isoformat()},
            f,
            ensure_ascii=False,
            indent=2,
        )


def _draw_ob_row(  # pylint: disable=too-many-locals
    draw: ImageDraw.ImageDraw,
    ob: dict[str, Any],
    i: int,
    threshold: float,
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> None:
    y0 = HEADER_H + i * OB_ROW_H
    if i > 0:
        draw.line([(PAD, y0), (CARD_W - PAD, y0)], fill=DIVIDER_COLOR, width=1)

    dias, urgente, kanban, alternativo, produto, cliente, entrega = _ob_display_data(ob, threshold)
    dias_color = ACCENT_URGENT if urgente else TEXT_MAIN
    dot_color = DOT_NEW if ob.get("_is_new") else DOT_PERM
    text_x0 = PAD + DOT_RADIUS * 2 + DOT_GAP

    # 1. Preparar partes de texto (linha 1: OB/kanban/dias + pcs/kg + produto completo)
    part1 = f"OB {ob.get('NUMERO_OB', '—')}  ·  {kanban}  ·  {fmt_dias(dias)} dias"
    part_meta = f"  ·  {ob.get('QT_PECAS') or 0} pcs  ·  {fmt_kg(ob.get('QT_KILOS_REAL') or 0)} kg"
    icon_w = URGENCY_ICON_W if urgente else 0

    # 2. Medir larguras para calcular o espaço disponível para o produto
    w1 = draw.textbbox((0, 0), part1, font=fonts["ob"])[2]
    w_meta = draw.textbbox((0, 0), part_meta, font=fonts["detalhe"])[2]

    w_max = CARD_W - PAD - text_x0
    w_prod_max = w_max - w1 - icon_w - w_meta - 10

    # 3. Formatar texto do produto e truncar se exceder o limite
    prod_text = f"  ·  {alternativo} · {produto}" if alternativo else f"  ·  {produto}"
    w3 = draw.textbbox((0, 0), prod_text, font=fonts["produto"])[2]
    if w3 > w_prod_max:
        base_sep = f"  ·  {alternativo} · " if alternativo else "  ·  "
        prod_name = produto
        prod_text = ""
        while len(prod_name) > 0:
            prod_name = prod_name[:-1]
            test_text = base_sep + prod_name + "..."
            test_w = draw.textbbox((0, 0), test_text, font=fonts["produto"])[2]
            if test_w <= w_prod_max:
                prod_text = test_text
                break

    # 4. Desenhar linha 1 (mesma posicao/tamanho de sempre)
    x: float = text_x0
    y1 = y0 + 12

    dot_cy = y0 + OB_ROW_H // 2
    draw.ellipse(
        [(PAD, dot_cy - DOT_RADIUS), (PAD + DOT_RADIUS * 2, dot_cy + DOT_RADIUS)],
        fill=dot_color,
    )

    draw.text((x, y1), part1, font=fonts["ob"], fill=dias_color)
    x += w1

    if urgente:
        _draw_urgency_icon(draw, x + 4, y1 + 7)
        x += icon_w

    draw.text((x, y1), prod_text, font=fonts["produto"], fill=TEXT_MAIN)
    w3_real = draw.textbbox((0, 0), prod_text, font=fonts["produto"])[2]
    x += w3_real

    draw.text((x, y1), part_meta, font=fonts["detalhe"], fill=TEXT_DIM)

    # 5. Desenhar sublinha (linha 2: cliente + entrega, fonte menor, encaixada
    # no espaco ocioso que ja existe dentro dos mesmos OB_ROW_H px da linha 1)
    y2 = y0 + OB_ROW_H - 13
    sub_text = f"{cliente}  ·  Entrega: {entrega}"
    draw.text((text_x0, y2), sub_text, font=fonts["secundaria"], fill=TEXT_DIM)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    obs_fase: list[dict[str, Any]],
    threshold: float,
    n_obs: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    footer_y = HEADER_H + n_obs * OB_ROW_H
    draw.rectangle([(0, footer_y), (CARD_W, footer_y + FOOTER_H)], fill=FOOTER_BG)
    obs_distintas = len({o.get("NUMERO_OB") for o in obs_fase})
    pcs_total = sum(int(float(o.get("QT_PECAS") or 0)) for o in obs_fase)
    kg_total = sum(float(o.get("QT_KILOS_REAL") or 0) for o in obs_fase)
    agora    = datetime.now().strftime("%d/%m/%Y às %H:%M")
    ob_label = "OB" if obs_distintas == 1 else "OBs"
    text     = (
        f"  {obs_distintas} {ob_label}  ·  {pcs_total} pcs  ·  {fmt_kg(kg_total)} kg parados  ·  "
        f"limite ≥ {fmt_dias(threshold)} dia  ·  {agora}"
    )
    draw.text((PAD, footer_y + (FOOTER_H - 13) // 2), text, font=font, fill=TEXT_DIM)


def build_phase_image(
    phase_display: str,
    obs_fase: list[dict[str, Any]],
    threshold: float,
    out_path: str,
) -> None:
    n_obs  = len(obs_fase)
    img_h  = HEADER_H + OB_ROW_H * n_obs + FOOTER_H + PAD
    img    = Image.new("RGB", (CARD_W, img_h), BG_COLOR)
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    fonts: dict[str, ImageFont.FreeTypeFont] = {
        "header":     _load_font(22, bold=True),
        "ob":         _load_font(13, bold=True),
        "produto":    _load_font(12, bold=False),
        "detalhe":    _load_font(12, bold=False),
        "secundaria": _load_font(10, bold=False),
        "footer":     _load_font(13, bold=False),
    }

    _draw_header(draw, phase_display, n_obs, fonts["header"])
    for i, ob in enumerate(obs_fase):
        _draw_ob_row(draw, ob, i, threshold, fonts)
    _draw_footer(draw, obs_fase, threshold, n_obs, fonts["footer"])

    img.save(out_path, "PNG", optimize=True)


# ── Helpers de main ───────────────────────────────────────────────────────────

def _load_contatos_from_env() -> dict[str, str]:
    """Mesmas chaves de referencia de 'responsavel' em fases_monitoradas, valor lido do .env."""
    return {
        "lider_1_turno": _LIDER_1_TURNO,
        "lider_reserva_1_turno": _LIDER_RESERVA_1_TURNO,
        "lider_2_turno": _LIDER_2_TURNO,
        "lider_reserva_2_turno": _LIDER_RESERVA_2_TURNO,
        "lider_3_turno": _LIDER_3_TURNO,
        "lider_reserva_3_turno": _LIDER_RESERVA_3_TURNO,
        "lider_cq": _LIDER_CQ,
        "equipe_cq": _EQUIPE_QUALIDADE,
    }


def _load_config(
    config_file: str,
) -> tuple[dict[str, FaseConfig], int, dict[str, Any], list[int]]:
    fases_monitoradas = dict(DEFAULT_FASES_MONITORADAS)
    max_obs = DEFAULT_MAX_OBS
    phase_filters: dict[str, Any] = {}
    phase_order = list(DEFAULT_PHASE_ORDER)
    if not os.path.exists(config_file):
        return fases_monitoradas, max_obs, phase_filters, phase_order
    try:
        with open(config_file, "r", encoding="utf-8") as f:
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
        # config.json existe mas nao pode ser interpretado: falhar explicitamente em vez de
        # degradar silenciosamente para defaults hardcoded, que podem estar desatualizados
        # em relacao ao config de producao (thresholds, fases ativas).
        print(
            f"[ERROR] config.json existe mas falhou ao processar: {e}. "
            "Corrija o arquivo antes de reexecutar; defaults hardcoded nao serao usados como fallback silencioso.",
            file=sys.stderr,
        )
        sys.exit(1)
    return fases_monitoradas, max_obs, phase_filters, phase_order


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
    obs_all: list[dict[str, Any]],
    fases_monitoradas: dict[str, FaseConfig],
    phase_filters: dict[str, Any],
) -> list[dict[str, Any]]:
    filtradas: list[dict[str, Any]] = []
    for ob in obs_all:
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


def _group_obs(
    filtradas: list[dict[str, Any]],
    max_obs: int,
    phase_order: list[int],
) -> list[tuple[int, list[dict[str, Any]]]]:
    # Agrupa por codigo de fase antes de limitar, para não excluir fases inteiras por
    # saturação global. max_obs controla o teto por fase (não o total), garantindo que
    # todas as fases com OBs acima do threshold apareçam no relatório.
    filtradas.sort(key=lambda x: x["_dias_float"], reverse=True)

    grupos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ob in filtradas:
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
        # Limita por fase; também aplica teto de altura de card para WhatsApp (~5000px)
        max_por_fase = min(max_obs, MAX_OBS_PER_PHASE,
                          max(1, (MAX_CARD_HEIGHT - HEADER_H - FOOTER_H - PAD) // OB_ROW_H))
        del obs_fase[max_por_fase:]
    return grupos_ordenados


def _build_card_entry(
    codigo_fase: int,
    obs_fase: list[dict[str, Any]],
    images_dir: str,
    script_dir: str,
    fases_monitoradas: dict[str, FaseConfig],
) -> dict[str, Any]:
    fase_norm  = normalize_fase(obs_fase[0].get("FASE_ATUAL") or "Indefinida")
    phase_key  = re.sub(r"[^A-Z0-9]+", "_", fase_norm.upper()).strip("_")
    thr_val    = float(obs_fase[0]["_threshold"])
    max_dias   = max(o["_dias_float"] for o in obs_fase)
    kg_total   = sum(float(o.get("QT_KILOS_REAL") or 0) for o in obs_fase)
    n          = len(obs_fase)

    image_path = os.path.join(images_dir, f"{phase_key}.png")
    build_phase_image(fase_norm, obs_fase, thr_val, image_path)

    caption = (
        f"\U0001f538 *{fase_norm}* — {n} {'OB' if n == 1 else 'OBs'} paradas\n"
        f"Limite: ≥ {fmt_dias(thr_val)} {'dia' if thr_val == 1 else 'dias'}  |  "
        f"Máx: {fmt_dias(max_dias)} dias\n"
        f"\U0001f4ca {fmt_kg(kg_total)} kg  ·  {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
    )

    cfg = fases_monitoradas.get(str(codigo_fase))
    if cfg and cfg.responsavel:
        caption += f"\n\nResponsável: @{cfg.responsavel}"

    rel_image = os.path.relpath(image_path, script_dir).replace("\\", "/")
    print(f"[OK] {fase_norm}: {n} OBs → {rel_image}")
    return {
        "phase_key":     phase_key,
        "phase_display": fase_norm,
        "image_path":    rel_image,
        "caption":       caption,
    }


def main() -> None:
    if not os.path.exists(RESULT_FILE):
        print("[ERROR] obs_result.json nao encontrado. Execute extract_obs.py primeiro.", file=sys.stderr)
        sys.exit(1)

    with open(RESULT_FILE, "r", encoding="utf-8") as f:
        result = json.load(f)

    fases_monitoradas, max_obs, phase_filters, phase_order = _load_config(CONFIG_FILE)
    obs_all   = result.get("rows", [])
    filtradas = _filter_obs(obs_all, fases_monitoradas, phase_filters)

    if not filtradas:
        print("[OK] Nenhuma OB excedeu o limite configurado — nenhum card gerado.")
        sys.exit(2)

    seen = _load_seen_obs(SEEN_STATE_FILE)
    for ob in filtradas:
        ob["_is_new"] = str(ob.get("NUMERO_OB")) not in seen

    grupos_ordenados = _group_obs(filtradas, max_obs, phase_order)

    os.makedirs(IMAGES_DIR, exist_ok=True)
    manifest = [
        _build_card_entry(codigo_fase, obs_fase, IMAGES_DIR, SCRIPT_DIR, fases_monitoradas)
        for codigo_fase, obs_fase in grupos_ordenados
    ]

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    _save_seen_obs(SEEN_STATE_FILE, {str(o.get("NUMERO_OB")) for o in filtradas})

    print(f"[OK] phase_cards.json gerado ({len(manifest)} fases).")
    sys.exit(0)


if __name__ == "__main__":
    main()

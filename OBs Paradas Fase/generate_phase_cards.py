# pylint: disable=broad-exception-caught
# {
#   "version": "1.2.0",
#   "description": "Le obs_result.json + config.json, gera images PNG por fase e phase_cards.json"
# }
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE   = os.path.join(SCRIPT_DIR, "obs_result.json")
CONFIG_FILE   = os.path.join(SCRIPT_DIR, "config.json")
IMAGES_DIR    = os.path.join(SCRIPT_DIR, "images")
MANIFEST_FILE = os.path.join(SCRIPT_DIR, "phase_cards.json")

DEFAULT_KEYWORDS = {
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

# ── Cores do card ─────────────────────────────────────────────────────────────
BG_COLOR      = (30,  30,  46)
HEADER_COLOR  = (245, 158, 11)
HEADER_TEXT   = (30,  30,  46)
TEXT_MAIN     = (236, 234, 228)
TEXT_DIM      = (160, 160, 180)
ACCENT_URGENT = (239,  68,  68)
ACCENT_WARN   = (245, 158,  11)
DIVIDER_COLOR = (60,  60,  80)
FOOTER_BG     = (20,  20,  36)

CARD_W        = 800
PAD           = 28
HEADER_H      = 72
OB_ROW_H      = 84
FOOTER_H      = 52


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
        except Exception:
            continue
    return ImageFont.load_default()  # type: ignore[return-value]


def normalize_fase(fase: str) -> str:
    return _PREFIX_RE.sub("", fase.strip()).title()


def get_threshold(fase: str, thresholds: dict[str, float]) -> float | None:
    fase_upper = fase.upper()
    for kw, dias in thresholds.items():
        if kw.upper() in fase_upper:
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
    for i, kw in enumerate(ordem):
        if kw.upper() in upper:
            return (i, fase_norm)
    return (len(ordem), fase_norm)


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


def _ob_display_data(ob: dict[str, Any], threshold: float) -> tuple[float, bool, str, str, str]:
    """Extrai (dias, urgente, kanban, alternativo, produto) de um OB."""
    dias    = float(ob.get("_dias_float", 0))
    thr     = float(ob.get("_threshold", threshold))
    urgente = dias >= thr * 2
    kanban  = ob.get("PLACA_KANBAN") or "S/Kanban"
    if kanban == "SEM KANBAN":
        kanban = "S/Kanban"
    return dias, urgente, kanban, ob.get("ALTERNATIVO") or "", (ob.get("DS_ITEM") or "—").title()


def _draw_ob_row(draw: ImageDraw.ImageDraw, ob: dict[str, Any], i: int, threshold: float, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    y0 = HEADER_H + i * OB_ROW_H
    if i > 0:
        draw.line([(PAD, y0), (CARD_W - PAD, y0)], fill=DIVIDER_COLOR, width=1)

    dias, urgente, kanban, alternativo, produto = _ob_display_data(ob, threshold)
    dias_color = ACCENT_URGENT if urgente else TEXT_MAIN
    ob_label = f"OB {ob.get('NUMERO_OB', '—')}  ·  {kanban}  ·  {fmt_dias(dias)} dias"
    draw.text((PAD, y0 + 10), ob_label, font=fonts["ob"], fill=dias_color)
    if urgente:
        label_w = draw.textbbox((0, 0), ob_label, font=fonts["ob"])[2]
        draw.text((PAD + label_w + 6, y0 + 10), "⚠", font=fonts["ob"], fill=ACCENT_WARN)
    prod_lines = _wrap_text(
        f"{alternativo} · {produto}" if alternativo else produto,
        fonts["produto"], CARD_W - PAD * 2, draw,
    )
    draw.text((PAD, y0 + 35), prod_lines[0], font=fonts["produto"], fill=TEXT_MAIN)
    draw.text(
        (PAD, y0 + 58),
        f"{ob.get('QT_PECAS') or 0} pcs  ·  {fmt_kg(ob.get('QT_KILOS_REAL') or 0)} kg",
        font=fonts["detalhe"], fill=TEXT_DIM,
    )


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    obs_fase: list[dict[str, Any]],
    threshold: float,
    n_obs: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    footer_y = HEADER_H + n_obs * OB_ROW_H
    draw.rectangle([(0, footer_y), (CARD_W, footer_y + FOOTER_H)], fill=FOOTER_BG)
    kg_total = sum(float(o.get("QT_KILOS_REAL") or 0) for o in obs_fase)
    agora    = datetime.now().strftime("%d/%m/%Y às %H:%M")
    text     = f"  {fmt_kg(kg_total)} kg parados  ·  limite ≥ {fmt_dias(threshold)} dia  ·  {agora}"
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
        "header":  _load_font(22, bold=True),
        "ob":      _load_font(17, bold=True),
        "produto": _load_font(15, bold=False),
        "detalhe": _load_font(14, bold=False),
        "footer":  _load_font(13, bold=False),
    }

    _draw_header(draw, phase_display, n_obs, fonts["header"])
    for i, ob in enumerate(obs_fase):
        _draw_ob_row(draw, ob, i, threshold, fonts)
    _draw_footer(draw, obs_fase, threshold, n_obs, fonts["footer"])

    img.save(out_path, "PNG", optimize=True)


# ── Helpers de main ───────────────────────────────────────────────────────────

def _load_config(config_file: str) -> tuple[dict[str, float], int, dict[str, Any], list[str]]:
    thresholds: dict[str, float] = DEFAULT_KEYWORDS.copy()
    max_obs    = DEFAULT_MAX_OBS
    phase_filters: dict[str, Any] = {}
    phase_order: list[str] = []
    if not os.path.exists(config_file):
        return thresholds, max_obs, phase_filters, phase_order
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        thresholds    = {k.upper(): v for k, v in cfg.get("threshold_por_fase", {}).items()}
        max_obs       = int(cfg.get("max_obs_por_mensagem", DEFAULT_MAX_OBS))
        phase_filters = {k.upper(): v for k, v in cfg.get("filtros_por_fase", {}).items()}
        phase_order   = [k.upper() for k in cfg.get("ordem_fases", [])]
    except Exception as e:
        print(f"[WARN] Falha ao ler config.json, usando defaults: {e}", file=sys.stderr)
    return thresholds, max_obs, phase_filters, phase_order


def _apply_phase_filter(ob: dict[str, Any], fase_upper: str, phase_filters: dict[str, Any]) -> bool:
    """Retorna True se o OB deve ser ignorado (filtro não satisfeito)."""
    for kw, regras in phase_filters.items():
        if kw.upper() not in fase_upper:
            continue
        for campo, valor_esperado in regras.items():
            raw = ob.get(campo)
            try:
                val: Any = int(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                val = raw
            if val != valor_esperado:
                return True
        break
    return False


def _filter_obs(
    obs_all: list[dict[str, Any]],
    thresholds: dict[str, float],
    phase_filters: dict[str, Any],
) -> list[dict[str, Any]]:
    filtradas: list[dict[str, Any]] = []
    for ob in obs_all:
        fase      = ob.get("FASE_ATUAL") or ""
        threshold = get_threshold(fase, thresholds)
        if threshold is None:
            continue
        try:
            dias = float(ob.get("DIAS_PARADO") or 0)
        except (TypeError, ValueError):
            continue
        if dias < threshold:
            continue
        if _apply_phase_filter(ob, fase.upper(), phase_filters):
            continue
        filtradas.append({**ob, "_threshold": threshold, "_dias_float": dias})
    return filtradas


def _group_obs(
    filtradas: list[dict[str, Any]],
    max_obs: int,
    phase_order: list[str],
) -> list[tuple[str, list[dict[str, Any]]]]:
    filtradas.sort(key=lambda x: x["_dias_float"], reverse=True)
    exibidas: list[dict[str, Any]] = filtradas[:max_obs]

    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ob in exibidas:
        fase_norm = normalize_fase(ob.get("FASE_ATUAL") or "Indefinida")
        grupos[fase_norm].append(ob)

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


def _build_card_entry(
    fase_norm: str,
    obs_fase: list[dict[str, Any]],
    images_dir: str,
    script_dir: str,
) -> dict[str, Any]:
    phase_key  = re.sub(r"[^A-Z0-9]+", "_", fase_norm.upper()).strip("_")
    thr_val    = float(obs_fase[0]["_threshold"])
    max_dias   = max(o["_dias_float"] for o in obs_fase)
    kg_total   = sum(float(o.get("QT_KILOS_REAL") or 0) for o in obs_fase)
    n          = len(obs_fase)
    agora      = datetime.now().strftime("%d/%m/%Y às %H:%M")

    image_path = os.path.join(images_dir, f"{phase_key}.png")
    build_phase_image(fase_norm, obs_fase, thr_val, image_path)

    caption = (
        f"\U0001f538 *{fase_norm}* — {n} {'OB' if n == 1 else 'OBs'} paradas\n"
        f"Limite: ≥ {fmt_dias(thr_val)} {'dia' if thr_val == 1 else 'dias'}  |  "
        f"Máx: {fmt_dias(max_dias)} dias\n"
        f"\U0001f4ca {fmt_kg(kg_total)} kg  ·  {agora}"
    )
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

    thresholds, max_obs, phase_filters, phase_order = _load_config(CONFIG_FILE)
    obs_all   = result.get("rows", [])
    filtradas = _filter_obs(obs_all, thresholds, phase_filters)

    if not filtradas:
        print("[OK] Nenhuma OB excedeu o limite configurado — nenhum card gerado.")
        sys.exit(2)

    grupos_ordenados = _group_obs(filtradas, max_obs, phase_order)

    os.makedirs(IMAGES_DIR, exist_ok=True)
    manifest = [
        _build_card_entry(fase_norm, obs_fase, IMAGES_DIR, SCRIPT_DIR)
        for fase_norm, obs_fase in grupos_ordenados
    ]

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[OK] phase_cards.json gerado ({len(manifest)} fases).")
    sys.exit(0)


if __name__ == "__main__":
    main()

import json
import os
import re
import sys
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# import-error e wrong-import-position: import de lib/python via sys.path.insert()
# dinamico abaixo, que o pylint nao resolve em tempo de analise estatica.
# pylint: disable=broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "1.7.0",
#   "description": "Le obs_result.json + config.json, gera images PNG por fase e phase_cards.json"
# }
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
# FaseConfig, fmt_dias, fmt_kg, normalize_fase, _load_config, _filter_obs e
# group_obs_by_phase sao usados diretamente abaixo. get_fase_config,
# _codigo_fase_key, _load_contatos_from_env e _resolve_contato nao tem chamada
# local neste arquivo: sao importados apenas para ficarem acessiveis como
# atributos do modulo, pois Orchestrator/tests/test_obs_paradas_fase.py carrega
# este arquivo dinamicamente via importlib e os acessa como module.<nome> — sem
# o import ficariam ausentes.
from obp_config import (  # pylint: disable=unused-import  # noqa: F401
    FaseConfig,
    _codigo_fase_key,
    _filter_obs,
    _load_config,
    _load_contatos_from_env,
    _resolve_contato,
    fmt_dias,
    fmt_kg,
    get_fase_config,
    group_obs_by_phase,
    normalize_fase,
)

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "obs_result.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")
MANIFEST_FILE = os.path.join(SCRIPT_DIR, "phase_cards.json")
SEEN_STATE_FILE = os.path.join(SCRIPT_DIR, "obs_seen_state.json")

MAX_OBS_PER_PHASE = (
    15  # limite por fase para evitar cards com altura > 5000px (WhatsApp)
)
MAX_CARD_HEIGHT = 4800

# ── Cores do card ─────────────────────────────────────────────────────────────
BG_COLOR = (30, 30, 46)
HEADER_COLOR = (245, 158, 11)
HEADER_TEXT = (30, 30, 46)
TEXT_MAIN = (236, 234, 228)
TEXT_DIM = (160, 160, 180)
ACCENT_URGENT = (239, 68, 68)
DIVIDER_COLOR = (60, 60, 80)
FOOTER_BG = (20, 20, 36)
DOT_NEW = (34, 197, 94)
DOT_PERM = (110, 110, 130)

CARD_W = 800
PAD = 28
HEADER_H = 72
OB_ROW_H = 42
FOOTER_H = 52
DOT_RADIUS = 4
DOT_GAP = 8
URGENCY_ICON_SIZE = 7
URGENCY_ICON_W = 20


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
            # Pillow não publica stubs tipados para truetype: a chamada é untyped
            # e devolve Any. A anotação explícita mantém o contrato de retorno sob
            # mypy --strict sem afrouxar o resto do módulo.
            font: ImageFont.FreeTypeFont = ImageFont.truetype(path, size)
            return font
        except OSError:
            continue
    return ImageFont.load_default()  # type: ignore[return-value]


def fmt_entrega(dt_entrega: Any) -> str:
    if not dt_entrega:
        return "—"
    try:
        return datetime.fromisoformat(str(dt_entrega)).strftime("%d/%m")
    except ValueError:
        return "—"


def _wrap_text(
    text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw
) -> list[str]:
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


def _draw_header(
    draw: ImageDraw.ImageDraw,
    phase_display: str,
    n_obs: int,
    font: ImageFont.FreeTypeFont,
) -> None:
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


def _ob_display_data(
    ob: dict[str, Any], threshold: float
) -> tuple[float, bool, str, str, str, str, str]:
    """Extrai (dias, urgente, kanban, alternativo, produto, cliente, entrega) de um OB."""
    dias = float(ob.get("_dias_float", 0))
    thr = float(ob.get("_threshold", threshold))
    urgente = dias >= thr * 2
    kanban = ob.get("PLACA_KANBAN") or "S/Kanban"
    if kanban == "SEM KANBAN":
        kanban = "S/Kanban"
    cliente_raw = ob.get("NOME_CLIENTE") or "—"
    cliente = cliente_raw if len(cliente_raw) <= 40 else cliente_raw[:39] + "…"
    entrega = fmt_entrega(ob.get("DT_ENTREGA"))
    return (
        dias,
        urgente,
        kanban,
        ob.get("ALTERNATIVO") or "",
        (ob.get("DS_ITEM") or "—").upper(),
        cliente,
        entrega,
    )


def _load_seen_obs(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {str(n) for n in data.get("numero_obs", [])}
    except (OSError, json.JSONDecodeError):
        return set()


def _save_seen_obs(path: str, numero_obs: set[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "numero_obs": sorted(numero_obs),
                "updated_at": datetime.now().isoformat(),
            },
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

    dias, urgente, kanban, alternativo, produto, cliente, entrega = _ob_display_data(
        ob, threshold
    )
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
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    ob_label = "OB" if obs_distintas == 1 else "OBs"
    text = (
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
    n_obs = len(obs_fase)
    img_h = HEADER_H + OB_ROW_H * n_obs + FOOTER_H + PAD
    img = Image.new("RGB", (CARD_W, img_h), BG_COLOR)
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
    fonts: dict[str, ImageFont.FreeTypeFont] = {
        "header": _load_font(22, bold=True),
        "ob": _load_font(13, bold=True),
        "produto": _load_font(12, bold=False),
        "detalhe": _load_font(12, bold=False),
        "secundaria": _load_font(10, bold=False),
        "footer": _load_font(13, bold=False),
    }

    _draw_header(draw, phase_display, n_obs, fonts["header"])
    for i, ob in enumerate(obs_fase):
        _draw_ob_row(draw, ob, i, threshold, fonts)
    _draw_footer(draw, obs_fase, threshold, n_obs, fonts["footer"])

    img.save(out_path, "PNG", optimize=True)


# ── Helpers de main ───────────────────────────────────────────────────────────


def _group_obs(
    filtradas: list[dict[str, Any]],
    max_obs: int,
    phase_order: list[int],
) -> list[tuple[int, list[dict[str, Any]]]]:
    # max_obs controla o teto por fase (não o total), garantindo que todas as fases
    # com OBs acima do threshold apareçam no relatório — mesmo conjunto de fases que
    # format_message.py, via group_obs_by_phase() (fonte única em lib/python).
    grupos_ordenados = group_obs_by_phase(filtradas, phase_order)
    for _, obs_fase in grupos_ordenados:
        # Também aplica teto de altura de card para WhatsApp (~5000px)
        max_por_fase = min(
            max_obs,
            MAX_OBS_PER_PHASE,
            max(1, (MAX_CARD_HEIGHT - HEADER_H - FOOTER_H - PAD) // OB_ROW_H),
        )
        del obs_fase[max_por_fase:]
    return grupos_ordenados


def _build_card_entry(
    codigo_fase: int,
    obs_fase: list[dict[str, Any]],
    images_dir: str,
    script_dir: str,
    fases_monitoradas: dict[str, FaseConfig],
) -> dict[str, Any]:
    fase_norm = normalize_fase(obs_fase[0].get("FASE_ATUAL") or "Indefinida")
    phase_key = re.sub(r"[^A-Z0-9]+", "_", fase_norm.upper()).strip("_")
    thr_val = float(obs_fase[0]["_threshold"])
    max_dias = max(o["_dias_float"] for o in obs_fase)
    kg_total = sum(float(o.get("QT_KILOS_REAL") or 0) for o in obs_fase)
    n = len(obs_fase)

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
        "phase_key": phase_key,
        "phase_display": fase_norm,
        "image_path": rel_image,
        "caption": caption,
    }


def main() -> None:
    if not os.path.exists(RESULT_FILE):
        print(
            "[ERROR] obs_result.json nao encontrado. Execute extract_obs.py primeiro.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(RESULT_FILE, encoding="utf-8") as f:
        result = json.load(f)

    fases_monitoradas, max_obs, phase_filters, phase_order = _load_config(CONFIG_FILE)
    obs_all = result.get("rows", [])
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
        _build_card_entry(
            codigo_fase, obs_fase, IMAGES_DIR, SCRIPT_DIR, fases_monitoradas
        )
        for codigo_fase, obs_fase in grupos_ordenados
    ]

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    _save_seen_obs(SEEN_STATE_FILE, {str(o.get("NUMERO_OB")) for o in filtradas})

    print(f"[OK] phase_cards.json gerado ({len(manifest)} fases).")
    sys.exit(0)


if __name__ == "__main__":
    main()

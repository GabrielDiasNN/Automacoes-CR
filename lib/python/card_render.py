# {
#   "version": "1.0.0",
#   "description": "Utilitarios compartilhados de renderizacao Pillow, sanitizacao e orquestracao de cards"
# }
"""Utilitarios compartilhados de renderizacao Pillow e I/O para cards PNG e legendas."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from card_pagination import (
    DEFAULT_MAX_MESSAGE_CHARS,
    ArtifactTargets,
    PaginationConfig,
    build_paginated_artifacts,
)
from PIL import Image, ImageDraw, ImageFont

PayloadCaptionFn = Callable[
    [dict[str, Any], tuple[int, int] | None, int | None],
    str,
]
PayloadImageFn = Callable[
    [dict[str, Any], str, tuple[int, int] | None, int | None],
    None,
]

BG_COLOR = (30, 30, 46)
HEADER_TEXT = (15, 23, 42)
TEXT_MAIN = (236, 234, 228)
TEXT_DIM = (160, 160, 180)
DIVIDER_COLOR = (60, 60, 80)
FOOTER_BG = (20, 20, 36)

CARD_W = 860
PAD = 28
HEADER_H = 72
OB_ROW_H = 54
SUMMARY_ROW_H = 40
FOOTER_H = 50
DOT_RADIUS = 5
DOT_GAP = 10
COL_GAP = 16
MAX_CARD_ROWS = 85

FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont


@dataclass(frozen=True)
class FormatMainConfig:
    """Parametros de execucao da CLI compartilhada de cards e manifestos."""

    result_file: str
    targets: ArtifactTargets
    pagination: PaginationConfig
    render_caption: PayloadCaptionFn
    render_image: PayloadImageFn
    log_fn: Callable[[str, str, str], None]


def load_font(size: int, bold: bool = False) -> FontType:
    """Carrega fonte TrueType Windows/Linux com fallback proporcional."""
    windir = os.environ.get("WINDIR", "C:/Windows")
    candidates = (
        [
            os.path.join(windir, "Fonts", "arialbd.ttf"),
            "DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            os.path.join(windir, "Fonts", "arial.ttf"),
            os.path.join(windir, "Fonts", "Arial.ttf"),
            "DejaVuSans.ttf",
        ]
    )
    for path in candidates:
        try:
            font: ImageFont.FreeTypeFont = ImageFont.truetype(path, size)
            return font
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def sanitize_text(valor: Any, default: str = "—") -> str:
    """Normaliza campo textual para legenda e card, removendo quebras e aspas duplas."""
    if valor is None:
        return default
    texto = " ".join(str(valor).split()).replace('"', "'")
    return texto or default


def coerce_nonneg_int(valor: Any) -> int:
    """Converte valor numerico para inteiro nao negativo com fallback 0."""
    if isinstance(valor, bool) or valor is None:
        return 0
    if isinstance(valor, int):
        return max(valor, 0)
    texto = str(valor).strip()
    if texto.isascii() and texto.isdigit():
        return int(texto)
    try:
        return max(int(float(texto)), 0)
    except (TypeError, ValueError):
        return 0


def fmt_entrega(valor: Any) -> str:
    """DT_ENTREGA chega em isoformat (serialize_rows); exibe dd/mm/aaaa ou '—'."""
    if valor is None:
        return "—"
    texto = str(valor).strip()
    if not texto:
        return "—"
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y")
    except ValueError:
        return "—"


def truncate_message(
    titulo: str,
    linhas: list[str],
    *,
    max_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
) -> str:
    """Limita legenda ao teto de caracteres sem quebrar linhas no meio."""
    selecionadas: list[str] = []
    for idx, linha in enumerate(linhas):
        restantes = len(linhas) - idx - 1
        rodape = (
            f"\n… e mais {restantes} OB(s) (consulte os logs)" if restantes > 0 else ""
        )
        candidato = f"{titulo}\n\n" + "\n".join([*selecionadas, linha]) + f"{rodape}\n"
        if len(candidato) <= max_chars or not selecionadas:
            selecionadas.append(linha)
        else:
            break

    restantes = len(linhas) - len(selecionadas)
    rodape = f"\n… e mais {restantes} OB(s) (consulte os logs)" if restantes > 0 else ""
    resumo = f"{titulo}\n\n" + "\n".join(selecionadas) + f"{rodape}\n"
    if len(resumo) > max_chars:
        resumo = resumo[: max_chars - 2].rstrip() + "…\n"
    return resumo.replace('"', "'")


def text_width(draw: ImageDraw.ImageDraw, text: str, font: FontType) -> int:
    """Mede a largura em pixels de um texto renderizado na fonte dada."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0])


def center_text_y(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontType,
    box_y: int,
    box_h: int,
) -> int:
    """Calcula a coordenada Y para centralizar texto verticalmente em uma faixa."""
    if not text:
        return box_y
    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]
    return int(box_y + (box_h - text_h) / 2 - bbox[1])


def truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontType,
    max_width: int,
) -> str:
    """Trunca texto visual com reticencias para caber em `max_width` pixels."""
    if max_width <= 0 or not text:
        return ""
    if text_width(draw, text, font) <= max_width:
        return text
    atual = text[:240]
    while len(atual) > 1:
        atual = atual[:-1]
        candidato = atual.rstrip() + "…"
        if text_width(draw, candidato, font) <= max_width:
            return candidato
    return ""


def fit_prefixed_detail(
    draw: ImageDraw.ImageDraw,
    prefix: str,
    content: str,
    font: FontType,
    max_width: int,
) -> str:
    """Ajusta `<prefix><content>` sem deixar apenas prefixo + reticências."""
    if max_width <= 0 or not content:
        return ""
    completo = prefix + content
    if text_width(draw, completo, font) <= max_width:
        return completo
    fitted = truncate_text(draw, completo, font, max_width)
    if not fitted or len(fitted.removesuffix("…").rstrip()) <= len(prefix.rstrip()):
        return ""
    return fitted


def draw_summary_banner(
    draw: ImageDraw.ImageDraw,
    y0: int,
    omitted: int,
    font: FontType,
) -> None:
    """Desenha faixa de resumo quando ha linhas omitidas pelo limite visual."""
    draw.line([(PAD, y0), (CARD_W - PAD, y0)], fill=DIVIDER_COLOR, width=1)
    aviso = truncate_text(
        draw,
        f"… e mais {omitted} OB(s) omitidas do card (limite visual de {MAX_CARD_ROWS} linhas)",
        font,
        CARD_W - 2 * PAD,
    )
    if aviso:
        draw.text(
            (PAD, center_text_y(draw, aviso, font, y0, SUMMARY_ROW_H)),
            aviso,
            font=font,
            fill=TEXT_DIM,
        )


def load_card_fonts() -> dict[str, FontType]:
    """Carrega o mapa padrao de fontes dos cards."""
    return {
        "header": load_font(20, bold=True),
        "header_sub": load_font(13, bold=True),
        "ob": load_font(13, bold=True),
        "detalhe": load_font(12, bold=False),
        "acao": load_font(13, bold=True),
        "secundaria": load_font(11, bold=False),
        "footer": load_font(12, bold=False),
    }


def save_card_image_atomic(
    out_path: str,
    height: int,
    draw_fn: Callable[[ImageDraw.ImageDraw], None],
) -> None:
    """Renderiza imagem em `.tmp` e move atomicamente para `out_path`."""
    tmp_path = f"{out_path}.tmp"
    try:
        with Image.new("RGB", (CARD_W, height), BG_COLOR) as img:
            draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
            draw_fn(draw)
            img.save(tmp_path, "PNG", optimize=True)
        os.replace(tmp_path, out_path)
    except Exception:
        if os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
        raise


def load_validated_payload(result_path: str) -> dict[str, Any]:
    """Carrega e valida o JSON de resultado da extracao."""
    with open(result_path, encoding="utf-8") as f:
        payload: Any = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("Payload JSON deve ser um objeto")
    rows = payload.get("rows")
    if rows is None:
        return {"rows": []}
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Campo 'rows' deve ser uma lista de objetos")
    return payload


def resolve_manifest_path(card_file: str, cards_manifest_file: str) -> str:
    """Resolve o destino de `cards_manifest.json` acompanhando `card_file` em testes."""
    card_dir = os.path.dirname(os.path.abspath(card_file))
    default_manifest_dir = os.path.dirname(os.path.abspath(cards_manifest_file))
    if card_dir == default_manifest_dir:
        return cards_manifest_file
    return os.path.join(card_dir, "cards_manifest.json")


def run_format_main(
    config: FormatMainConfig,
    exec_id: str | None = None,
) -> None:
    """Fluxo padrao de CLI dos scripts `format_message.py`."""
    resolved_exec_id = (
        exec_id
        if exec_id is not None
        else (sys.argv[1] if len(sys.argv) > 1 else "manual")
    )
    result_name = os.path.basename(config.result_file)

    if not os.path.exists(config.result_file):
        config.log_fn(f"{result_name} nao encontrado.", "ERROR", resolved_exec_id)
        sys.exit(1)

    try:
        payload = load_validated_payload(config.result_file)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        config.log_fn(f"Falha ao ler {result_name}: {e}", "ERROR", resolved_exec_id)
        sys.exit(1)

    rows: list[dict[str, Any]] = payload.get("rows", [])
    if not rows:
        config.log_fn("Nenhuma OB a notificar.", "INFO", resolved_exec_id)
        sys.exit(2)

    def _caption(
        page_rows: list[dict[str, Any]],
        page_info: tuple[int, int] | None,
        total_obs: int | None,
    ) -> str:
        page_payload = {**payload, "rows": page_rows, "total": len(page_rows)}
        return config.render_caption(page_payload, page_info, total_obs)

    def _image(
        page_rows: list[dict[str, Any]],
        out_png: str,
        page_info: tuple[int, int] | None,
        total_obs: int | None,
    ) -> None:
        page_payload = {**payload, "rows": page_rows, "total": len(page_rows)}
        config.render_image(page_payload, out_png, page_info, total_obs)

    try:
        manifest = build_paginated_artifacts(
            rows,
            _caption,
            _image,
            config.targets,
            config.pagination,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        config.log_fn(
            f"Falha ao gerar artefatos de mensagem/card: {e}",
            "ERROR",
            resolved_exec_id,
        )
        sys.exit(1)

    if len(manifest) == 1:
        config.log_fn(
            f"message.txt, card.png e cards_manifest.json gerados com {len(rows)} OB(s).",
            "INFO",
            resolved_exec_id,
        )
    else:
        config.log_fn(
            f"cards_manifest.json e {len(manifest)} card(s) paginados gerados para {len(rows)} OB(s).",
            "INFO",
            resolved_exec_id,
        )
    sys.exit(0)

# pylint: disable=broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "2.3.0",
#   "contract": "exit-0=cards-e-manifesto-gerados, exit-2=nada-a-enviar, exit-1=erro",
#   "description": "Le orb_result.json e gera card(s) PNG e cards_manifest.json"
# }
"""Camada de apresentacao do ORB-07.

Le orb_result.json (ja validado pelo extrator), pagina as OBs em cards visuais
em PNG (`card.png` quando 1 pagina ou `card_01.png`..`card_NN.png` em lote)
com legenda pesquisavel no WhatsApp e grava `cards_manifest.json`.
O envio em si e do run.ps1 via lib/Send-WhatsApp.ps1.
"""

import os
import sys
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

from automation_log import ensure_utf8_streams, make_logger
from card_pagination import (
    DEFAULT_MAX_MESSAGE_CHARS,
    MAX_OBS_PER_PAGE,
    ArtifactTargets,
    PaginationConfig,
    write_atomic_text,
)
from card_render import (
    CARD_W,
    COL_GAP,
    DIVIDER_COLOR,
    DOT_GAP,
    DOT_RADIUS,
    FOOTER_BG,
    FOOTER_H,
    HEADER_H,
    HEADER_TEXT,
    MAX_CARD_ROWS,
    OB_ROW_H,
    PAD,
    SUMMARY_ROW_H,
    TEXT_DIM,
    TEXT_MAIN,
    FontType,
    FormatMainConfig,
    center_text_y,
    coerce_nonneg_int,
    draw_summary_banner,
    fit_prefixed_detail,
    fmt_entrega,
    load_card_fonts,
    load_font,
    load_validated_payload,
    resolve_manifest_path,
    run_format_main,
    sanitize_text,
    save_card_image_atomic,
    text_width,
    truncate_message,
    truncate_text,
)

__all__ = [
    "Image",
    "ImageDraw",
    "ImageFont",
    "MAX_MESSAGE_CHARS",
    "build_card_image",
    "build_message",
    "main",
]

ensure_utf8_streams()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "orb_result.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")
CARD_FILE = os.path.join(SCRIPT_DIR, "card.png")
CARDS_MANIFEST_FILE = os.path.join(SCRIPT_DIR, "cards_manifest.json")

log = make_logger("ORB-FORMAT")

# ── Layout e paleta do card visual ────────────────────────────────────────────
HEADER_COLOR = (56, 189, 248)
ACCENT_COMPLETE = (34, 197, 94)
ACCENT_PARTIAL = (245, 158, 11)
MAX_MESSAGE_CHARS = DEFAULT_MAX_MESSAGE_CHARS

# Reexportacoes de retrocompatibilidade para callers e testes unitarios
_load_font = load_font
_sanitize_text = sanitize_text
_coerce_nonneg_int = coerce_nonneg_int
_fmt_entrega = fmt_entrega
_text_width = text_width
_center_text_y = center_text_y
_truncate_text = truncate_text
_fit_prefixed_detail = fit_prefixed_detail
_draw_summary_banner = draw_summary_banner
_load_card_fonts = load_card_fonts
_write_atomic_text = write_atomic_text
_load_validated_payload = load_validated_payload


def _truncate_message(titulo: str, linhas: list[str]) -> str:
    return truncate_message(titulo, linhas, max_chars=MAX_MESSAGE_CHARS)


def _resolve_manifest_path() -> str:
    return resolve_manifest_path(CARD_FILE, CARDS_MANIFEST_FILE)


def _fmt_reduzido(row: dict[str, Any]) -> str:
    return _sanitize_text(row.get("CODIGO_REDUZIDO_CRU"))


def _fmt_numero_ob(row: dict[str, Any]) -> str:
    return _sanitize_text(row.get("NUMERO_OB"))


def _fmt_codigo(valor: Any, largura: int) -> str:
    """Exibe códigos numéricos com largura mínima, sem truncar valores.

    O Oracle pode devolver artigo como NUMBER (perdendo zeros à esquerda) e
    cor como texto preenchido. Converter apenas dígitos ASCII garante o padrão
    de comunicação (artigo com 3 dígitos), preservando alfanuméricos como 0A231.
    """
    texto = _sanitize_text(valor, default="")
    if not texto:
        return "—"
    if texto.isascii() and texto.isdigit():
        return f"{int(texto):0{largura}d}"
    return texto


def _fmt_restricoes(row: dict[str, Any]) -> tuple[str, str]:
    """Retorna (rótulo, valor) das finalidades presentes no saldo distinto."""
    itens = row.get("RESTRICOES_DISPONIVEIS") or []
    restricoes: list[str] = []
    if isinstance(itens, list):
        for item in itens:
            if not isinstance(item, dict):
                continue
            codigo = item.get("codigo")
            descricao = _sanitize_text(item.get("descricao"), default="")
            if codigo is None or not descricao:
                continue
            restricoes.append(f"{_fmt_codigo(codigo, 1)} — {descricao}")

    if not restricoes:
        return "Restrição da peça", "—"
    rotulo = "Restrição da peça" if len(restricoes) == 1 else "Restrições da peça"
    return rotulo, "; ".join(restricoes)


def _pecas_alocadas_e_faltantes(row: dict[str, Any]) -> tuple[int, int, int]:
    total = _coerce_nonneg_int(row.get("TOTAL_PECAS"))
    faltantes = _coerce_nonneg_int(row.get("QTD_PECAS_FALTANTES"))
    alocadas_raw = row.get("QTD_PECAS_ALOCADAS")
    if faltantes > 0 and alocadas_raw is not None:
        alocadas = _coerce_nonneg_int(alocadas_raw)
        return total, alocadas, faltantes
    return total, total, 0


def _is_parcial(row: dict[str, Any]) -> bool:
    _, _, faltantes = _pecas_alocadas_e_faltantes(row)
    return faltantes > 0


def _fmt_acao_pecas(row: dict[str, Any]) -> str:
    """Resume a ação de separação em uma linha direta para a Montagem."""
    total, alocadas, faltantes = _pecas_alocadas_e_faltantes(row)
    if faltantes > 0:
        return f"{total} pçs → usar {alocadas} restr. + {faltantes} s/ restr."
    return f"{total} pçs → usar {total} restr. (Completa)"


def _bloco_ob(row: dict[str, Any]) -> str:
    artigo = _fmt_codigo(row.get("CODIGO_ARTIGO_CRU"), 3)
    reduzido = _fmt_reduzido(row)
    numero_ob = _fmt_numero_ob(row)
    return (
        f"• *OB {numero_ob}* (Art. {artigo} · Red. {reduzido}) — {_fmt_acao_pecas(row)}"
    )


def _build_message_header(
    rows: list[dict[str, Any]],
    page_info: tuple[int, int] | None = None,
    total_batch_obs: int | None = None,
) -> str:
    parciais = len([row for row in rows if _is_parcial(row)])
    completas = len(rows) - parciais
    if page_info is not None:
        page_idx, total_pages = page_info
        total_geral = total_batch_obs if total_batch_obs is not None else len(rows)
        ob_label = "OB" if len(rows) == 1 else "OBs"
        titulo = f"🎯 *Depósito 95 - OBs Restrição Branco* _(Página {page_idx}/{total_pages})_"
        if parciais:
            return (
                f"{titulo}\n_{len(rows)} {ob_label} nesta página "
                f"({completas} completa{'s' if completas != 1 else ''}, "
                f"{parciais} parcia{'is' if parciais != 1 else 'l'}) · "
                f"{total_geral} no total_"
            )
        return (
            f"{titulo}\n_{len(rows)} {ob_label} pronta{'s' if len(rows) != 1 else ''} "
            f"nesta página · {total_geral} no total_"
        )

    titulo = "🎯 *Depósito 95 - OBs Restrição Branco*"
    if len(rows) <= 1:
        return titulo
    if parciais:
        return (
            f"{titulo}\n_{len(rows)} OBs com peças restritas disponíveis "
            f"({completas} completa{'s' if completas != 1 else ''}, "
            f"{parciais} parcia{'is' if parciais != 1 else 'l'})_"
        )
    return f"{titulo}\n_{len(rows)} OBs prontas para montagem_"


def build_message(
    payload: dict[str, Any],
    *,
    page_info: tuple[int, int] | None = None,
    total_batch_obs: int | None = None,
    truncate: bool = True,
) -> str:
    """Monta a legenda enxuta enviada junto com o card PNG. Funcao pura."""
    rows: list[dict[str, Any]] = payload.get("rows", [])
    titulo = _build_message_header(rows, page_info, total_batch_obs)

    linhas = [_bloco_ob(row) for row in rows]
    corpo = "\n".join(linhas)
    mensagem = f"{titulo}\n\n{corpo}\n".replace('"', "'")
    if not truncate or len(mensagem) <= MAX_MESSAGE_CHARS:
        return mensagem
    return _truncate_message(titulo, linhas)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    rows: list[dict[str, Any]],
    fonts: dict[str, FontType],
    *,
    page_info: tuple[int, int] | None = None,
    total_batch_obs: int | None = None,
) -> None:
    draw.rectangle([(0, 0), (CARD_W, HEADER_H)], fill=HEADER_COLOR)

    total_obs = len(rows)
    parciais = len([row for row in rows if _is_parcial(row)])
    completas = total_obs - parciais
    ob_label = "OB" if total_obs == 1 else "OBs"
    if page_info is not None:
        total_geral = total_batch_obs if total_batch_obs is not None else total_obs
        resumo_raw = (
            f"Pág. {page_info[0]}/{page_info[1]} · {total_obs} de {total_geral} OBs"
        )
    elif parciais:
        resumo_raw = (
            f"{total_obs} {ob_label} "
            f"({completas} completa{'s' if completas != 1 else ''}, "
            f"{parciais} parcia{'is' if parciais != 1 else 'l'})"
        )
    else:
        resumo_raw = f"{total_obs} {ob_label} completa{'s' if total_obs != 1 else ''}"

    max_resumo_w = (CARD_W - 2 * PAD) // 2
    resumo = _truncate_text(draw, resumo_raw, fonts["header_sub"], max_resumo_w)
    resumo_x = CARD_W - PAD - _text_width(draw, resumo, fonts["header_sub"])
    draw.text(
        (resumo_x, _center_text_y(draw, resumo, fonts["header_sub"], 0, HEADER_H)),
        resumo,
        font=fonts["header_sub"],
        fill=HEADER_TEXT,
    )

    titulo = _truncate_text(
        draw,
        "DEPÓSITO 95 — OBs RESTRIÇÃO BRANCO",
        fonts["header"],
        resumo_x - PAD - COL_GAP,
    )
    if titulo:
        draw.text(
            (PAD, _center_text_y(draw, titulo, fonts["header"], 0, HEADER_H)),
            titulo,
            font=fonts["header"],
            fill=HEADER_TEXT,
        )


def _draw_ob_linha_principal(
    draw: ImageDraw.ImageDraw,
    row: dict[str, Any],
    line_y0: int,
    status_color: tuple[int, int, int],
    fonts: dict[str, FontType],
) -> None:
    text_x0 = PAD + DOT_RADIUS * 2 + DOT_GAP
    max_acao_w = CARD_W - PAD - text_x0 - COL_GAP - 80
    acao = _truncate_text(draw, _fmt_acao_pecas(row), fonts["acao"], max_acao_w)
    acao_x = CARD_W - PAD - _text_width(draw, acao, fonts["acao"])
    if acao:
        draw.text(
            (acao_x, _center_text_y(draw, acao, fonts["acao"], line_y0, 24)),
            acao,
            font=fonts["acao"],
            fill=status_color,
        )

    part_id_raw = (
        f"OB {_fmt_numero_ob(row)}  ·  Art. {_fmt_codigo(row.get('CODIGO_ARTIGO_CRU'), 3)}"
        f"  ·  Red. {_fmt_reduzido(row)}"
    )
    max_part_w = acao_x - text_x0 - COL_GAP
    part_id = _truncate_text(draw, part_id_raw, fonts["ob"], max_part_w)
    if not part_id:
        return
    draw.text(
        (text_x0, _center_text_y(draw, part_id, fonts["ob"], line_y0, 24)),
        part_id,
        font=fonts["ob"],
        fill=TEXT_MAIN,
    )

    id_end_x = text_x0 + _text_width(draw, part_id, fonts["ob"])
    _, restricoes = _fmt_restricoes(row)
    restr_fitted = _fit_prefixed_detail(
        draw,
        "  ·  Restr. ",
        restricoes,
        fonts["detalhe"],
        acao_x - id_end_x - COL_GAP,
    )
    if restr_fitted:
        draw.text(
            (
                id_end_x,
                _center_text_y(draw, restr_fitted, fonts["detalhe"], line_y0, 24),
            ),
            restr_fitted,
            font=fonts["detalhe"],
            fill=TEXT_DIM,
        )


def _draw_ob_row(
    draw: ImageDraw.ImageDraw,
    row: dict[str, Any],
    index: int,
    fonts: dict[str, FontType],
) -> None:
    y0 = HEADER_H + index * OB_ROW_H
    if index > 0:
        draw.line([(PAD, y0), (CARD_W - PAD, y0)], fill=DIVIDER_COLOR, width=1)

    status_color = ACCENT_PARTIAL if _is_parcial(row) else ACCENT_COMPLETE
    dot_cy = y0 + OB_ROW_H // 2
    draw.ellipse(
        [(PAD, dot_cy - DOT_RADIUS), (PAD + DOT_RADIUS * 2, dot_cy + DOT_RADIUS)],
        fill=status_color,
    )

    _draw_ob_linha_principal(draw, row, y0 + 4, status_color, fonts)

    text_x0 = PAD + DOT_RADIUS * 2 + DOT_GAP
    filial = _sanitize_text(row.get("NOME_CLIENTE"))
    sub_text = _truncate_text(
        draw,
        f"{filial}  ·  Entrega: {_fmt_entrega(row.get('DT_ENTREGA'))}",
        fonts["secundaria"],
        CARD_W - PAD - text_x0,
    )
    if sub_text:
        draw.text(
            (
                text_x0,
                _center_text_y(draw, sub_text, fonts["secundaria"], y0 + 28, 22),
            ),
            sub_text,
            font=fonts["secundaria"],
            fill=TEXT_DIM,
        )


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    rows: list[dict[str, Any]],
    font: FontType,
    footer_y: int,
    *,
    page_info: tuple[int, int] | None = None,
) -> None:
    draw.rectangle([(0, footer_y), (CARD_W, footer_y + FOOTER_H)], fill=FOOTER_BG)

    total_restr = 0
    total_sem_restr = 0
    for row in rows:
        _, alocadas, faltantes = _pecas_alocadas_e_faltantes(row)
        total_restr += alocadas
        total_sem_restr += faltantes

    n_obs = len(rows)
    ob_label = "OB" if n_obs == 1 else "OBs"
    partes = [f"{n_obs} {ob_label}", f"{total_restr} pçs c/ restrição"]
    if page_info is not None:
        partes.insert(0, f"Pág. {page_info[0]}/{page_info[1]}")
    if total_sem_restr > 0:
        partes.append(f"{total_sem_restr} pçs s/ restrição")
    partes.append(datetime.now().strftime("%d/%m/%Y às %H:%M"))

    text = _truncate_text(draw, "  ·  ".join(partes), font, CARD_W - 2 * PAD)
    if text:
        draw.text(
            (PAD, _center_text_y(draw, text, font, footer_y, FOOTER_H)),
            text,
            font=font,
            fill=TEXT_DIM,
        )


def build_card_image(
    payload: dict[str, Any],
    out_path: str = CARD_FILE,
    *,
    page_info: tuple[int, int] | None = None,
    total_batch_obs: int | None = None,
) -> None:
    """Gera o card PNG consolidado das OBs notificadas no ciclo de forma atômica."""
    rows: list[dict[str, Any]] = payload.get("rows", [])
    visible_rows = rows[:MAX_CARD_ROWS]
    omitted = len(rows) - len(visible_rows)
    footer_y = (
        HEADER_H + OB_ROW_H * len(visible_rows) + (SUMMARY_ROW_H if omitted > 0 else 0)
    )
    fonts = _load_card_fonts()

    def _draw(draw: ImageDraw.ImageDraw) -> None:
        _draw_header(
            draw,
            rows,
            fonts,
            page_info=page_info,
            total_batch_obs=total_batch_obs,
        )
        for index, row in enumerate(visible_rows):
            _draw_ob_row(draw, row, index, fonts)
        if omitted > 0:
            _draw_summary_banner(
                draw,
                HEADER_H + OB_ROW_H * len(visible_rows),
                omitted,
                fonts["detalhe"],
            )
        _draw_footer(draw, rows, fonts["footer"], footer_y, page_info=page_info)

    save_card_image_atomic(out_path, footer_y + FOOTER_H, _draw)


def main() -> None:
    """Lê o resultado validado e grava o(s) card(s) PNG, legenda e manifesto."""
    run_format_main(
        FormatMainConfig(
            result_file=RESULT_FILE,
            targets=ArtifactTargets(
                card_file=CARD_FILE,
                message_file=MESSAGE_FILE,
                manifest_file=_resolve_manifest_path(),
            ),
            pagination=PaginationConfig(
                per_page=MAX_OBS_PER_PAGE,
                max_chars=MAX_MESSAGE_CHARS,
            ),
            render_caption=lambda p, pi, tot: build_message(
                p, page_info=pi, total_batch_obs=tot, truncate=False
            ),
            render_image=lambda p, out_png, pi, tot: build_card_image(
                p, out_png, page_info=pi, total_batch_obs=tot
            ),
            log_fn=log,
        )
    )


if __name__ == "__main__":
    main()

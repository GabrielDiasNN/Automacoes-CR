# pylint: disable=broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "2.2.0",
#   "contract": "exit-0=cards-e-manifesto-gerados, exit-2=nada-a-enviar, exit-1=erro",
#   "description": "Le orb_result.json e gera card(s) PNG e cards_manifest.json"
# }
"""Camada de apresentacao do ORB-07.

Le orb_result.json (ja validado pelo extrator), pagina as OBs em cards visuais
em PNG (`card.png` quando 1 pagina ou `card_01.png`..`card_NN.png` em lote)
com legenda pesquisavel no WhatsApp e grava `cards_manifest.json`.
O envio em si e do run.ps1 via lib/Send-WhatsApp.ps1.
"""

import contextlib
import json
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
    MAX_OBS_PER_PAGE,
    ArtifactTargets,
    PaginationConfig,
    build_paginated_artifacts,
    write_atomic_text,
)

ensure_utf8_streams()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "orb_result.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")
CARD_FILE = os.path.join(SCRIPT_DIR, "card.png")
CARDS_MANIFEST_FILE = os.path.join(SCRIPT_DIR, "cards_manifest.json")

log = make_logger("ORB-FORMAT")

# ── Layout e paleta do card visual ────────────────────────────────────────────
BG_COLOR = (30, 30, 46)
HEADER_COLOR = (56, 189, 248)
HEADER_TEXT = (15, 23, 42)
TEXT_MAIN = (236, 234, 228)
TEXT_DIM = (160, 160, 180)
DIVIDER_COLOR = (60, 60, 80)
FOOTER_BG = (20, 20, 36)
ACCENT_COMPLETE = (34, 197, 94)
ACCENT_PARTIAL = (245, 158, 11)

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
MAX_MESSAGE_CHARS = 3500

FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _load_font(size: int, bold: bool = False) -> FontType:
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


def _sanitize_text(valor: Any, default: str = "—") -> str:
    """Normaliza campo textual para legenda e card, protegendo argv de aspas e quebras."""
    if valor is None:
        return default
    texto = " ".join(str(valor).split()).replace('"', "'")
    return texto or default


def _coerce_nonneg_int(valor: Any) -> int:
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


def _fmt_entrega(valor: Any) -> str:
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


def _truncate_message(titulo: str, linhas: list[str]) -> str:
    selecionadas: list[str] = []
    for idx, linha in enumerate(linhas):
        restantes = len(linhas) - idx - 1
        rodape = (
            f"\n… e mais {restantes} OB(s) (consulte os logs)" if restantes > 0 else ""
        )
        candidato = f"{titulo}\n\n" + "\n".join([*selecionadas, linha]) + f"{rodape}\n"
        if len(candidato) <= MAX_MESSAGE_CHARS or not selecionadas:
            selecionadas.append(linha)
        else:
            break

    restantes = len(linhas) - len(selecionadas)
    rodape = f"\n… e mais {restantes} OB(s) (consulte os logs)" if restantes > 0 else ""
    resumo = f"{titulo}\n\n" + "\n".join(selecionadas) + f"{rodape}\n"
    if len(resumo) > MAX_MESSAGE_CHARS:
        resumo = resumo[: MAX_MESSAGE_CHARS - 2].rstrip() + "…\n"
    return resumo.replace('"', "'")


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


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: FontType) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0])


def _center_text_y(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontType,
    box_y: int,
    box_h: int,
) -> int:
    if not text:
        return box_y
    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]
    return int(box_y + (box_h - text_h) / 2 - bbox[1])


def _truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontType,
    max_width: int,
) -> str:
    if max_width <= 0 or not text:
        return ""
    if _text_width(draw, text, font) <= max_width:
        return text
    atual = text[:240]
    while len(atual) > 1:
        atual = atual[:-1]
        candidato = atual.rstrip() + "…"
        if _text_width(draw, candidato, font) <= max_width:
            return candidato
    return ""


def _fit_prefixed_detail(
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
    if _text_width(draw, completo, font) <= max_width:
        return completo
    fitted = _truncate_text(draw, completo, font, max_width)
    if not fitted or len(fitted.removesuffix("…").rstrip()) <= len(prefix.rstrip()):
        return ""
    return fitted


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


def _draw_summary_banner(
    draw: ImageDraw.ImageDraw,
    y0: int,
    omitted: int,
    font: FontType,
) -> None:
    draw.line([(PAD, y0), (CARD_W - PAD, y0)], fill=DIVIDER_COLOR, width=1)
    aviso = _truncate_text(
        draw,
        f"… e mais {omitted} OB(s) omitidas do card (limite visual de {MAX_CARD_ROWS} linhas)",
        font,
        CARD_W - 2 * PAD,
    )
    if aviso:
        draw.text(
            (PAD, _center_text_y(draw, aviso, font, y0, SUMMARY_ROW_H)),
            aviso,
            font=font,
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


def _load_card_fonts() -> dict[str, FontType]:
    return {
        "header": _load_font(20, bold=True),
        "header_sub": _load_font(13, bold=True),
        "ob": _load_font(13, bold=True),
        "detalhe": _load_font(12, bold=False),
        "acao": _load_font(13, bold=True),
        "secundaria": _load_font(11, bold=False),
        "footer": _load_font(12, bold=False),
    }


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

    tmp_path = f"{out_path}.tmp"
    try:
        with Image.new("RGB", (CARD_W, footer_y + FOOTER_H), BG_COLOR) as img:
            draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
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
            img.save(tmp_path, "PNG", optimize=True)
        os.replace(tmp_path, out_path)
    except Exception:
        if os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
        raise


def _write_atomic_text(path: str, content: str) -> None:
    write_atomic_text(path, content)


def _load_validated_payload(result_path: str) -> dict[str, Any]:
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


def _resolve_manifest_path() -> str:
    card_dir = os.path.dirname(os.path.abspath(CARD_FILE))
    default_manifest_dir = os.path.dirname(os.path.abspath(CARDS_MANIFEST_FILE))
    if card_dir == default_manifest_dir:
        return CARDS_MANIFEST_FILE
    return os.path.join(card_dir, "cards_manifest.json")


def main() -> None:
    """Lê o resultado validado e grava o(s) card(s) PNG, legenda e manifesto."""
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    if not os.path.exists(RESULT_FILE):
        log("orb_result.json nao encontrado.", "ERROR", exec_id)
        sys.exit(1)

    try:
        payload = _load_validated_payload(RESULT_FILE)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log(f"Falha ao ler orb_result.json: {e}", "ERROR", exec_id)
        sys.exit(1)

    rows = payload.get("rows", [])
    if not rows:
        log("Nenhuma OB a notificar.", "INFO", exec_id)
        sys.exit(2)

    def _render_caption(
        page_rows: list[dict[str, Any]],
        page_info: tuple[int, int] | None,
        total_obs: int | None,
    ) -> str:
        page_payload = {**payload, "rows": page_rows, "total": len(page_rows)}
        return build_message(
            page_payload,
            page_info=page_info,
            total_batch_obs=total_obs,
            truncate=False,
        )

    def _render_image(
        page_rows: list[dict[str, Any]],
        out_png: str,
        page_info: tuple[int, int] | None,
        total_obs: int | None,
    ) -> None:
        page_payload = {**payload, "rows": page_rows, "total": len(page_rows)}
        build_card_image(
            page_payload,
            out_png,
            page_info=page_info,
            total_batch_obs=total_obs,
        )

    try:
        manifest = build_paginated_artifacts(
            rows,
            _render_caption,
            _render_image,
            ArtifactTargets(
                card_file=CARD_FILE,
                message_file=MESSAGE_FILE,
                manifest_file=_resolve_manifest_path(),
            ),
            PaginationConfig(
                per_page=MAX_OBS_PER_PAGE,
                max_chars=MAX_MESSAGE_CHARS,
            ),
        )
    except Exception as e:
        log(f"Falha ao gerar artefatos de mensagem/card: {e}", "ERROR", exec_id)
        sys.exit(1)

    if len(manifest) == 1:
        log(
            f"message.txt, card.png e cards_manifest.json gerados com {len(rows)} OB(s).",
            "INFO",
            exec_id,
        )
    else:
        log(
            f"cards_manifest.json e {len(manifest)} card(s) paginados gerados para {len(rows)} OB(s).",
            "INFO",
            exec_id,
        )
    sys.exit(0)


if __name__ == "__main__":
    main()

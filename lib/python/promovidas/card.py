"""Renderizacao de cards PNG genericos e manifesto paginado para WhatsApp."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from card_pagination import (
    DEFAULT_MAX_MESSAGE_CHARS,
    MAX_OBS_PER_PAGE,
    cleanup_stale_page_images,
    paginate_rows,
    write_atomic_text,
)
from card_render import (
    CARD_W,
    DIVIDER_COLOR,
    FOOTER_BG,
    FOOTER_H,
    HEADER_H,
    HEADER_TEXT,
    OB_ROW_H,
    PAD,
    TEXT_DIM,
    TEXT_MAIN,
    center_text_y,
    load_card_fonts,
    sanitize_text,
    save_card_image_atomic,
    truncate_message,
    truncate_text,
)
from PIL import ImageDraw

from .config import ConfigPromocao
from .regras import extrair_chave

_COR_HEADER_SOMBRA = (245, 158, 11)
_COR_HEADER_PRODUCAO = (56, 189, 248)
_COR_TEXTO_CLARO = (255, 255, 255)


def _resolver_cores_header(
    cfg: ConfigPromocao,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    cor_hex = cfg.excecao.cor_header if cfg.excecao else None
    if cor_hex:
        r = int(cor_hex[1:3], 16)
        g = int(cor_hex[3:5], 16)
        b = int(cor_hex[5:7], 16)
        luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        texto = HEADER_TEXT if luminancia > 0.6 else _COR_TEXTO_CLARO
        return (r, g, b), texto
    bg = _COR_HEADER_SOMBRA if cfg.modo == "sombra" else _COR_HEADER_PRODUCAO
    return bg, HEADER_TEXT


def _valor_card(cfg: ConfigPromocao, row: Mapping[str, Any], col: str) -> str:
    texto = sanitize_text(row.get(col))
    exc = cfg.excecao
    if exc and col in exc.colunas_unidade and texto != "—":
        um = sanitize_text(row.get(exc.coluna_unidade))
        if um and um != "—":
            return f"{texto} {um.lower()}"
    return texto


def _colunas_card(cfg: ConfigPromocao) -> tuple[str, ...]:
    if cfg.excecao and cfg.excecao.colunas_card:
        return cfg.excecao.colunas_card
    return cfg.painel.colunas


def _formatar_linha_legenda(
    cfg: ConfigPromocao, row: Mapping[str, Any], colunas: Sequence[str]
) -> str:
    partes = [f"{col}: {_valor_card(cfg, row, col)}" for col in colunas[:6]]
    return "• " + " | ".join(partes)


def _partes_legenda(
    cfg: ConfigPromocao,
    rows: Sequence[Mapping[str, Any]],
    page_info: tuple[int, int] | None,
    total_geral: int,
) -> tuple[str, list[str]]:
    pag = f" (Pág. {page_info[0]}/{page_info[1]})" if page_info else ""
    titulo = (
        f"*{cfg.excecao.titulo_alerta if cfg.excecao else cfg.painel.titulo}*"
        f"{pag} — {total_geral} item(ns)"
    )
    cols = _colunas_card(cfg)
    linhas = [_formatar_linha_legenda(cfg, r, cols) for r in rows]
    return titulo, linhas


def _montar_legenda_bruta(
    cfg: ConfigPromocao,
    rows: Sequence[Mapping[str, Any]],
    page_info: tuple[int, int] | None,
    total_geral: int,
) -> str:
    titulo, linhas = _partes_legenda(cfg, rows, page_info, total_geral)
    return "\n".join([titulo, *linhas]) if linhas else titulo


def _montar_legenda(
    cfg: ConfigPromocao,
    rows: Sequence[Mapping[str, Any]],
    page_info: tuple[int, int] | None,
    total_geral: int,
) -> str:
    titulo, linhas = _partes_legenda(cfg, rows, page_info, total_geral)
    return truncate_message(titulo, linhas, max_chars=DEFAULT_MAX_MESSAGE_CHARS)


def _desenhar_linha_card(
    cfg: ConfigPromocao,
    draw: ImageDraw.ImageDraw,
    row: Mapping[str, Any],
    idx: int,
    fonts: dict[str, Any],
) -> None:
    cols = _colunas_card(cfg)
    y0 = HEADER_H + idx * OB_ROW_H
    if idx > 0:
        draw.line([(PAD, y0), (CARD_W - PAD, y0)], fill=DIVIDER_COLOR, width=1)
    principal = _valor_card(cfg, row, cols[0]) if cols else "—"
    detalhes = " · ".join(f"{c}: {_valor_card(cfg, row, c)}" for c in cols[1:6])
    prim = truncate_text(draw, principal, fonts["ob"], CARD_W - 2 * PAD)
    sec = truncate_text(draw, detalhes, fonts["detalhe"], CARD_W - 2 * PAD)
    draw.text((PAD, y0 + 8), prim, font=fonts["ob"], fill=TEXT_MAIN)
    if sec:
        draw.text((PAD, y0 + 29), sec, font=fonts["detalhe"], fill=TEXT_DIM)


def _render_pagina_png(
    cfg: ConfigPromocao,
    page_rows: Sequence[Mapping[str, Any]],
    out_png: Path,
    page_info: tuple[int, int] | None,
    total_geral: int,
) -> None:
    fonts = load_card_fonts()
    footer_y = HEADER_H + OB_ROW_H * len(page_rows)
    header_bg, header_fg = _resolver_cores_header(cfg)
    titulo = f"{cfg.excecao.titulo_alerta if cfg.excecao else cfg.painel.titulo}"

    def _draw(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle([(0, 0), (CARD_W, HEADER_H)], fill=header_bg)
        cabecalho = truncate_text(
            draw, f"{titulo} ({total_geral})", fonts["header"], CARD_W - 2 * PAD
        )
        draw.text(
            (PAD, center_text_y(draw, cabecalho, fonts["header"], 0, HEADER_H)),
            cabecalho,
            font=fonts["header"],
            fill=header_fg,
        )
        for idx, row in enumerate(page_rows):
            _desenhar_linha_card(cfg, draw, row, idx, fonts)
        draw.rectangle([(0, footer_y), (CARD_W, footer_y + FOOTER_H)], fill=FOOTER_BG)
        pag_txt = f"Pág. {page_info[0]}/{page_info[1]}  ·  " if page_info else ""
        rodape = f"{pag_txt}{datetime.now().strftime('%d/%m/%Y às %H:%M')}"
        draw.text(
            (PAD, center_text_y(draw, rodape, fonts["footer"], footer_y, FOOTER_H)),
            rodape,
            font=fonts["footer"],
            fill=TEXT_DIM,
        )

    save_card_image_atomic(str(out_png), footer_y + FOOTER_H, _draw)


def gerar_artefatos_whatsapp(
    cfg: ConfigPromocao,
    pendentes: Sequence[Mapping[str, Any]],
    pasta_trabalho: Path,
) -> tuple[Path, Path, Path]:
    """Gera PNG(s), ``message.txt`` e ``cards_manifest.json`` na pasta da promocao."""
    if not pendentes:
        raise ValueError("gerar_artefatos_whatsapp exige ao menos uma linha pendente.")
    cleanup_stale_page_images(str(pasta_trabalho))
    total_geral = len(pendentes)
    paginas = paginate_rows(
        [dict(r) for r in pendentes],
        lambda rows_pag, page_info, total_obs: _montar_legenda_bruta(
            cfg,
            rows_pag,
            page_info,
            total_obs if total_obs is not None else total_geral,
        ),
        per_page=MAX_OBS_PER_PAGE,
        max_chars=DEFAULT_MAX_MESSAGE_CHARS,
    )
    total_pags = len(paginas)
    manifest: list[dict[str, Any]] = []

    for idx, page_rows in enumerate(paginas, start=1):
        page_info = (idx, total_pags) if total_pags > 1 else None
        nome_img = "card.png" if total_pags == 1 else f"card_{idx:02d}.png"
        img_path = pasta_trabalho / nome_img
        _render_pagina_png(cfg, page_rows, img_path, page_info, total_geral)
        legenda = _montar_legenda(cfg, page_rows, page_info, total_geral)
        if idx == 1:
            write_atomic_text(str(pasta_trabalho / "message.txt"), legenda)
        manifest.append(
            {
                "phase_key": f"{cfg.slug}_p{idx:02d}",
                "image_path": os.path.basename(str(img_path)),
                "caption": legenda,
                "ob_ids": [extrair_chave(r, cfg.chave) for r in page_rows],
            }
        )

    manifest_path = pasta_trabalho / "cards_manifest.json"
    write_atomic_text(
        str(manifest_path),
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    return (
        pasta_trabalho / ("card.png" if total_pags == 1 else "card_01.png"),
        pasta_trabalho / "message.txt",
        manifest_path,
    )

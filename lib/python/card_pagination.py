# {
#   "version": "1.0.0",
#   "description": "Helper compartilhado de paginacao e manifesto para cards PNG e legendas WhatsApp"
# }
"""Paginacao deterministica de OBs em multiplas paginas de cards e legendas."""

from __future__ import annotations

import contextlib
import glob
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

MAX_OBS_PER_PAGE = 15
DEFAULT_MAX_MESSAGE_CHARS = 3500

RenderCaptionFn = Callable[
    [list[dict[str, Any]], tuple[int, int] | None, int | None],
    str,
]
RenderImageFn = Callable[
    [list[dict[str, Any]], str, tuple[int, int] | None, int | None],
    None,
]


@dataclass(frozen=True)
class ArtifactTargets:
    """Caminhos de saida para card, legenda e manifesto paginado."""

    card_file: str
    message_file: str
    manifest_file: str


@dataclass(frozen=True)
class PaginationConfig:
    """Limites de paginacao para cards PNG e legendas WhatsApp."""

    per_page: int = MAX_OBS_PER_PAGE
    max_chars: int = DEFAULT_MAX_MESSAGE_CHARS


def extract_ob_id(row: dict[str, Any]) -> str:
    """Extrai o identificador da OB de uma linha serializada de resultado."""
    for key in ("NUMERO_OB", "ob", "id_ob"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def write_atomic_text(path: str, content: str) -> None:
    """Grava texto UTF-8 sem BOM via arquivo temporario + replace atomico."""
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".txt", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


def cleanup_stale_page_images(out_dir: str) -> None:
    """Remove PNGs paginados residuais (`card_*.png`) antes de nova geracao."""
    pattern = os.path.join(out_dir, "card_*.png")
    for path in glob.glob(pattern):
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)


def paginate_rows(
    rows: list[dict[str, Any]],
    render_caption: RenderCaptionFn,
    per_page: int = MAX_OBS_PER_PAGE,
    max_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
) -> list[list[dict[str, Any]]]:
    """Divide `rows` em paginas com ate `per_page` itens e legenda <= `max_chars`.

    Nunca descarta OBs: se uma pagina exceder `max_chars` antes de atingir
    `per_page`, quebra a pagina antecipadamente; se uma unica OB exceder
    `max_chars`, ainda assim ela e mantida isolada na propria pagina.
    """
    if per_page < 1:
        raise ValueError("per_page deve ser maior ou igual a 1.")
    if not rows:
        return []

    total_obs = len(rows)
    if total_obs <= per_page:
        single_caption = render_caption(rows, None, total_obs)
        if len(single_caption) <= max_chars:
            return [list(rows)]

    # Usa marcador conservador de paginacao para que a legenda real (com
    # total_pages <= total_obs) nunca ultrapasse o limite apos calcular paginas.
    worst_page_info = (max(2, total_obs), max(2, total_obs))
    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for row in rows:
        candidate = current + [row]
        fits_rows = len(candidate) <= per_page
        fits_chars = (
            len(render_caption(candidate, worst_page_info, total_obs)) <= max_chars
        )
        if not current or (fits_rows and fits_chars):
            current = candidate
        else:
            pages.append(current)
            current = [row]

    if current:
        pages.append(current)
    return pages


def _build_manifest_entry(
    page_rows: list[dict[str, Any]],
    page_idx: int,
    total_pages: int,
    image_name: str,
    caption: str,
) -> dict[str, Any]:
    return {
        "page": page_idx,
        "total_pages": total_pages,
        "phase_key": f"page_{page_idx:02d}",
        "image_path": image_name,
        "caption": caption,
        "ob_ids": [extract_ob_id(row) for row in page_rows],
    }


def _emit_single_page(
    page_rows: list[dict[str, Any]],
    render_caption: RenderCaptionFn,
    render_image: RenderImageFn,
    targets: ArtifactTargets,
    total_obs: int,
) -> list[dict[str, Any]]:
    caption = render_caption(page_rows, None, total_obs)
    write_atomic_text(targets.message_file, caption)
    render_image(page_rows, targets.card_file, None, total_obs)
    return [
        _build_manifest_entry(
            page_rows,
            1,
            1,
            os.path.basename(targets.card_file),
            caption,
        )
    ]


def _emit_multi_page(
    pages: list[list[dict[str, Any]]],
    render_caption: RenderCaptionFn,
    render_image: RenderImageFn,
    targets: ArtifactTargets,
    out_dir: str,
) -> list[dict[str, Any]]:
    total_pages = len(pages)
    total_obs = sum(len(page) for page in pages)
    for stale in (targets.card_file, targets.message_file):
        with contextlib.suppress(FileNotFoundError):
            os.remove(stale)

    manifest: list[dict[str, Any]] = []
    for page_idx, page_rows in enumerate(pages, start=1):
        page_info = (page_idx, total_pages)
        image_name = f"card_{page_idx:02d}.png"
        caption = render_caption(page_rows, page_info, total_obs)
        render_image(page_rows, os.path.join(out_dir, image_name), page_info, total_obs)
        manifest.append(
            _build_manifest_entry(
                page_rows,
                page_idx,
                total_pages,
                image_name,
                caption,
            )
        )
    return manifest


def build_paginated_artifacts(
    rows: list[dict[str, Any]],
    render_caption: RenderCaptionFn,
    render_image: RenderImageFn,
    targets: ArtifactTargets,
    config: PaginationConfig | None = None,
) -> list[dict[str, Any]]:
    """Gera PNGs, legendas (quando 1 pagina) e `cards_manifest.json`."""
    if not rows:
        raise ValueError("Nenhuma OB disponivel para gerar artefatos paginados.")

    cfg = config or PaginationConfig()
    out_dir = os.path.dirname(os.path.abspath(targets.card_file))
    cleanup_stale_page_images(out_dir)

    pages = paginate_rows(
        rows,
        render_caption,
        per_page=cfg.per_page,
        max_chars=cfg.max_chars,
    )
    if len(pages) == 1:
        manifest = _emit_single_page(
            pages[0],
            render_caption,
            render_image,
            targets,
            len(rows),
        )
    else:
        manifest = _emit_multi_page(
            pages,
            render_caption,
            render_image,
            targets,
            out_dir,
        )

    write_atomic_text(
        targets.manifest_file,
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    return manifest

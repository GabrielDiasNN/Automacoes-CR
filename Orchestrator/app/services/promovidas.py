"""Servicos de leitura snapshot-first de consultas promovidas (nunca abre Oracle)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain_errors import DomainRuleError

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validar_slug(slug: str) -> str:
    limpo = (slug or "").strip()
    if not _SLUG_RE.match(limpo):
        raise DomainRuleError(400, f"Slug de consulta promovida invalido: {slug!r}")
    return limpo


def _promovidas_dir(project_root: Path) -> Path:
    return project_root / "Consultas Promovidas"


def _snapshots_dir(project_root: Path) -> Path:
    return _promovidas_dir(project_root) / "snapshots"


def _idade_minutos(generated_at: str | None) -> float | None:
    if not generated_at:
        return None
    try:
        dt = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return round(max((datetime.now(UTC) - dt).total_seconds() / 60.0, 0.0), 1)


def _ler_snapshot_latest(project_root: Path, slug: str) -> dict[str, Any] | None:
    arquivo = _snapshots_dir(project_root) / "latest" / f"{slug}.json"
    if not arquivo.is_file():
        return None
    try:
        dados: Any = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dados if isinstance(dados, dict) else None


def _int_seguro(valor: Any, padrao: int = 0) -> int:
    if isinstance(valor, bool):
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _kpis_seguros(valor: Any) -> dict[str, Any]:
    if isinstance(valor, dict):
        return dict(valor)
    if isinstance(valor, str):
        try:
            parsed: Any = json.loads(valor)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def listar_promocoes(project_root: Path) -> list[dict[str, Any]]:
    """Lista todas as promocoes configuradas em ``Consultas Promovidas/*/promocao.json``."""
    base = _promovidas_dir(project_root)
    if not base.is_dir():
        return []
    itens: list[dict[str, Any]] = []
    for pasta in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if (
            not pasta.is_dir()
            or pasta.name in {"snapshots"}
            or pasta.name.startswith(".")
        ):
            continue
        cfg_path = pasta / "promocao.json"
        if not cfg_path.is_file():
            continue
        try:
            cfg: Any = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(cfg, dict):
            continue
        slug = str(cfg.get("slug") or pasta.name)
        snap = _ler_snapshot_latest(project_root, slug)
        cfg_painel = cfg.get("painel")
        painel: dict[str, Any] = cfg_painel if isinstance(cfg_painel, dict) else {}
        destinos_raw = cfg.get("destinos")
        destinos = (
            list(destinos_raw) if isinstance(destinos_raw, list) else ["dashboard"]
        )
        generated_at = (
            str(snap["generated_at"]) if snap and snap.get("generated_at") else None
        )
        itens.append(
            {
                "slug": slug,
                "nome": str(cfg.get("nome") or slug),
                "titulo": str(painel.get("titulo") or cfg.get("nome") or slug),
                "modo": str(cfg.get("modo") or "sombra"),
                "destinos": destinos,
                "has_snapshot": snap is not None,
                "generated_at": generated_at,
                "age_minutes": _idade_minutos(generated_at),
                "total_rows": _int_seguro(snap.get("total_rows"), 0) if snap else 0,
                "excecoes_count": (
                    _int_seguro(snap.get("excecoes_count"), 0) if snap else 0
                ),
                "kpis": _kpis_seguros(snap.get("kpis")) if snap else {},
            }
        )
    return itens


def obter_ultimo_snapshot(project_root: Path, slug: str) -> dict[str, Any]:
    """Retorna o snapshot JSON mais recente de ``slug`` ou levanta DomainRuleError(404)."""
    slug_ok = _validar_slug(slug)
    snap = _ler_snapshot_latest(project_root, slug_ok)
    if snap is None:
        raise DomainRuleError(
            404, f"Snapshot nao encontrado para a consulta promovida '{slug_ok}'."
        )
    snap["age_minutes"] = _idade_minutos(
        str(snap["generated_at"]) if snap.get("generated_at") else None
    )
    return snap


def obter_historico(
    project_root: Path, slug: str, *, limit: int = 30
) -> list[dict[str, Any]]:
    """Retorna historico resumido de execucoes da promocao a partir de ``promovidas.db``."""
    slug_ok = _validar_slug(slug)
    db_path = _snapshots_dir(project_root) / "promovidas.db"
    if not db_path.is_file():
        return []
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT slug, generated_at, modo, total_rows, excecoes_count, kpis_json
              FROM snapshots_historico
             WHERE slug = ?
             ORDER BY generated_at DESC
             LIMIT ?
            """,
            (slug_ok, limit),
        ).fetchall()
    return [
        {
            "slug": str(r["slug"]),
            "generated_at": str(r["generated_at"]),
            "modo": str(r["modo"]),
            "total_rows": _int_seguro(r["total_rows"], 0),
            "excecoes_count": _int_seguro(r["excecoes_count"], 0),
            "kpis": _kpis_seguros(r["kpis_json"]),
        }
        for r in rows
    ]

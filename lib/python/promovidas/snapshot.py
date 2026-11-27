"""Persistencia de snapshots locais (JSON latest + SQLite historico)."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import hub_runner as hr

from .config import ConfigPromocao

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snapshots_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    modo TEXT NOT NULL,
    total_rows INTEGER NOT NULL,
    excecoes_count INTEGER NOT NULL,
    kpis_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_slug_dt
    ON snapshots_historico (slug, generated_at DESC);
"""


def dir_snapshots(raiz: Path) -> Path:
    """Diretorio raiz dos snapshots de consultas promovidas."""
    return raiz / "Consultas Promovidas" / "snapshots"


def _colunas_efetivas(
    rows: Sequence[Mapping[str, Any]],
    colunas_cfg: Sequence[str],
) -> list[str]:
    if colunas_cfg:
        return list(colunas_cfg)
    if rows:
        return list(rows[0].keys())
    return []


def gravar_snapshot(
    raiz: Path,
    cfg: ConfigPromocao,
    rows: Sequence[Mapping[str, Any]],
    kpis: Mapping[str, Any],
    *,
    excecoes_count: int = 0,
) -> Path:
    """Grava ``latest/<slug>.json`` atomicamente e registra historico em ``promovidas.db``."""
    base = dir_snapshots(raiz)
    latest_dir = base / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)

    gerado_em = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "slug": cfg.slug,
        "nome": cfg.nome,
        "titulo": cfg.painel.titulo,
        "modo": cfg.modo,
        "generated_at": gerado_em,
        "total_rows": len(rows),
        "excecoes_count": excecoes_count,
        "kpis": dict(kpis),
        "columns": _colunas_efetivas(rows, cfg.painel.colunas),
        "rows": [dict(r) for r in rows],
    }

    destino_json = latest_dir / f"{cfg.slug}.json"
    hr.write_json_atomic(destino_json, payload)

    db_path = base / "promovidas.db"
    with contextlib.closing(sqlite3.connect(str(db_path), timeout=15.0)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO snapshots_historico
                (slug, generated_at, modo, total_rows, excecoes_count, kpis_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                cfg.slug,
                gerado_em,
                cfg.modo,
                len(rows),
                excecoes_count,
                json.dumps(dict(kpis), ensure_ascii=False),
            ),
        )
        conn.commit()
    return destino_json

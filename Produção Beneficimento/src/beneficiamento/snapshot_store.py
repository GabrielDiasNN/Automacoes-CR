"""Leitura e escrita atomica dos snapshots do Beneficiamento."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import PERIOD_ORDER, SNAPSHOT_DIR


def resolve_snapshot_dir(override: str | None = None) -> Path:
    raw = override or os.environ.get("BENEFICIAMENTO_SNAPSHOT_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return SNAPSHOT_DIR


def snapshot_path(period: str, kind: str, snapshot_dir: Path | None = None) -> Path:
    if period not in PERIOD_ORDER:
        raise ValueError(f"Periodo invalido: {period}")
    if kind not in {"analytics", "profile"}:
        raise ValueError(f"Tipo de snapshot invalido: {kind}")
    root = snapshot_dir or resolve_snapshot_dir()
    return root / f"{period}.{kind}.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime)

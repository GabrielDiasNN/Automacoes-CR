"""Leitura e escrita atomica dos snapshots do Beneficiamento."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
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
    """Escreve JSON com troca atômica, isolando escritores concorrentes.

    O temporário era derivado deterministicamente (`<periodo>.<kind>.json.tmp`).
    O `max_instances=1` das jobs impede a sobreposição do agendador consigo
    mesmo, mas NÃO com `POST /api/beneficiamento/refresh`, que chama a mesma
    função: um "Atualizar agora" clicado durante o ciclo de 90 s punha dois
    processos escrevendo o MESMO arquivo temporário, e o `replace` — atômico
    quanto à troca — podia promover a intercalação das duas escritas.

    O sufixo por PID + uuid isola os escritores. `fsync` antes do `replace`
    fecha a outra ponta: sem ele, uma queda de energia podia promover um arquivo
    de conteúdo truncado por cima de um snapshot íntegro.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(
        f"{path.suffix}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    )
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        # O temporário agora é único por processo: se algo falhar antes do
        # replace, ninguém o sobrescreve no ciclo seguinte — removê-lo aqui
        # evita acúmulo de lixo no diretório de snapshots.
        if tmp_path.exists():
            with contextlib.suppress(OSError):
                tmp_path.unlink()


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

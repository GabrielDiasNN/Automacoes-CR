"""Camada de manifesto do portfólio: modelos e carga de automation.manifest.json.

Extraído de ``portfolio_catalog`` para isolar a leitura/validação dos manifestos
(I/O de disco + modelos Pydantic) da lógica de saúde operacional cruzada.
``portfolio_catalog`` reexporta estes símbolos para preservar a API pública.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CatalogDependencies(BaseModel):
    """Dependências externas declaradas no manifesto da automação."""

    oracle: bool = False
    outlook: bool = False
    whatsapp: bool = False


class CatalogOrchestrator(BaseModel):
    """Bloco ``orchestrator`` do manifesto (caminho do script de entrada)."""

    script_path: str


class CatalogManifest(BaseModel):
    """Manifesto validado de uma automação (automation.manifest.json)."""

    id: str
    name: str
    slug: str
    directory_name: str | None = None
    criticality: str
    sla_minutes: int | None = None
    owner_area: str
    entrypoint: str
    runtime: str
    channels: list[str] = Field(default_factory=list)
    queue_group: str | None = None
    max_runtime_minutes: int = 30
    max_retries: int = 0
    schedule_summary: str
    runbook_path: str
    context_path: str
    readme_path: str
    orchestrator: CatalogOrchestrator
    dependencies: CatalogDependencies = Field(default_factory=CatalogDependencies)
    smoke_tests: list[str] = Field(default_factory=list)

    @field_validator("criticality")
    @classmethod
    def v_criticality(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"critical", "high", "medium", "low"}:
            raise ValueError("criticality deve ser: critical, high, medium ou low.")
        return normalized

    @field_validator("channels")
    @classmethod
    def v_channels(cls, value: list[str]) -> list[str]:
        allowed = ["email", "whatsapp"]
        normalized: list[str] = []
        for item in value:
            current = str(item or "").strip().lower()
            if not current:
                continue
            if current not in allowed:
                raise ValueError("channels aceita apenas email e whatsapp.")
            if current not in normalized:
                normalized.append(current)
        return normalized


@dataclass
class CatalogEntry:
    """Manifesto carregado com o caminho de origem em disco."""

    manifest: CatalogManifest
    manifest_path: Path


def _normalize_repo_relative(project_root: Path, raw_path: str | None) -> str | None:
    if raw_path is None:
        return None
    candidate = str(raw_path).strip()
    if not candidate:
        return None
    resolved = _resolve_repo_path(project_root, candidate)
    relpath = resolved.relative_to(project_root.resolve()).as_posix()
    return f"./{relpath}"


def _resolve_repo_path(project_root: Path, raw_path: str) -> Path:
    value = str(raw_path).strip().replace("\\", "/")
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        base = project_root.resolve()
        relative = value[2:] if value.startswith("./") else value
        resolved = (base / relative).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Caminho fora do projeto: {raw_path}") from exc
    return resolved


def _slugify(text: str) -> str:
    normalized = "".join(
        char.lower() if char.isalnum() else "-" for char in str(text or "").strip()
    )
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "sem-slug"


def _format_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _channels_to_csv(channels: list[str]) -> str | None:
    if not channels:
        return None
    allowed = ["email", "whatsapp"]
    ordered = [item for item in allowed if item in channels]
    return ",".join(ordered) if ordered else None


def _path_exists(project_root: Path, raw_path: str | None) -> bool:
    if not raw_path:
        return False
    try:
        return _resolve_repo_path(project_root, raw_path).exists()
    except ValueError:
        return False


def _load_manifest(manifest_path: Path) -> CatalogEntry:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["directory_name"] = manifest_path.parent.name
    manifest = CatalogManifest.model_validate(payload)
    return CatalogEntry(manifest=manifest, manifest_path=manifest_path)


# Cache de manifests: lista com no máximo um item (mtimes_snapshot, entries),
# invalidado quando algum mtime muda. Container mutável dispensa 'global'.
_MANIFESTS_CACHE: list[tuple[dict[str, float], list[CatalogEntry]]] = []


def _build_manifests_mtime_snapshot(
    root: Path, include_template: bool
) -> dict[str, float]:
    """Coleta os mtimes dos manifests presentes no disco."""
    snapshot: dict[str, float] = {}
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name == "_Template" and not include_template:
            continue
        manifest_path = child / "automation.manifest.json"
        if manifest_path.exists():
            snapshot[str(manifest_path)] = manifest_path.stat().st_mtime
    return snapshot


def load_catalog_manifests(
    project_root: str | Path, include_template: bool = False
) -> list[CatalogEntry]:
    root = Path(project_root).resolve()
    current_mtimes = _build_manifests_mtime_snapshot(root, include_template)

    if _MANIFESTS_CACHE:
        cached_mtimes, cached_entries = _MANIFESTS_CACHE[0]
        if cached_mtimes == current_mtimes:
            return cached_entries

    manifests: list[CatalogEntry] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name == "_Template" and not include_template:
            continue
        manifest_path = child / "automation.manifest.json"
        if not manifest_path.exists():
            continue
        manifests.append(_load_manifest(manifest_path))

    _MANIFESTS_CACHE[:] = [(current_mtimes, manifests)]
    return manifests

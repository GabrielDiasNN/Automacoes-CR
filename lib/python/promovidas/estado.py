"""Estado de idempotencia por chave com janela de renotificacao."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import hub_runner as hr

from .regras import extrair_chave


def ler_estado(caminho: Path) -> dict[str, str]:
    """Le mapa ``{chave: iso_timestamp_utc}`` do arquivo de estado (ou vazio)."""
    if not caminho.exists():
        return {}
    try:
        bruto: Any = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(bruto, dict):
        return {}
    itens = bruto.get("notified")
    if not isinstance(itens, dict):
        return {}
    return {str(k): str(v) for k, v in itens.items() if isinstance(k, str)}


def _expirou(ultimo_iso: str | None, agora: datetime, ttl_horas: float) -> bool:
    if not ultimo_iso:
        return True
    try:
        anterior = datetime.fromisoformat(ultimo_iso)
    except ValueError:
        return True
    if anterior.tzinfo is None:
        anterior = anterior.replace(tzinfo=UTC)
    atual = agora if agora.tzinfo is not None else agora.replace(tzinfo=UTC)
    if ttl_horas <= 0:
        return False
    return (atual - anterior).total_seconds() >= ttl_horas * 3600.0


def selecionar_pendentes(
    excecoes: Sequence[Mapping[str, Any]],
    colunas_chave: Sequence[str],
    estado_anterior: Mapping[str, str],
    *,
    agora: datetime | None = None,
    renotificar_apos_horas: float = 24.0,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Filtra excecoes novas ou vencidas e gera o proximo mapa de estado.

    Chaves que deixaram de aparecer nas excecoes saem do estado para que,
    caso voltem a ocorrer no futuro, gerem novo alerta imediato.
    """
    ref = agora or datetime.now(UTC)
    agora_iso = ref.isoformat()
    pendentes: list[dict[str, Any]] = []
    proximo_estado: dict[str, str] = {}

    for row in excecoes:
        chave = extrair_chave(row, colunas_chave)
        ultimo = estado_anterior.get(chave)
        if _expirou(ultimo, ref, renotificar_apos_horas):
            pendentes.append(dict(row))
            proximo_estado[chave] = agora_iso
        elif ultimo is not None:
            proximo_estado[chave] = ultimo

    return pendentes, proximo_estado


def gravar_estado(caminho: Path, estado: Mapping[str, str], *, exec_id: str) -> None:
    """Persiste ``seen_state.json`` de forma atomica."""
    hr.write_json_atomic(
        caminho,
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "exec_id": exec_id,
            "notified": dict(estado),
        },
    )

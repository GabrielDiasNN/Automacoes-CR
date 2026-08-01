"""Normalizacao de turno do Beneficiamento (implementacao unica).

Substitui as quatro copias historicas: historico_db._normalize_turno_fields,
historico_db.buscar_historico (inline), overview_v1._normalize_turno_values e a
logica embutida em analytics.build_fato_producao.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .coercion import safe_strip

DEFAULT_LABEL = "Indefinido"


def normalize_shift(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Retorna ``(turno_id, turno_label)`` a partir de um registro.

    Regra: o id vem de TURNO_PROD/turno/TURNO; o rotulo de TURNO_DESC. Quando o
    rotulo falta mas ha id, usa ``"TURNO {id}"``. Ambos podem ser None se nada
    estiver presente -- o chamador decide o default de exibicao.
    """
    turno_id = safe_strip(
        payload.get("TURNO_PROD") or payload.get("turno") or payload.get("TURNO")
    )
    turno_label = safe_strip(payload.get("TURNO_DESC"))
    if not turno_label and turno_id:
        turno_label = f"TURNO {turno_id}"
    return (turno_id or None, turno_label or None)

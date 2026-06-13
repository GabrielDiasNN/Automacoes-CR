"""Nucleo compartilhado do dominio Beneficiamento.

Fonte unica de coercoes de tipo, normalizacao de turno, aliases de coluna e
formulas de KPI. Substitui as copias historicamente duplicadas em analytics,
historico_db, overview_v1, quality e profile.
"""

from .coercion import (parse_iso_date, round_or_zero, safe_strip, safe_text,
                       to_float)
from .metrics import deviation_minutes, time_efficiency, weighted_average
from .schema import PHASE_GROUPS, first_present, resolve_alias
from .shifts import normalize_shift

__all__ = [
    "to_float",
    "safe_text",
    "safe_strip",
    "parse_iso_date",
    "round_or_zero",
    "normalize_shift",
    "resolve_alias",
    "first_present",
    "PHASE_GROUPS",
    "time_efficiency",
    "weighted_average",
    "deviation_minutes",
]

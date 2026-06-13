"""Formulas de KPI do Beneficiamento (nomeadas e auditaveis).

Centraliza calculos antes repetidos em overview_v1, analytics e
snapshot_dashboard, dando-lhes nome e documentacao unica.
"""

from __future__ import annotations

import statistics
from typing import Iterable


def time_efficiency(min_prev: float, min_real: float) -> float:
    """Eficiencia de tempo (proxy OEE operacional), em pontos percentuais.

    Formula: ``MIN_PREV / MIN_REAL * 100``. Interpretacao: percentual do tempo
    previsto frente ao tempo real gasto. Retorna 0.0 quando ``min_real <= 0``.
    """
    if min_real <= 0:
        return 0.0
    return round((min_prev / min_real) * 100.0, 2)


def deviation_minutes(min_prev: float, min_real: float) -> float:
    """Desvio em minutos: ``MIN_REAL - MIN_PREV`` (positivo = atraso)."""
    return round(min_real - min_prev, 2)


def weighted_average(values: Iterable[float | None], scale: int) -> float | None:
    """Media aritmetica ignorando None; None se nao houver valores utilizaveis."""
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(statistics.fmean(usable), scale)

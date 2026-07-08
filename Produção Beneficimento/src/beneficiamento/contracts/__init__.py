"""Contratos públicos do histórico de Beneficiamento."""

from .detail import obter_detail_historico
from .overview import obter_overview_historico
from .tingimento import obter_tingimento_historico

__all__ = [
    "obter_detail_historico",
    "obter_overview_historico",
    "obter_tingimento_historico",
]

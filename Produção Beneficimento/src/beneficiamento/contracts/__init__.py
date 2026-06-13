"""Contratos públicos do histórico de Beneficiamento."""

from .analytics import obter_analytics_historico
from .detail import obter_detail_historico
from .overview import obter_overview_historico

__all__ = [
    "obter_analytics_historico",
    "obter_detail_historico",
    "obter_overview_historico",
]

"""Compatibilidade para consumidores legados dos contratos históricos V1."""

from .contracts import (obter_analytics_historico, obter_detail_historico,
                        obter_overview_historico)

__all__ = [
    "obter_analytics_historico",
    "obter_detail_historico",
    "obter_overview_historico",
]

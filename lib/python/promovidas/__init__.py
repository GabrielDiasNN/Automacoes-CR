"""Motor declarativo de consultas promovidas (Modelo 2)."""

from .config import (
    CondicaoFiltro,
    ConfigExcecao,
    ConfigPainel,
    ConfigPromocao,
    carregar_config,
)
from .regras import calcular_kpis, extrair_chave, filtrar_excecoes

__all__ = [
    "CondicaoFiltro",
    "ConfigExcecao",
    "ConfigPainel",
    "ConfigPromocao",
    "calcular_kpis",
    "carregar_config",
    "extrair_chave",
    "filtrar_excecoes",
]

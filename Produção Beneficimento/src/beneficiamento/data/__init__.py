"""Camada de dados do historico de Beneficiamento (SQLite tipado).

Reorganiza o antigo historico_db.py em tres responsabilidades:

- ``schema``: definicao declarativa da tabela, indices e bootstrap do banco.
- ``writer``: persistencia idempotente orientada a dados (FIELD_SPECS).
- ``queries``: leitura por colunas tipadas/indices; o blob JSON
  (``DADOS_COMPLETOS``) fica reservado a auditoria/``include_raw``.
"""

from .queries import (
    buscar_historico,
    descrever_schema_historico,
    explicar_busca_historico,
)
from .schema import HISTORICO_SCHEMA_VERSION, init_db, resolve_db_path
from .writer import salvar_historico

__all__ = [
    "init_db",
    "resolve_db_path",
    "HISTORICO_SCHEMA_VERSION",
    "salvar_historico",
    "buscar_historico",
    "descrever_schema_historico",
    "explicar_busca_historico",
]

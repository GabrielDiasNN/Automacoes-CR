# {
#   "version": "1.0.0",
#   "description": "Excecoes customizadas da automacao OBs Fluxo Sem Tingimento (OFST-06)"
# }
"""Hierarquia de erros do OFST-06.

Todas herdam de `OfstError`, o que permite ao chamador distinguir uma falha de
dominio (dado ruim, schema fora do contrato) de uma falha de infraestrutura
(`oracledb.DatabaseError`, `CircuitBreakerError`), que sobe sem ser mascarada.
"""

from __future__ import annotations


class OfstError(Exception):
    """Base de todas as falhas de dominio do OFST-06."""


class SchemaInvalidoError(OfstError):
    """A query retornou colunas fora do contrato esperado.

    Erro de contrato, nao de dado: aborta a execucao inteira em vez de pular a
    OB — se o schema mudou, nenhuma linha e confiavel.
    """


class DadoIncompletoError(OfstError):
    """Uma linha especifica veio nula/nao-coercivel.

    Escopo de UMA OB: o chamador loga e pula a OB, sem derrubar o lote.
    """

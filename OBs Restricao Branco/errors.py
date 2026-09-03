# {
#   "version": "1.0.0",
#   "description": "Excecoes customizadas da automacao OBs Restrição Branco (ORB-07)"
# }
"""Hierarquia de erros do ORB-07.

Todas herdam de `OrbError`, o que permite ao chamador distinguir uma falha de
dominio (dado ruim, schema fora do contrato) de uma falha de infraestrutura
(`oracledb.DatabaseError`, `CircuitBreakerError`), que sobe sem ser mascarada.
"""

from __future__ import annotations


class OrbError(Exception):
    """Base de todas as falhas de dominio do ORB-07."""


class SchemaInvalidoError(OrbError):
    """A query retornou colunas fora do contrato esperado.

    Erro de contrato, nao de dado: aborta a execucao inteira em vez de pular a
    OB — se o schema mudou, nenhuma linha e confiavel.
    """


class DadoIncompletoError(OrbError):
    """Uma linha especifica veio nula/nao-coercivel.

    Escopo de UMA OB: o chamador loga e pula a OB, sem derrubar o lote.
    """


class ClassificacaoNaoResolvidaError(DadoIncompletoError):
    """A OB veio da query sem `CD_CLASSIFICACAO_COR`.

    Nao e dado corrompido: e o estado TRANSITORIO da montagem. A OB some de
    `VW_EXC_OB_PROD_CLASS_COR` antes de `PEDPRODUCAOOB.OBMONTADA` virar para
    '1', entao por alguns segundos ela ainda entra na query (LEFT JOIN) sem
    classificacao. Observado em 01/09/2026 (OB #185889, montada em curso) e em
    03/09/2026, quando as DUAS unicas OBs do universo estavam nessa janela ao
    mesmo tempo e o lote inteiro foi tratado como dado quebrado — 3 tentativas
    e ExitCode=3 num caso que se resolve sozinho no ciclo seguinte.

    Subclasse de `DadoIncompletoError` para o caminho normal (pular a OB) nao
    mudar; existe para o extrator distinguir "todas as linhas eram OB em
    montagem" (nada a notificar) de "todas as linhas estavam quebradas"
    (abortar sem tocar no state).
    """

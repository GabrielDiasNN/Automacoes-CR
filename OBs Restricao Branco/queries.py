# {
#   "version": "1.0.0",
#   "description": "Carrega os arquivos .sql e monta a query de estoque parametrizada por bind"
# }
"""Acesso as queries SQL do ORB-07.

O SQL vive em arquivos .sql (padrao do repo, auditavel pelo Test-SqlPerformance);
este modulo apenas le e parametriza. Nenhuma regra de negocio aqui.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_OBS_PATH = os.path.join(SCRIPT_DIR, "SQL-ObsRestricaoBranco.sql")
SQL_ESTOQUE_PATH = os.path.join(SCRIPT_DIR, "SQL-EstoqueFinalidadesBranco.sql")
SQL_FINALIDADES_PATH = os.path.join(SCRIPT_DIR, "SQL-FinalidadesCompativeis.sql")
SQL_DIAGNOSTICO_CLASSIFICACOES_PATH = os.path.join(
    SCRIPT_DIR, "SQL-DiagnosticoClassificacoes.sql"
)

IN_BINDS_MARKER = "/*IN_BINDS*/"
FIN_BINDS_MARKER = "/*FIN_BINDS*/"

# ORA-01795 limita uma lista IN a 1000 expressoes; 900 deixa margem.
MAX_IN_BINDS = 900


def load_sql(path: str) -> str:
    """Le um arquivo .sql. Propaga OSError se ausente — o chamador decide o exit code."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def chunk_codigos(codigos: Sequence[int], size: int = MAX_IN_BINDS) -> list[list[int]]:
    """Fatia os codigos em lotes que cabem numa lista IN do Oracle."""
    if size < 1:
        raise ValueError("size deve ser >= 1")
    return [list(codigos[i : i + size]) for i in range(0, len(codigos), size)]


def build_finalidades_sql(
    classificacoes: Sequence[int],
) -> tuple[str, dict[str, Any]]:
    """Monta a consulta das finalidades compativeis com as classificacoes alvo.

    O conjunto de finalidades NAO e fixo no codigo: vem de COR_FINALIDADE, o
    cadastro que o ERP usa para dizer o que pode ser consumido por uma cor de
    cada classificacao.
    """
    if not classificacoes:
        raise ValueError("build_finalidades_sql exige ao menos uma classificacao")

    nomes = [f"K{i}" for i in range(len(classificacoes))]
    sql = load_sql(SQL_FINALIDADES_PATH).replace(
        IN_BINDS_MARKER, ", ".join(f":{n}" for n in nomes)
    )
    return sql, {
        nome: int(codigo) for nome, codigo in zip(nomes, classificacoes, strict=True)
    }


def build_estoque_sql(
    codigos: Sequence[int], finalidades: Sequence[int]
) -> tuple[str, dict[str, Any]]:
    """Monta a query de estoque para N codigos reduzidos e M finalidades.

    Retorna (sql, params). Os nomes de bind (:C0, :F0, ...) sao gerados aqui e
    os valores vao em `params` — nunca interpolados na string.
    """
    if not codigos:
        raise ValueError("build_estoque_sql exige ao menos um codigo reduzido")
    if not finalidades:
        raise ValueError("build_estoque_sql exige ao menos uma finalidade compativel")
    if len(codigos) > MAX_IN_BINDS:
        raise ValueError(
            f"{len(codigos)} codigos excedem o limite de {MAX_IN_BINDS} por lote "
            f"(use chunk_codigos antes de chamar)"
        )

    nomes = [f"C{i}" for i in range(len(codigos))]
    nomes_fin = [f"F{i}" for i in range(len(finalidades))]
    sql = (
        load_sql(SQL_ESTOQUE_PATH)
        .replace(IN_BINDS_MARKER, ", ".join(f":{n}" for n in nomes))
        .replace(FIN_BINDS_MARKER, ", ".join(f":{n}" for n in nomes_fin))
    )
    params: dict[str, Any] = {
        nome: int(codigo) for nome, codigo in zip(nomes, codigos, strict=True)
    }
    params.update(
        {nome: int(fin) for nome, fin in zip(nomes_fin, finalidades, strict=True)}
    )
    return sql, params

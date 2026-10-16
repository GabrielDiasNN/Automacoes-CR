"""Quality Gate Automatizado de Custo e Plano SQL (EXPLAIN PLAN no CI).

Valida estaticamente e via EXPLAIN PLAN os 4 arquivos SQL de produção:
1. Receitas Emitidas/SQL-ReceitasEmitidas.sql
2. OBs Paradas Fase/SQL-ObsParadasFase.sql
3. Receitas Bloqueadas/SQL-ReceitasBloqueadas.sql
4. Montagem de Terceirizados/SQL-MontagemTerceirizados.sql

Regras do Gate:
- Regra 1 (Anti-Cartesiano): Proíbe MERGE JOIN CARTESIAN.
- Regra 2 (Zero Full Scan em Tabelas Críticas): Proíbe TABLE ACCESS FULL em tabelas
  gigantes do SGT (OB_FASES, MOVTO_RECEITA, GERAPECASPRODUTO, OB, PEDPRODUCAOOB).
- Regra 3 (Custo Limite): Custo do CBO deve estar abaixo do teto acordado.
- CI Offline-Safe: Executa validações estáticas e unitárias mesmo sem Oracle ativo.
"""

from __future__ import annotations

import contextlib
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LIB_PYTHON = _ROOT / "lib" / "python"
_TOOLS_ORACLE = _ROOT / "Tools" / "oracle"

if str(_LIB_PYTHON) not in sys.path:
    sys.path.insert(0, str(_LIB_PYTHON))
if str(_TOOLS_ORACLE) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ORACLE))

from oracle_client import (  # noqa: E402  pylint: disable=wrong-import-position
    connect_adaptive,
)

# Arquivos SQL de produção avaliados pelo Quality Gate
SQL_FILES = {
    "Receitas Emitidas": _ROOT / "Receitas Emitidas" / "SQL-ReceitasEmitidas.sql",
    "OBs Paradas Fase": _ROOT / "OBs Paradas Fase" / "SQL-ObsParadasFase.sql",
    "Receitas Bloqueadas": _ROOT / "Receitas Bloqueadas" / "SQL-ReceitasBloqueadas.sql",
    "Montagem de Terceirizados": _ROOT
    / "Montagem de Terceirizados"
    / "SQL-MontagemTerceirizados.sql",
}

# Tabelas gigantes transacionais do ERP SGT que NUNCA devem sofrer TABLE ACCESS FULL
TABELAS_GIGANTES_CRITICAS = {
    "OB_FASES",
    "MOVTO_RECEITA",
    "GERAPECASPRODUTO",
    "OB",
    "PEDPRODUCAOOB",
}

# Custo máximo do CBO para queries de extração do PCP
CUSTO_MAXIMO_PERMITIDO = 500_000


def analisar_plano_execucao(
    plan_rows: Sequence[tuple[Any, ...]],
    custo_maximo: int = CUSTO_MAXIMO_PERMITIDO,
) -> dict[str, Any]:
    """Analisa as linhas de PLAN_TABLE para conformidade arquitetural no Oracle 19c.

    Cada linha é uma tupla: (operation, options, object_name, cost).
    """
    violacoes: list[str] = []
    max_cost = 0

    for row in plan_rows:
        operation = (row[0] or "").strip().upper()
        options = (row[1] or "").strip().upper()
        object_name = (row[2] or "").strip().upper()
        cost = int(row[3]) if row[3] is not None else 0

        max_cost = max(max_cost, cost)

        # Regra 1 (Anti-Cartesiano): Proíbe MERGE JOIN CARTESIAN
        if "CARTESIAN" in options:
            violacoes.append(
                f"Regra 1 (Anti-Cartesiano): Detectado {operation} {options} no plano."
            )

        # Regra 2: Tabelas Críticas Sem Full Scan
        if (
            "TABLE ACCESS" in operation
            and "FULL" in options
            and object_name in TABELAS_GIGANTES_CRITICAS
        ):
            violacoes.append(
                f"Regra 2 (Tabela Crítica): TABLE ACCESS FULL não permitido na tabela gigante '{object_name}'."
            )

    # Regra 3: Custo Limite
    if max_cost > custo_maximo:
        violacoes.append(
            f"Regra 3 (Custo Limite): Custo máximo ({max_cost}) excedeu o teto de {custo_maximo}."
        )

    return {
        "aprovado": len(violacoes) == 0,
        "violacoes": violacoes,
        "max_cost": max_cost,
    }


# ==============================================================================
# 1. VALIDAÇÃO OFFLINE / ESTÁTICA (RODA NO CI SEMPRE, SEM BANCO)
# ==============================================================================


@pytest.mark.parametrize("nome,path", SQL_FILES.items())
def test_sql_files_exist_and_utf8_sem_bom(nome: str, path: Path) -> None:
    """Garante que os arquivos SQL de produção existem e são UTF-8 sem BOM."""
    assert path.exists(), f"Arquivo SQL da automação '{nome}' não encontrado: {path}"

    raw_bytes = path.read_bytes()
    assert (
        len(raw_bytes) > 100
    ), f"Arquivo SQL da automação '{nome}' está vazio ou muito curto."
    assert not raw_bytes.startswith(
        b"\xef\xbb\xbf"
    ), f"Arquivo SQL da automação '{nome}' contém BOM (Byte Order Mark). Deve ser UTF-8 sem BOM."

    content = raw_bytes.decode("utf-8")
    assert "WITH" in content.upper(), f"Query '{nome}' deve usar CTEs (cláusula WITH)."
    assert (
        "SGTPRD." in content.upper()
    ), f"Query '{nome}' deve referenciar o schema SGTPRD explicitamente."


def test_analisador_plano_offline_detecta_cartesian_e_full_scan() -> None:
    """Valida o motor de análise de plano com mocks de sucesso e violação."""
    # Cenário 1: Plano Limpo (Índices e custo baixo)
    plano_limpo = [
        ("SELECT STATEMENT", "", "", 120),
        ("NESTED LOOPS", "", "", 120),
        ("TABLE ACCESS", "BY INDEX ROWID", "OB", 10),
        ("INDEX", "RANGE SCAN", "PK_OB", 2),
        (
            "TABLE ACCESS",
            "FULL",
            "FASES_FLUXO",
            5,
        ),  # Permitido: tabela cadastral pequena
    ]
    res_limpo = analisar_plano_execucao(plano_limpo)
    assert res_limpo["aprovado"] is True
    assert len(res_limpo["violacoes"]) == 0
    assert res_limpo["max_cost"] == 120

    # Cenário 2: Violação Regra 1 (Cartesiano)
    plano_cartesiano = [
        ("SELECT STATEMENT", "", "", 5000),
        ("MERGE JOIN", "CARTESIAN", "", 5000),
    ]
    res_cart = analisar_plano_execucao(plano_cartesiano)
    assert res_cart["aprovado"] is False
    assert any("Anti-Cartesiano" in v for v in res_cart["violacoes"])

    # Cenário 3: Violação Regra 2 (TABLE ACCESS FULL em tabela gigante)
    plano_full_scan = [
        ("SELECT STATEMENT", "", "", 15000),
        ("TABLE ACCESS", "FULL", "OB_FASES", 15000),
    ]
    res_full = analisar_plano_execucao(plano_full_scan)
    assert res_full["aprovado"] is False
    assert any("OB_FASES" in v for v in res_full["violacoes"])

    # Cenário 4: Violação Regra 3 (Custo estourado)
    plano_caro = [
        ("SELECT STATEMENT", "", "", 900_000),
    ]
    res_caro = analisar_plano_execucao(plano_caro, custo_maximo=500_000)
    assert res_caro["aprovado"] is False
    assert any("Custo Limite" in v for v in res_caro["violacoes"])


# ==============================================================================
# 2. VALIDAÇÃO CONECTADA (EXPLAIN PLAN REAL QUANDO O BANCO ESTIVER ACESSÍVEL)
# ==============================================================================


@pytest.fixture(name="oracle_conn_explain", scope="module")
def _conexao_oracle() -> Any:
    """Conexão ao Oracle quando há credenciais e rede; caso contrário, o teste é pulado."""
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING", "dbprd")
    # Sem caminho fixo no código: o padrão vem do .env (ORACLE_CLIENT_LIB_DIR).
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR", "")
    tns_admin = os.environ.get("TNS_ADMIN")

    # Opt-in explícito: as credenciais do .env local apontam para o dbprd, então um
    # `pytest` comum não pode rodar EXPLAIN PLAN em produção sem o dono pedir.
    if os.environ.get("ORACLE_EXPLAIN_REAL") != "1":
        pytest.skip("EXPLAIN PLAN real só com ORACLE_EXPLAIN_REAL=1.")
    if not user or not password:
        pytest.skip(
            "Ambiente sem credenciais Oracle (.env): teste de EXPLAIN PLAN real ignorado."
        )

    try:
        conn = connect_adaptive(
            user=user,
            password=password,
            dsn=dsn,
            client_lib=client_lib,
            tns_admin=tns_admin,
            log_fn=lambda *a, **k: None,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Qualquer falha de rede ou driver significa "ambiente sem banco", não defeito do plano.
        pytest.skip(
            f"Conexão com Oracle na Unifique não disponível no ambiente atual ({exc})."
        )
    yield conn
    with contextlib.suppress(Exception):
        conn.close()


@pytest.mark.parametrize("nome,path", SQL_FILES.items())
def test_explain_plan_conectado_oracle(
    oracle_conn_explain: Any, nome: str, path: Path
) -> None:
    """Executa EXPLAIN PLAN real no Oracle 19c e valida ausência de Cartesian e Full Scan crítico."""
    conn = oracle_conn_explain
    sql = path.read_text(encoding="utf-8").strip().rstrip(";")
    stmt_id = f"CI_COST_{uuid.uuid4().hex[:16]}"

    cursor = conn.cursor()
    try:
        # 1. Gera o plano de execução no banco Oracle 19c
        cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {sql}")

        # 2. Consulta a PLAN_TABLE
        cursor.execute(
            "SELECT OPERATION, OPTIONS, OBJECT_NAME, COST "
            "FROM PLAN_TABLE WHERE STATEMENT_ID = :stmt_id",
            {"stmt_id": stmt_id},
        )
        plan_rows = cursor.fetchall()
        assert plan_rows, f"PLAN_TABLE vazia para a query '{nome}'."

        # 3. Analisa com o Quality Gate
        analise = analisar_plano_execucao(plan_rows)
        assert analise[
            "aprovado"
        ], f"Falha de Quality Gate no plano da query '{nome}':\n" + "\n".join(
            analise["violacoes"]
        )
    finally:
        # 4. Rollback, sem DELETE nem COMMIT: as linhas do EXPLAIN PLAN estão na transação.
        with contextlib.suppress(Exception):
            conn.rollback()
        with contextlib.suppress(Exception):
            cursor.close()

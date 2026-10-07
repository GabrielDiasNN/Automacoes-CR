"""Testes offline dos auxiliares do teste de regressão do PCP mensal.

Cobrem o caminho que dava falso verde: `build_fixed_window_sql` voltando o SQL
inalterado (com SYSDATE) e a comparação com a baseline sendo pulada.
"""

import copy
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

_TESTE = (
    Path(__file__).resolve().parent / "test_consultas_pcp_producao_mensal_regression.py"
)


def _carregar() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pcp_regressao_helpers", _TESTE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pcp_regressao_helpers"] = module
    spec.loader.exec_module(module)
    return module


reg = _carregar()


def _janela_fixa(sql: str) -> str:
    resultado: str = reg.build_fixed_window_sql(sql)
    return resultado


def test_janela_fixa_substitui_a_cte_do_sql_real() -> None:
    bruto = reg.SQL_FILE.read_text(encoding="utf-8")

    fixo = _janela_fixa(bruto)

    assert fixo != bruto
    assert "TO_DATE('01-09-2026', 'DD-MM-YYYY') AS DT_INICIO" in fixo
    assert (
        "SYSDATE" not in fixo.split("BASE_FASES_AGR AS (")[0].split("WITH JANELA")[-1]
    )


def test_janela_fixa_sem_base_fases_agr_falha() -> None:
    sql = "WITH JANELA AS (SELECT SYSDATE AS DT_INICIO FROM DUAL), OUTRA AS (SELECT 1 FROM DUAL) SELECT 1 FROM DUAL"

    with pytest.raises(ValueError, match="janela fixa não foi aplicada"):
        _janela_fixa(sql)


def test_janela_fixa_com_cte_extra_entre_janela_e_base_falha() -> None:
    sql = (
        "WITH JANELA AS (SELECT SYSDATE AS DT_INICIO FROM DUAL), "
        "EXTRA AS (SELECT 1 AS X FROM DUAL), "
        "BASE_FASES_AGR AS (SELECT 1 FROM DUAL) SELECT 1 FROM BASE_FASES_AGR"
    )

    with pytest.raises(ValueError, match="apagaria"):
        _janela_fixa(sql)


def test_comparacao_com_competencia_divergente_falha() -> None:
    fixture = reg.load_baseline_fixture()
    linhas: list[dict[str, Any]] = copy.deepcopy(fixture["rows"])
    for linha in linhas:
        linha["COMPETENCIA"] = "10-2026"

    with pytest.raises(AssertionError, match="difere da baseline"):
        reg.compare_results_against_fixture(linhas, fixture)


def test_comparacao_com_resultado_vazio_falha_legivel() -> None:
    fixture = reg.load_baseline_fixture()

    with pytest.raises(AssertionError, match="0 linhas"):
        reg.compare_results_against_fixture([], fixture)


def test_comparacao_identica_a_baseline_passa() -> None:
    fixture = reg.load_baseline_fixture()

    reg.compare_results_against_fixture(copy.deepcopy(fixture["rows"]), fixture)


def test_comparacao_detecta_numero_divergente() -> None:
    fixture = reg.load_baseline_fixture()
    linhas: list[dict[str, Any]] = copy.deepcopy(fixture["rows"])
    linhas[0]["QT_KG"] = (linhas[0]["QT_KG"] or 0) + 5

    with pytest.raises(AssertionError, match="divergências"):
        reg.compare_results_against_fixture(linhas, fixture)


def test_execucao_oracle_delega_a_execute_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[dict[str, Any]] = []

    resultado = SimpleNamespace(
        columns=["A"], rows=[(1,)], metadata={"elapsed_seconds": 0.5}
    )

    def falso(sql: str, **kwargs: Any) -> SimpleNamespace:
        chamadas.append({"sql": sql, **kwargs})
        return resultado

    monkeypatch.setattr(reg, "execute_query", falso)

    colunas, linhas, duracao_ms = reg.run_oracle_with_retry("  SELECT 1 FROM DUAL ;  ")

    assert (colunas, linhas, duracao_ms) == (["A"], [(1,)], 500.0)
    assert chamadas[0]["sql"] == "SELECT 1 FROM DUAL"
    assert chamadas[0]["wall_clock_budget_seconds"] == reg.ORACLE_BUDGET_SECONDS


@pytest.mark.parametrize(
    "nome",
    [
        "test_oracle_database_invariants",
        "test_fixed_window_historical_regression",
        "test_live_oracle_execution",
    ],
)
def test_testes_que_tocam_oracle_exigem_opt_in(nome: str) -> None:
    marcas = getattr(reg, nome).pytestmark

    assert any(m.name == "skipif" for m in marcas)

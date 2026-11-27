"""Testes unitários de Tools/oracle/oracle_queue_tools.py: prazo do modo queue.

Trocam `execute_query` por um falso que só anota o `timeout_seconds` recebido: não
tocam a fila, o TSplus nem o Oracle.
"""

import time
from typing import Any

import oracle_queue
import pytest
from oracle_queue import OracleQueueTimeoutError, QueueResult
from tests.carregadores_modulos import carregar_tool_oracle as _carregar

# oracle_queue_tools faz `from guard_sql import ...`, e Tools/oracle não está no
# pythonpath do pytest.ini: carregar guard_sql antes o registra em sys.modules pelo
# nome curto, e o import do oracle_queue_tools o encontra lá.
_carregar("guard_sql")
oqt = _carregar("oracle_queue_tools")

pytestmark = pytest.mark.unitario

SQL = "SELECT 1 AS X FROM DUAL"
PRAZO_ENV = "ORACLE_QUEUE_DEADLINE_EPOCH"


@pytest.fixture(name="timeouts")
def _timeouts(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Registra o `timeout_seconds` de cada chamada a `execute_query` do módulo."""
    recebidos: list[float] = []

    def falso(*_args: Any, timeout_seconds: float, **_kwargs: Any) -> QueueResult:
        recebidos.append(timeout_seconds)
        return QueueResult(columns=["X"], types=["number"], rows=[])

    monkeypatch.setattr(oqt, "execute_query", falso)
    monkeypatch.delenv(PRAZO_ENV, raising=False)
    return recebidos


def test_timeout_pedido_chega_inteiro_sem_prazo_global(timeouts: list[float]) -> None:
    """Antes do fix, 300 s virava 120 s em silêncio."""
    oqt.executar_consulta_fila(SQL, timeout=300)

    assert timeouts == [300.0]


def test_explicar_plano_respeita_timeout_pedido(timeouts: list[float]) -> None:
    oqt.explicar_plano_fila(SQL, timeout=300)

    assert timeouts == [300.0]


def test_verificar_objetos_respeita_timeout_pedido(timeouts: list[float]) -> None:
    motivo = oqt.verificar_objetos_fila("SELECT 1 FROM DUAL", timeout=300)

    assert motivo is None
    assert timeouts == [300.0]


def test_timeout_abaixo_de_um_segundo_sobe_para_o_minimo(
    timeouts: list[float],
) -> None:
    oqt.executar_consulta_fila(SQL, timeout=0.1)

    assert timeouts == [1.0]


def test_prazo_global_de_dez_segundos_limita_o_pedido_de_trezentos(
    monkeypatch: pytest.MonkeyPatch, timeouts: list[float]
) -> None:
    monkeypatch.setenv(PRAZO_ENV, str(time.time() + 10))

    oqt.executar_consulta_fila(SQL, timeout=300)

    assert len(timeouts) == 1
    assert 9.0 < timeouts[0] <= 10.0


def test_prazo_global_vencido_nao_chama_a_fila(
    monkeypatch: pytest.MonkeyPatch, timeouts: list[float]
) -> None:
    monkeypatch.setenv(PRAZO_ENV, str(time.time() - 5))

    with pytest.raises(OracleQueueTimeoutError, match="ORACLE_QUEUE_DEADLINE_EPOCH"):
        oqt.executar_consulta_fila(SQL, timeout=300)

    assert timeouts == []


def test_limitar_linhas_sql_foi_removida() -> None:
    assert not hasattr(oqt, "limitar_linhas_sql")


def test_modulo_usa_a_mesma_regra_de_prazo_da_lib() -> None:
    """`apply_queue_deadline` vem da lib: o módulo de ferramentas usa a mesma regra."""
    assert oqt.apply_queue_deadline is oracle_queue.apply_queue_deadline

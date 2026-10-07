"""Testes unitarios da nova tentativa do `beneficiamento.oracle.execute_query`."""

import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import oracledb
import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from beneficiamento import (  # noqa: E402  pylint: disable=wrong-import-position
    oracle,
)

_SESSION_DROP = "DPY-4011: the database or network closed the connection\nDPI-1080: connection was closed by ORA-00028"


def _ok_result() -> Any:
    return oracle.QueryResult(
        columns=["A"], rows=[(1,)], duplicate_columns={}, metadata={"row_count": 1}
    )


def _scripted(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> list[int]:
    """Substitui `_execute_once` por uma sequência de falhas/sucessos; devolve
    a lista de chamadas para o teste contar tentativas."""
    calls: list[int] = []

    def fake(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(1)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(oracle, "_execute_once", fake)
    return calls


def test_sessao_derrubada_tenta_de_novo_e_registra_tentativas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _scripted(
        monkeypatch, [oracledb.DatabaseError(_SESSION_DROP), _ok_result()]
    )

    result = oracle.execute_query("SELECT 1 FROM DUAL")

    assert len(calls) == 2
    assert result.metadata["attempts"] == 2


def test_sessao_perdida_como_interface_error_tambem_e_repetida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DPY-1001 (e DPI-1010, remapeado para ele) chega como InterfaceError, que
    # não é subclasse de DatabaseError.
    calls = _scripted(
        monkeypatch,
        [oracledb.InterfaceError("DPY-1001: not connected to database"), _ok_result()],
    )

    result = oracle.execute_query("SELECT 1 FROM DUAL")

    assert len(calls) == 2
    assert result.metadata["attempts"] == 2


def test_erro_de_sql_nao_e_repetido(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _scripted(
        monkeypatch, [oracledb.DatabaseError("ORA-00942: table or view does not exist")]
    )

    with pytest.raises(oracledb.DatabaseError, match="ORA-00942"):
        oracle.execute_query("SELECT 1 FROM NAO_EXISTE")

    assert len(calls) == 1


def test_orcamento_de_tempo_estourado_nao_e_repetido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _scripted(
        monkeypatch, [TimeoutError("Consulta Beneficiamento excedeu 19s.")]
    )

    with pytest.raises(TimeoutError):
        oracle.execute_query("SELECT 1 FROM DUAL")

    assert len(calls) == 1


def test_desiste_apos_o_limite_de_tentativas(monkeypatch: pytest.MonkeyPatch) -> None:
    drops = [
        oracledb.DatabaseError(_SESSION_DROP) for _ in range(oracle.MAX_QUERY_ATTEMPTS)
    ]
    calls = _scripted(monkeypatch, drops)

    with pytest.raises(oracledb.DatabaseError, match="ORA-00028"):
        oracle.execute_query("SELECT 1 FROM DUAL")

    assert len(calls) == oracle.MAX_QUERY_ATTEMPTS


def _fake_clock(monkeypatch: pytest.MonkeyPatch, values: list[float]) -> None:
    """Relogio falso que devolve `values` em ordem e repete o ultimo valor, sem
    esgotar, para nao depender do numero exato de leituras. Troca apenas
    `oracle.time` por um stub, sem tocar o modulo `time` global."""

    def perf_counter() -> float:
        return values.pop(0) if len(values) > 1 else values[0]

    monkeypatch.setattr(oracle, "time", SimpleNamespace(perf_counter=perf_counter))


def _scripted_with_kwargs(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake(*_args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(oracle, "_execute_once", fake)
    return calls


def test_segunda_tentativa_recebe_apenas_o_orcamento_restante(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tentativa 1 cai aos 12 s de um orcamento de 19 s: a 2a recebe 7 s e um
    call_timeout limitado a 7 s (nao os 19 s / 18 s cheios)."""
    calls = _scripted_with_kwargs(
        monkeypatch, [oracledb.DatabaseError(_SESSION_DROP), _ok_result()]
    )
    _fake_clock(monkeypatch, [0.0, 12.0])

    result = oracle.execute_query(
        "SELECT 1 FROM DUAL", oracle_timeout_ms=18000, wall_clock_budget_seconds=19
    )

    assert len(calls) == 2
    assert calls[0]["wall_clock_budget_seconds"] == 19
    assert calls[0]["oracle_timeout_ms"] == 18000
    assert calls[1]["wall_clock_budget_seconds"] == pytest.approx(7.0)
    assert calls[1]["oracle_timeout_ms"] == 7000
    assert result.metadata["attempts"] == 2


def test_call_timeout_menor_que_o_restante_e_preservado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _scripted_with_kwargs(
        monkeypatch, [oracledb.DatabaseError(_SESSION_DROP), _ok_result()]
    )
    _fake_clock(monkeypatch, [0.0, 2.0])

    oracle.execute_query(
        "SELECT 1 FROM DUAL", oracle_timeout_ms=5000, wall_clock_budget_seconds=19
    )

    assert calls[1]["oracle_timeout_ms"] == 5000
    assert calls[1]["wall_clock_budget_seconds"] == pytest.approx(17.0)


def test_nao_tenta_de_novo_quando_o_restante_e_menor_que_o_minimo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma queda aos 17 s de 19 s (restam 2 s < minimo) nao dispara nova
    tentativa, que estouraria o limite de 45 s do Orchestrator."""
    calls = _scripted_with_kwargs(
        monkeypatch, [oracledb.DatabaseError(_SESSION_DROP), _ok_result()]
    )
    _fake_clock(monkeypatch, [0.0, 19 - oracle.MIN_RETRY_REMAINING_SECONDS + 1])

    with pytest.raises(oracledb.DatabaseError):
        oracle.execute_query("SELECT 1 FROM DUAL", wall_clock_budget_seconds=19)

    assert len(calls) == 1


def test_tenta_de_novo_quando_o_restante_e_exatamente_o_minimo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _scripted_with_kwargs(
        monkeypatch, [oracledb.DatabaseError(_SESSION_DROP), _ok_result()]
    )
    _fake_clock(monkeypatch, [0.0, 19 - oracle.MIN_RETRY_REMAINING_SECONDS])

    oracle.execute_query("SELECT 1 FROM DUAL", wall_clock_budget_seconds=19)

    assert len(calls) == 2
    assert calls[1]["wall_clock_budget_seconds"] == pytest.approx(
        oracle.MIN_RETRY_REMAINING_SECONDS
    )


@pytest.mark.parametrize("marcador", ["ORA-03113", "ORA-03135", "DPY-1001", "DPI-1010"])
def test_is_session_drop_reconhece_a_lista_compartilhada(marcador: str) -> None:
    assert oracle._is_session_drop(  # pylint: disable=protected-access
        oracledb.DatabaseError(f"{marcador}: conexao perdida")
    )


def test_is_session_drop_ignora_erro_de_sql() -> None:
    assert not oracle._is_session_drop(  # pylint: disable=protected-access
        oracledb.DatabaseError("ORA-00942: tabela ou view nao existe")
    )


class _ConexaoSemCallTimeout:
    """Simula o Oracle Client 12.2: `call_timeout` não existe; `execute` só
    volta quando `cancel()` é chamado (ou nunca, se ninguém cancelar)."""

    def __init__(self, bloqueia: bool) -> None:
        self.bloqueia = bloqueia
        self.cancelada = threading.Event()
        self.cursor_falso = _CursorBloqueante(self)

    @property
    def call_timeout(self) -> int:
        return 0

    @call_timeout.setter
    def call_timeout(self, _valor: int) -> None:
        raise oracledb.DatabaseError(
            "DPI-1050: Oracle Client library is at version 12.2"
        )

    def cancel(self) -> None:
        self.cancelada.set()

    def cursor(self) -> "_CursorBloqueante":
        return self.cursor_falso

    def __enter__(self) -> "_ConexaoSemCallTimeout":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _CursorBloqueante:
    description = [("A",)]
    arraysize = 0

    def __init__(self, conexao: _ConexaoSemCallTimeout) -> None:
        self._conexao = conexao
        self._entregue = False

    def __enter__(self) -> "_CursorBloqueante":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, *_a: Any, **_k: Any) -> None:
        if self._conexao.bloqueia:
            assert self._conexao.cancelada.wait(timeout=5), "watchdog nunca cancelou"
            raise oracledb.DatabaseError("ORA-01013: cancelado pelo usuario")

    def fetchmany(self, _n: int) -> list[tuple[int]]:
        if self._entregue:
            return []
        self._entregue = True
        return [(1,)]


def test_watchdog_cancela_execute_travado_e_vira_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conexao = _ConexaoSemCallTimeout(bloqueia=True)
    monkeypatch.setattr(oracle, "connect_readonly", lambda: conexao)
    with pytest.raises(TimeoutError, match="watchdog"):
        oracle.execute_query("select 1", wall_clock_budget_seconds=0.3)
    assert conexao.cancelada.is_set()


def test_watchdog_nao_atrapalha_consulta_rapida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conexao = _ConexaoSemCallTimeout(bloqueia=False)
    monkeypatch.setattr(oracle, "connect_readonly", lambda: conexao)
    resultado = oracle.execute_query("select 1", wall_clock_budget_seconds=5)
    assert resultado.rows == [(1,)]
    assert resultado.metadata["oracle_timeout_applied"] is False
    assert resultado.metadata["oracle_watchdog_applied"] is True
    assert not conexao.cancelada.is_set()


def test_erro_oracle_sem_watchdog_continua_sendo_erro_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conexao = _ConexaoSemCallTimeout(bloqueia=False)

    def falha(*_a: Any, **_k: Any) -> None:
        raise oracledb.DatabaseError("ORA-00942: tabela ou view nao existe")

    monkeypatch.setattr(conexao.cursor_falso, "execute", falha)
    monkeypatch.setattr(oracle, "connect_readonly", lambda: conexao)
    with pytest.raises(oracledb.DatabaseError, match="ORA-00942"):
        oracle.execute_query("select 1", wall_clock_budget_seconds=5)


class _ConexaoRastreada:
    """Conexão mínima que registra o fechamento."""

    def __init__(self) -> None:
        self.fechada = threading.Event()

    def close(self) -> None:
        self.fechada.set()

    def __enter__(self) -> "_ConexaoRastreada":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def test_connect_com_prazo_estourado_vira_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    liberar = threading.Event()
    conexao = _ConexaoRastreada()

    def conecta_devagar() -> _ConexaoRastreada:
        liberar.wait(timeout=5)
        return conexao

    monkeypatch.setattr(oracle, "connect_readonly", conecta_devagar)
    with pytest.raises(TimeoutError, match="Conexão Oracle"):
        oracle.execute_query("select 1", wall_clock_budget_seconds=0.2)
    # a conexão que chega depois do prazo é fechada pela thread abandonada
    liberar.set()
    assert conexao.fechada.wait(timeout=2)


def test_connect_rapido_devolve_a_conexao(monkeypatch: pytest.MonkeyPatch) -> None:
    conexao = _ConexaoRastreada()
    monkeypatch.setattr(oracle, "connect_readonly", lambda: conexao)
    assert oracle._connect_within(2) is conexao  # pylint: disable=protected-access


def test_connect_com_erro_repassa_a_excecao_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def falha() -> Any:
        raise oracledb.DatabaseError("DPY-4011: rede fechou")

    monkeypatch.setattr(oracle, "connect_readonly", falha)
    with pytest.raises(oracledb.DatabaseError, match="DPY-4011"):
        oracle._connect_within(2)  # pylint: disable=protected-access


def test_watchdog_espera_o_cancel_em_curso_antes_de_liberar_a_conexao() -> None:
    ordem: list[str] = []

    class Conexao:  # pylint: disable=too-few-public-methods
        def cancel(self) -> None:
            ordem.append("cancel-inicio")
            threading.Event().wait(0.3)
            ordem.append("cancel-fim")

    disparou = threading.Event()
    # pylint: disable-next=protected-access
    with oracle._cancel_after(Conexao(), 0.05, disparou):
        assert disparou.wait(timeout=2)  # o timer já entrou no cancel()
    ordem.append("saiu")
    assert ordem == ["cancel-inicio", "cancel-fim", "saiu"]

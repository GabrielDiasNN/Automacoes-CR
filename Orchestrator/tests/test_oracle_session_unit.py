"""Testes unitarios de lib/python/oracle_session.py (sem tocar o Oracle)."""

import threading
from typing import Any

import oracle_session
import oracledb
import pytest

pytestmark = pytest.mark.unitario


@pytest.mark.parametrize("marcador", oracle_session.SESSION_DROP_MARKERS)
def test_is_session_drop_reconhece_a_lista_compartilhada(marcador: str) -> None:
    assert oracle_session.is_session_drop(
        oracledb.DatabaseError(f"{marcador}: conexao perdida")
    )
    assert oracle_session.is_session_drop(f"erro {marcador.lower()} qualquer")


def test_is_session_drop_ignora_erro_de_sql() -> None:
    assert not oracle_session.is_session_drop(
        oracledb.DatabaseError("ORA-00942: tabela ou view nao existe")
    )
    # Cancelamento por prazo nao e queda de rede.
    assert not oracle_session.is_session_drop("ORA-01013: user requested cancel")


class _Conexao:
    def __init__(self) -> None:
        self.canceladas = 0
        self.fechada = threading.Event()

    def cancel(self) -> None:
        self.canceladas += 1

    def close(self) -> None:
        self.fechada.set()


def test_connect_within_devolve_a_conexao() -> None:
    conexao = _Conexao()
    assert oracle_session.connect_within(lambda: conexao, 2) is conexao


def test_connect_within_repassa_a_excecao_original() -> None:
    def falha() -> Any:
        raise oracledb.DatabaseError("DPY-4011: rede fechou")

    with pytest.raises(oracledb.DatabaseError, match="DPY-4011"):
        oracle_session.connect_within(falha, 2)


def test_connect_within_fecha_conexao_que_chega_depois_do_prazo() -> None:
    liberar = threading.Event()
    conexao = _Conexao()

    def conecta_devagar() -> _Conexao:
        liberar.wait(timeout=5)
        return conexao

    with pytest.raises(TimeoutError, match="Conexão Oracle"):
        oracle_session.connect_within(conecta_devagar, 0.1)
    liberar.set()
    assert conexao.fechada.wait(timeout=2)


def test_cancel_after_espera_o_cancel_em_curso_antes_de_liberar() -> None:
    ordem: list[str] = []

    class Conexao:  # pylint: disable=too-few-public-methods
        def cancel(self) -> None:
            ordem.append("cancel-inicio")
            threading.Event().wait(0.3)
            ordem.append("cancel-fim")

    disparou = threading.Event()
    with oracle_session.cancel_after(Conexao(), 0.05, disparou):
        assert disparou.wait(timeout=2)  # o timer ja entrou no cancel()
    ordem.append("saiu")
    assert ordem == ["cancel-inicio", "cancel-fim", "saiu"]


def test_run_with_cancel_devolve_valor_e_erro() -> None:
    conexao = _Conexao()
    ok = oracle_session.run_with_cancel(lambda: 42, lambda: conexao, 2)
    assert (ok.value, ok.error, ok.timed_out) == (42, None, False)

    def falha() -> Any:
        raise ValueError("ruim")

    erro = oracle_session.run_with_cancel(falha, lambda: conexao, 2)
    assert isinstance(erro.error, ValueError) and not erro.timed_out
    assert conexao.canceladas == 0


def test_run_with_cancel_cancela_no_prazo() -> None:
    liberar = threading.Event()
    conexao = _Conexao()
    conexao.cancel = liberar.set  # type: ignore[method-assign]

    resultado = oracle_session.run_with_cancel(
        lambda: liberar.wait(timeout=5), lambda: conexao, 0.1
    )
    assert resultado.timed_out and not resultado.abandoned


def test_run_with_cancel_sem_conexao_nao_espera_a_thread() -> None:
    liberar = threading.Event()
    try:
        resultado = oracle_session.run_with_cancel(
            lambda: liberar.wait(timeout=5), lambda: None, 0.1
        )
        assert resultado.timed_out and resultado.abandoned
    finally:
        liberar.set()

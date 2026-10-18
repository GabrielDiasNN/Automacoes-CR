"""Testes unitarios de lib/python/oracle_session.py (sem tocar o Oracle)."""

import threading
from typing import Any
from unittest.mock import MagicMock

import oracle_client
import oracle_session
import oracledb
import pytest
from oracle_client import DriverMode

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
    call_timeout: int | None = None

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


def _modo(monkeypatch: pytest.MonkeyPatch, modo: DriverMode) -> None:
    monkeypatch.setattr(oracle_session, "describe_driver_mode", lambda: modo)


def test_call_timeout_nativo_no_thin(monkeypatch: pytest.MonkeyPatch) -> None:
    _modo(monkeypatch, DriverMode("thin", "Thin", None))
    assert oracle_session.supports_native_call_timeout() is True


@pytest.mark.parametrize(
    ("versao", "esperado"),
    [
        ((12, 2, 0, 1, 0), False),
        ((18, 0, 0, 0, 0), False),
        ((18, 1, 0, 0, 0), True),
        ((19, 25, 0, 0, 0), True),
    ],
)
def test_call_timeout_nativo_no_thick_exige_client_18_1(
    monkeypatch: pytest.MonkeyPatch, versao: tuple[int, ...], esperado: bool
) -> None:
    _modo(monkeypatch, DriverMode("thick", "Thick", versao))
    assert oracle_session.supports_native_call_timeout() is esperado


@pytest.mark.parametrize(
    "mensagem",
    [
        "DPY-4024: call timeout of 1000 ms exceeded",
        "DPI-1067: call timeout of 1000 ms exceeded",
        "call timeout of 1000 ms exceeded",
    ],
)
def test_is_call_timeout_reconhece_o_prazo_do_driver(mensagem: str) -> None:
    assert oracle_session.is_call_timeout(mensagem)


def test_is_call_timeout_ignora_queda_de_sessao() -> None:
    assert not oracle_session.is_call_timeout(
        "ORA-03113: end-of-file on communication channel"
    )


def test_call_deadline_nativo_define_e_zera_call_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _modo(monkeypatch, DriverMode("thin", "Thin", None))
    conexao = _Conexao()
    disparou = threading.Event()
    with oracle_session.call_deadline(conexao, 2.5, disparou):
        assert conexao.call_timeout == 2500
    assert conexao.call_timeout == 0
    assert not disparou.is_set()


def test_call_deadline_nativo_marca_disparo_no_erro_de_prazo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _modo(monkeypatch, DriverMode("thin", "Thin", None))
    conexao = _Conexao()
    disparou = threading.Event()
    with (
        pytest.raises(oracledb.DatabaseError, match="DPY-4024"),
        oracle_session.call_deadline(conexao, 1, disparou),
    ):
        raise oracledb.DatabaseError("DPY-4024: call timeout of 1000 ms exceeded")
    assert disparou.is_set()
    assert conexao.call_timeout == 0


def test_call_deadline_nativo_nao_marca_erro_comum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _modo(monkeypatch, DriverMode("thin", "Thin", None))
    conexao = _Conexao()
    disparou = threading.Event()
    with (
        pytest.raises(oracledb.DatabaseError, match="ORA-00942"),
        oracle_session.call_deadline(conexao, 1, disparou),
    ):
        raise oracledb.DatabaseError("ORA-00942: tabela ou view nao existe")
    assert not disparou.is_set()


def test_call_deadline_sem_suporte_cancela_pela_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oracle Client 12.2: sem call_timeout, o prazo cai no cancel_after por thread."""
    _modo(monkeypatch, DriverMode("thick", "Thick 12.2", (12, 2, 0, 1, 0)))
    conexao = _Conexao()
    disparou = threading.Event()
    with oracle_session.call_deadline(conexao, 0.05, disparou):
        assert disparou.wait(timeout=2)
    assert conexao.canceladas == 1
    assert conexao.call_timeout is None


def test_cancel_tardio_depois_do_bloco_nao_cancela_a_conexao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disparos: list[Any] = []

    class _TimerFalso:  # pylint: disable=too-few-public-methods
        def __init__(self, _segundos: float, funcao: Any) -> None:
            disparos.append(funcao)
            self.daemon = False

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

        def join(self, _timeout: float | None = None) -> None:
            return None

    monkeypatch.setattr(threading, "Timer", _TimerFalso)
    conexao = MagicMock(name="conexao")
    disparado = threading.Event()

    with oracle_session.cancel_after(conexao, 1.0, disparado):
        pass
    # Simula o timer que chega depois do fim do bloco (janela que o achado apontou).
    disparos[0]()

    conexao.cancel.assert_not_called()
    assert not disparado.is_set()


class _ConexaoOci:  # pylint: disable=too-few-public-methods
    def __init__(self) -> None:
        self.module = self.action = self.client_identifier = ""
        self.client_info = self.db_op = ""


def test_aplicar_metadados_oci_trunca_nos_limites_do_oracle() -> None:
    conexao = _ConexaoOci()
    erro = oracle_client.aplicar_metadados_oci(
        conexao,
        modulo="M" * 100,
        acao="A" * 100,
        identificador="I" * 100,
        db_op="D" * 100,
    )
    assert erro is None
    assert len(conexao.module) == 64
    assert len(conexao.action) == 64
    assert len(conexao.client_identifier) == 64
    assert len(conexao.db_op) == 32
    assert conexao.client_info.startswith("PID:")


def test_aplicar_metadados_oci_falha_do_driver_vira_mensagem_sem_excecao() -> None:
    class _Recusa:  # pylint: disable=too-few-public-methods
        def __setattr__(self, nome: str, valor: Any) -> None:
            raise AttributeError(f"atributo {nome} recusado pelo servidor")

    erro = oracle_client.aplicar_metadados_oci(
        _Recusa(), modulo="m", acao="a", identificador="i", db_op="d"
    )
    assert erro is not None
    assert "recusado" in erro


def test_cancel_after_consome_break_quando_o_prazo_coincide_com_o_fim() -> None:
    """Prazo estourado no instante em que a chamada terminou: o ping limpa o break."""

    class Conexao:  # pylint: disable=too-few-public-methods
        def __init__(self) -> None:
            self.pings = 0

        def cancel(self) -> None:
            return None

        def ping(self) -> None:
            self.pings += 1

    conexao = Conexao()
    disparou = threading.Event()
    with oracle_session.cancel_after(conexao, 0.05, disparou):
        assert disparou.wait(timeout=2)
    assert conexao.pings == 1


def test_cancel_after_sem_disparo_nao_faz_ping() -> None:
    class Conexao:  # pylint: disable=too-few-public-methods
        def __init__(self) -> None:
            self.pings = 0

        def ping(self) -> None:
            self.pings += 1

    conexao = Conexao()
    with oracle_session.cancel_after(conexao, 5, threading.Event()):
        pass
    assert conexao.pings == 0


def test_call_timeout_aplicado_zera_ao_sair() -> None:
    """Regressão (achado 14): fonte única aplica e zera o call_timeout."""
    conexao = MagicMock()
    with oracle_session.call_timeout_aplicado(conexao, 2.5) as info:
        assert info.applied is True
        assert conexao.call_timeout == 2500
    assert conexao.call_timeout == 0


def test_call_timeout_aplicado_devolve_aviso_quando_driver_recusa() -> None:
    class _Client122:  # pylint: disable=too-few-public-methods
        @property
        def call_timeout(self) -> int:
            return 0

        @call_timeout.setter
        def call_timeout(self, _valor: int) -> None:
            raise RuntimeError("DPI-1050: Oracle Client library is at version 12.2")

    with oracle_session.call_timeout_aplicado(_Client122(), 1.0) as info:
        assert info.applied is False
        assert "DPI-1050" in info.warning


def test_query_deadline_arma_watchdog_e_zera_call_timeout() -> None:
    conexao = MagicMock()
    disparou = threading.Event()
    with oracle_session.query_deadline(conexao, 10.0, 3.0, disparou) as info:
        assert info.applied is True
        assert conexao.call_timeout == 3000  # o menor dos dois prazos
    assert conexao.call_timeout == 0
    assert not disparou.is_set()


def test_query_deadline_marca_disparo_no_prazo_por_chamada_do_driver() -> None:
    """Regressão (achado 8): DPY-4024 do call_timeout nativo seta `fired` como o watchdog."""
    conexao = MagicMock()
    disparou = threading.Event()
    with (
        pytest.raises(oracledb.Error, match="DPY-4024"),
        oracle_session.query_deadline(conexao, 1.0, 3.0, disparou),
    ):
        raise oracledb.DatabaseError("DPY-4024: call timeout of 1000 ms exceeded")
    assert disparou.is_set()


def test_query_deadline_nao_marca_disparo_em_erro_comum() -> None:
    conexao = MagicMock()
    disparou = threading.Event()
    with (
        pytest.raises(oracledb.Error, match="ORA-00942"),
        oracle_session.query_deadline(conexao, 1.0, 3.0, disparou),
    ):
        raise oracledb.DatabaseError("ORA-00942: tabela ou view nao existe")
    assert not disparou.is_set()

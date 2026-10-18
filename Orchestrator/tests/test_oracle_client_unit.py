"""Testes unitarios de lib/python/oracle_client.py (sem tocar o Oracle).

O driver e substituido por um estado falso: o modo thin/thick, as chamadas
de `init_oracle_client` e as falhas de `connect` sao controlados pelo teste.
"""

from typing import Any

import oracle_client
import oracledb
import pytest

pytestmark = pytest.mark.unitario

_MENSAGEM_DPY3015 = (
    "DPY-3015: password verifier type 0x939 is not supported by "
    "python-oracledb in thin mode"
)


class _Driver:
    """Estado falso do driver: modo ativo e registro das chamadas."""

    def __init__(self) -> None:
        self.thin = True
        self.chamadas: list[str] = []
        self.falhas_connect: list[BaseException] = []
        self.init_erro: BaseException | None = None
        self.init_args: tuple[str, str | None] | None = None
        self.ultimos_kwargs: dict[str, Any] = {}

    def is_thin_mode(self) -> bool:
        return self.thin

    def init_oracle_client(self, lib_dir: str, config_dir: str | None = None) -> None:
        self.chamadas.append("init")
        self.init_args = (lib_dir, config_dir)
        if self.init_erro is not None:
            raise self.init_erro
        self.thin = False

    def connect(self, **kwargs: Any) -> str:
        self.chamadas.append("connect")
        self.ultimos_kwargs = kwargs
        if self.falhas_connect:
            raise self.falhas_connect.pop(0)
        return "CONEXAO"


@pytest.fixture(name="driver")
def _driver_fixture(monkeypatch: pytest.MonkeyPatch) -> _Driver:
    estado = _Driver()
    monkeypatch.setattr(oracledb, "is_thin_mode", estado.is_thin_mode)
    monkeypatch.setattr(oracledb, "init_oracle_client", estado.init_oracle_client)
    monkeypatch.setattr(oracledb, "connect", estado.connect)
    monkeypatch.delenv("ORACLE_DRIVER_MODE", raising=False)
    # Estado do processo zerado a cada teste: nenhuma conexão anterior fixa o modo Thin.
    monkeypatch.setattr(oracle_client, "_ESTADO", {"thin_consolidado": False})
    return estado


def _silencio(*_a: Any, **_k: Any) -> None:
    return None


def _conectar() -> Any:
    return oracle_client.connect_adaptive(
        user="usuario_teste",
        password="",
        dsn="dbprd",
        client_lib="instantclient_19c",
        tns_admin="instantclient_19c/network/admin",
        log_fn=_silencio,
    )


def test_thin_sucesso_nao_ativa_thick_e_usa_prazos_de_rede(driver: _Driver) -> None:
    assert _conectar() == "CONEXAO"
    assert driver.chamadas == ["connect"]
    assert driver.ultimos_kwargs["tcp_connect_timeout"] == 15.0
    assert "retry_count" not in driver.ultimos_kwargs
    assert driver.ultimos_kwargs["expire_time"] == 2
    assert driver.ultimos_kwargs["config_dir"] == "instantclient_19c/network/admin"


def test_dpy3015_ativa_thick_e_reconecta_sem_config_dir(driver: _Driver) -> None:
    driver.falhas_connect.append(oracledb.NotSupportedError(_MENSAGEM_DPY3015))
    avisos: list[str] = []

    def registra(msg: str, lvl: str = "INFO") -> None:
        if lvl == "WARN":
            avisos.append(msg)

    resultado: Any = oracle_client.connect_adaptive(
        user="u",
        password="",
        dsn="dbprd",
        client_lib="instantclient_19c",
        tns_admin="instantclient_19c/network/admin",
        log_fn=registra,
    )

    assert resultado == "CONEXAO"
    assert driver.chamadas == ["connect", "init", "connect"]
    assert driver.init_args == ("instantclient_19c", "instantclient_19c/network/admin")
    # Depois do init, o diretório do tnsnames vai para init_oracle_client, não para connect.
    assert "config_dir" not in driver.ultimos_kwargs
    assert avisos and "DPY-3015" in avisos[0]


def test_outro_erro_de_conexao_nao_ativa_thick(driver: _Driver) -> None:
    driver.falhas_connect.append(oracledb.DatabaseError("ORA-12541: TNS:no listener"))
    with pytest.raises(oracledb.DatabaseError, match="ORA-12541"):
        _conectar()
    assert driver.chamadas == ["connect"]


def test_notsupported_sem_dpy3015_nao_ativa_thick(driver: _Driver) -> None:
    driver.falhas_connect.append(
        oracledb.NotSupportedError("DPY-3001: feature not supported")
    )
    with pytest.raises(oracledb.NotSupportedError, match="DPY-3001"):
        _conectar()
    assert driver.chamadas == ["connect"]


def test_dpy3015_com_thick_ja_ativo_propaga(driver: _Driver) -> None:
    driver.thin = False
    driver.falhas_connect.append(oracledb.NotSupportedError(_MENSAGEM_DPY3015))
    with pytest.raises(oracledb.NotSupportedError, match="DPY-3015"):
        _conectar()
    assert driver.chamadas == ["connect"]


def test_modo_thick_inicializa_antes_da_primeira_conexao(
    driver: _Driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    assert _conectar() == "CONEXAO"
    assert driver.chamadas == ["init", "connect"]
    assert "config_dir" not in driver.ultimos_kwargs


def test_modo_invalido_falha_alto(
    driver: _Driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "turbo")
    with pytest.raises(ValueError, match="ORACLE_DRIVER_MODE"):
        _conectar()
    assert driver.chamadas == []


@pytest.mark.usefixtures("driver")
def test_modo_padrao_e_auto() -> None:
    assert oracle_client.get_driver_mode() == "auto"


def test_init_thick_e_noop_quando_ja_ativo(driver: _Driver) -> None:
    driver.thin = False
    oracle_client.init_oracle_thick_mode("instantclient_19c", None, _silencio)
    assert driver.chamadas == []


def test_init_tolera_init_repetido_com_argumentos_diferentes(driver: _Driver) -> None:
    driver.init_erro = oracledb.ProgrammingError(
        "init_oracle_client() was already called with different arguments"
    )
    oracle_client.init_oracle_thick_mode("instantclient_19c", None, _silencio)
    assert driver.chamadas == ["init"]


def test_init_propaga_falha_real_do_client(driver: _Driver) -> None:
    driver.init_erro = oracledb.InterfaceError(
        "DPI-1047: Oracle Client library cannot be loaded"
    )
    with pytest.raises(oracledb.InterfaceError, match="DPI-1047"):
        oracle_client.init_oracle_thick_mode("instantclient_19c", None, _silencio)


def test_init_propaga_thin_ja_criado_sem_engolir(driver: _Driver) -> None:
    driver.init_erro = oracledb.ProgrammingError(
        "python-oracledb thick mode cannot be used because thin mode has already been enabled"
    )
    with pytest.raises(oracledb.ProgrammingError, match="thin mode"):
        oracle_client.init_oracle_thick_mode("instantclient_19c", None, _silencio)


@pytest.mark.usefixtures("driver")
def test_describe_driver_mode_thin() -> None:
    modo = oracle_client.describe_driver_mode()
    assert modo.mode == "thin"
    assert modo.client_version is None
    assert "Thin Mode" in modo.label


def test_describe_driver_mode_thick_informa_versao_do_client(
    driver: _Driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver.thin = False
    monkeypatch.setattr(oracledb, "clientversion", lambda: (19, 25, 0, 0, 0))
    modo = oracle_client.describe_driver_mode()
    assert modo.mode == "thick"
    assert modo.client_version == (19, 25, 0, 0, 0)
    assert "19.25.0.0.0" in modo.label


def test_dpy3015_depois_de_thin_consolidado_propaga_causa_com_orientacao(
    driver: _Driver,
) -> None:
    assert _conectar() == "CONEXAO"
    driver.falhas_connect.append(oracledb.NotSupportedError(_MENSAGEM_DPY3015))

    with pytest.raises(oracledb.NotSupportedError, match="DPY-3015") as info:
        _conectar()

    assert "Reinicie o processo" in str(info.value)
    assert driver.chamadas == ["connect", "connect"], "não deveria inicializar o Thick"


def test_modo_thick_depois_de_thin_consolidado_orienta_reinicio(
    driver: _Driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão (achado 11): thick após Thin consolidado tem a mesma orientação do DPY-3015."""
    assert _conectar() == "CONEXAO"
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")

    with pytest.raises(oracledb.NotSupportedError, match="Reinicie o processo"):
        _conectar()

    assert driver.chamadas == ["connect"], "não deveria tentar o init do Thick"

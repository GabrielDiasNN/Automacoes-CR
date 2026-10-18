"""Testes unitários de lib/python/oracle_extract.py (fetch, serialize, hash, credenciais)."""

import json
import os
import sys
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "python"
    ),
)

from oracle_extract import (  # noqa: E402  pylint: disable=wrong-import-position
    OracleCredentials,
    _extrair_host_porta_dsn,
    _registrar_saude_wan,
    compute_hash,
    fetch_all,
    probe_wan_health,
    read_last_hash,
    resolve_oracle_credentials,
    serialize_rows,
    write_state_tmp,
)

pytestmark = pytest.mark.unitario


def _noop_log(*_args: Any, **_kwargs: Any) -> None:
    pass


def _fake_credentials() -> OracleCredentials:
    """Credenciais fictícias (não reais) para exercitar fetch_all/resolve_oracle_credentials."""
    return OracleCredentials("u", "p", "dbprd", "C:\\oracle", None)


def test_fetch_all_retorna_colunas_e_linhas(mock_oracle_connection: MagicMock) -> None:
    cursor = mock_oracle_connection.return_value.cursor.return_value
    cursor.description = [("NUMERO_OB",), ("QT_KG",)]
    cursor.fetchmany.side_effect = [[("900001", 10.0)], []]

    creds = _fake_credentials()
    columns, rows = fetch_all(creds, "SELECT 1", "EXEC-1", _noop_log)

    assert columns == ["NUMERO_OB", "QT_KG"]
    assert rows == [("900001", 10.0)]


def test_fetch_all_lotes_multiplos_concatenados(
    mock_oracle_connection: MagicMock,
) -> None:
    cursor = mock_oracle_connection.return_value.cursor.return_value
    cursor.description = [("COL",)]
    cursor.fetchmany.side_effect = [[("a",)], [("b",)], []]

    creds = _fake_credentials()
    _, rows = fetch_all(creds, "SELECT 1", "EXEC-1", _noop_log, batch_size=1)

    assert rows == [("a",), ("b",)]


def test_fetch_all_cursor_sem_description_retorna_vazio(
    mock_oracle_connection: MagicMock,
) -> None:
    cursor = mock_oracle_connection.return_value.cursor.return_value
    cursor.description = None

    creds = _fake_credentials()
    columns, rows = fetch_all(creds, "SELECT 1", "EXEC-1", _noop_log)

    assert not columns
    assert not rows


def test_fetch_all_sem_cursor_arraysize_explicito_acompanha_batch_size(
    mock_oracle_connection: MagicMock,
) -> None:
    """Regressão: sem cursor_arraysize, o driver ficava no default (100)
    independente do batch_size pedido, custando ~50 round-trips de rede por
    lote de 5000 linhas em vez de 1."""
    cursor = mock_oracle_connection.return_value.cursor.return_value
    cursor.description = [("COL",)]
    cursor.fetchmany.side_effect = [[]]

    creds = _fake_credentials()
    fetch_all(creds, "SELECT 1", "EXEC-1", _noop_log, batch_size=5000)

    assert cursor.arraysize == 5000


def test_fetch_all_cursor_arraysize_explicito_tem_precedencia_sobre_batch_size(
    mock_oracle_connection: MagicMock,
) -> None:
    cursor = mock_oracle_connection.return_value.cursor.return_value
    cursor.description = [("COL",)]
    cursor.fetchmany.side_effect = [[]]

    creds = _fake_credentials()
    fetch_all(
        creds, "SELECT 1", "EXEC-1", _noop_log, batch_size=5000, cursor_arraysize=200
    )

    assert cursor.arraysize == 200


def test_serialize_rows_datetime_para_isoformat() -> None:
    dt = datetime(2026, 7, 3, 10, 30)
    data = serialize_rows(["DATA"], [(dt,)])
    assert data == [{"DATA": dt.isoformat()}]


def test_serialize_rows_strip_espacos() -> None:
    data = serialize_rows(["NOME"], [("  fulano  ",)])
    assert data == [{"NOME": "fulano"}]


def test_serialize_rows_sort_key_aplicado() -> None:
    data = serialize_rows(
        ["NUMERO_OB"], [("900003",), ("900001",)], sort_key=lambda r: r["NUMERO_OB"]
    )
    assert [r["NUMERO_OB"] for r in data] == ["900001", "900003"]


def test_compute_hash_deterministico() -> None:
    payload = [{"a": 1, "b": 2}]
    assert compute_hash(payload) == compute_hash(payload)


def test_compute_hash_sort_keys_garante_ordem() -> None:
    assert compute_hash({"a": 1, "b": 2}) == compute_hash({"b": 2, "a": 1})


def test_read_last_hash_arquivo_ausente_retorna_string_vazia(tmp_path: Any) -> None:
    state_path = str(tmp_path / "state.json")
    assert read_last_hash(state_path) == ""


def test_read_last_hash_json_invalido_retorna_string_vazia(tmp_path: Any) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{invalido", encoding="utf-8")
    assert read_last_hash(str(state_path)) == ""


def test_read_last_hash_retorna_hash_salvo(tmp_path: Any) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_hash": "abc123"}), encoding="utf-8")
    assert read_last_hash(str(state_path)) == "abc123"


def test_write_state_tmp_cria_arquivo_com_sufixo_tmp(tmp_path: Any) -> None:
    state_path = str(tmp_path / "state.json")
    write_state_tmp(state_path, "hash123")

    tmp_file = tmp_path / "state.json.tmp"
    assert tmp_file.exists()
    content = json.loads(tmp_file.read_text(encoding="utf-8"))
    assert content["last_hash"] == "hash123"


def test_resolve_oracle_credentials_ausentes_retorna_none(monkeypatch: Any) -> None:
    monkeypatch.delenv("ORACLE_READONLY_USER", raising=False)
    monkeypatch.delenv("ORACLE_READONLY_PASSWORD", raising=False)
    result = resolve_oracle_credentials(_noop_log, "EXEC-1")
    assert result is None


def test_resolve_oracle_credentials_force_dsn_ignora_env(
    monkeypatch: Any, tmp_path: Any
) -> None:
    client_lib_dir = tmp_path / "oracle_client"
    client_lib_dir.mkdir()
    monkeypatch.setenv("ORACLE_READONLY_USER", "user")
    monkeypatch.setenv("ORACLE_READONLY_PASSWORD", "pass")
    monkeypatch.setenv("ORACLE_CONNECT_STRING", "outra_dsn")
    monkeypatch.setenv("ORACLE_CLIENT_LIB_DIR", str(client_lib_dir))

    creds = resolve_oracle_credentials(_noop_log, "EXEC-1", force_dsn="dbprd")

    assert creds is not None
    assert creds.dsn == "dbprd"


def test_resolve_oracle_credentials_easy_connect_plus_19c(
    monkeypatch: Any, tmp_path: Any
) -> None:
    client_lib_dir = tmp_path / "oracle_client"
    client_lib_dir.mkdir()
    dsn_plus = "unifique.lan:1521/dbprd?transport_connect_timeout=5&retry_count=3&retry_delay=2&sdu=65535"
    monkeypatch.setenv("ORACLE_READONLY_USER", "user")
    monkeypatch.setenv("ORACLE_READONLY_PASSWORD", "pass")
    monkeypatch.setenv("ORACLE_CONNECT_STRING", f"  {dsn_plus}  ")
    monkeypatch.setenv("ORACLE_CLIENT_LIB_DIR", str(client_lib_dir))

    creds = resolve_oracle_credentials(_noop_log, "EXEC-1")

    assert creds is not None
    assert creds.dsn == dsn_plus


def test_fetch_all_instrumenta_sessao_oci(mock_oracle_connection: MagicMock) -> None:
    conn = mock_oracle_connection.return_value
    cursor = conn.cursor.return_value
    cursor.description = [("ID",)]
    cursor.fetchmany.side_effect = [[(1,)], []]

    creds = _fake_credentials()
    fetch_all(
        creds, "SELECT 1", "EXEC-ABCDEF1234", _noop_log, automacao="Receitas Emitidas"
    )

    assert conn.module == "HubAutomacoes.Receitas Emitidas"
    assert conn.action == "FETCH:EXEC-ABC"
    assert conn.client_identifier == "AUTO:Receitas Emitidas:EXEC-ABC"
    assert "PID:" in conn.client_info
    assert conn.db_op == "OP_RECEITAS_EMITIDAS"


def test_extrair_host_porta_dsn() -> None:
    host, port = _extrair_host_porta_dsn("10.62.0.2:1521/dbprd")
    assert host == "10.62.0.2"
    assert port == 1521

    host, port = _extrair_host_porta_dsn("unifique.lan:1526/dbprd?sdu=65535")
    assert host == "unifique.lan"
    assert port == 1526

    # Regressão (achado 12): sem host no DSN não há IP fixo de fallback.
    host, port = _extrair_host_porta_dsn("dbprd")
    assert host == ""
    assert port == 1521


def test_probe_wan_health_sucesso_mock(monkeypatch: Any) -> None:
    mock_socket = MagicMock()
    monkeypatch.setattr("socket.socket", MagicMock(return_value=mock_socket))

    res = probe_wan_health("10.62.0.2", 1521, samples=2, timeout=0.1)

    assert res["reachable"] is True
    assert res["samples_ok"] == 2
    assert res["packet_loss_pct"] == 0.0
    assert res["rtt_ms"] is not None
    assert res["error"] is None


def test_probe_wan_health_timeout_mock(monkeypatch: Any) -> None:
    mock_socket = MagicMock()
    mock_socket.connect.side_effect = TimeoutError("timed out")
    monkeypatch.setattr("socket.socket", MagicMock(return_value=mock_socket))

    res = probe_wan_health("10.62.0.2", 1521, samples=2, timeout=0.1)

    assert res["reachable"] is False
    assert res["samples_ok"] == 0
    assert res["packet_loss_pct"] == 100.0
    assert res["rtt_ms"] is None
    assert "timed out" in (res["error"] or "")


def test_fetch_all_wan_degradada_ajusta_batch_dinamicamente(
    mock_oracle_connection: MagicMock, monkeypatch: Any
) -> None:
    conn = mock_oracle_connection.return_value
    cursor = conn.cursor.return_value
    cursor.description = [("COL",)]
    cursor.fetchmany.side_effect = [[]]

    # Simula probe WAN com RTT de 120ms (> 80ms)
    mock_probe = {
        "reachable": True,
        "rtt_ms": 120.0,
        "packet_loss_pct": 0.0,
        "samples_ok": 3,
        "samples_total": 3,
        "error": None,
    }
    monkeypatch.setattr("oracle_extract.probe_wan_health", lambda *a, **k: mock_probe)
    # Alias TNS só é medido com host conhecido.
    monkeypatch.setenv("ORACLE_HOST", "host-teste")

    logs: list[tuple[str, str]] = []

    def _captura_log(msg: str, lvl: str = "INFO", _exec_id: str = "") -> None:
        logs.append((lvl, msg))

    creds = _fake_credentials()
    fetch_all(creds, "SELECT 1", "EXEC-WAN-1", _captura_log, batch_size=5000)

    # O lote pedido é mantido: lote menor em link lento só multiplica os round-trips.
    assert cursor.arraysize == 5000
    assert cursor.prefetchrows == 5000
    # Verifica que o log de advertência foi emitido
    assert any(lvl == "WARN" and "WAN degradada" in msg for lvl, msg in logs)


def test_serialize_rows_rejeita_nomes_de_coluna_repetidos() -> None:
    with pytest.raises(ValueError, match="nome repetido.*ID"):
        serialize_rows(["ID", "ID"], [(1, 2)])


@pytest.mark.parametrize("conteudo", ["[]", "null", "42"])
def test_read_last_hash_raiz_que_nao_e_objeto_levanta_valueerror(
    tmp_path: Any, conteudo: str
) -> None:
    arquivo = tmp_path / "state.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError, match="objeto JSON"):
        read_last_hash(str(arquivo))


def test_read_last_hash_bytes_fora_de_utf8_nao_vira_primeira_execucao(
    tmp_path: Any,
) -> None:
    arquivo = tmp_path / "state.json"
    arquivo.write_bytes(b'{"last_hash": "\xff\xfe"}')
    with pytest.raises(ValueError):
        read_last_hash(str(arquivo))


def test_ajuste_wan_pula_probe_de_alias_sem_host(monkeypatch: Any) -> None:
    monkeypatch.delenv("ORACLE_HOST", raising=False)
    chamado = MagicMock()
    monkeypatch.setattr("oracle_extract.probe_wan_health", chamado)
    _registrar_saude_wan("dbprd", 5000, lambda *a: None, "X")
    chamado.assert_not_called()


def test_ajuste_wan_ignora_uma_amostra_perdida(monkeypatch: Any) -> None:
    probe = {"reachable": True, "rtt_ms": 10.0, "packet_loss_pct": 33.3}
    monkeypatch.setattr("oracle_extract.probe_wan_health", lambda *a, **k: probe)
    _registrar_saude_wan("h:1521/dbprd", 5000, lambda *a: None, "X")


@pytest.mark.parametrize(
    ("dsn", "esperado"),
    [
        ("tcps://h.lan:2484/dbprd?x=1", ("h.lan", 2484)),
        ("//h:1600/svc", ("h", 1600)),
        ("[::1]:1530/svc", ("::1", 1530)),
        ("[fe80::1]/svc", ("fe80::1", 1521)),
    ],
)
def test_extrair_host_porta_dsn_com_protocolo_e_ipv6(
    dsn: str, esperado: tuple[str, int]
) -> None:
    assert _extrair_host_porta_dsn(dsn) == esperado


@pytest.mark.parametrize("vazio", ["", "   "])
def test_resolve_oracle_credentials_dsn_vazio_nao_cai_no_padrao(
    monkeypatch: Any, tmp_path: Any, vazio: str
) -> None:
    client_lib_dir = tmp_path / "oracle_client"
    client_lib_dir.mkdir()
    monkeypatch.setenv("ORACLE_READONLY_USER", "user")
    monkeypatch.setenv("ORACLE_READONLY_PASSWORD", "pass")
    monkeypatch.setenv("ORACLE_CONNECT_STRING", vazio)
    monkeypatch.setenv("ORACLE_CLIENT_LIB_DIR", str(client_lib_dir))

    assert resolve_oracle_credentials(_noop_log, "EXEC-1") is None
    assert resolve_oracle_credentials(_noop_log, "EXEC-1", force_dsn="") is None


def test_extrair_host_porta_dsn_ignora_url_na_query_string() -> None:
    dsn = "dbhost:1521/dbprd?wallet_location=file:///wallet"
    assert _extrair_host_porta_dsn(dsn) == ("dbhost", 1521)


def test_probe_wan_health_dns_falho_nao_tenta_conectar(monkeypatch: Any) -> None:
    def _falha(*_a: Any, **_k: Any) -> Any:
        raise OSError("nome não resolvido")

    monkeypatch.setattr("socket.getaddrinfo", _falha)
    criar_socket = MagicMock()
    monkeypatch.setattr("socket.socket", criar_socket)
    res = probe_wan_health("host-inexistente", 1521, samples=3, timeout=0.1)
    assert res["reachable"] is False
    assert "resolução de nome" in res["error"]
    criar_socket.assert_not_called()


def test_modo_auto_nao_exige_client_lib(monkeypatch: Any) -> None:
    """Regressão (achado 10): Thin (auto) não depende de ORACLE_CLIENT_LIB_DIR."""
    monkeypatch.setenv("ORACLE_READONLY_USER", "user")
    monkeypatch.setenv("ORACLE_READONLY_PASSWORD", "pass")
    monkeypatch.delenv("ORACLE_DRIVER_MODE", raising=False)
    monkeypatch.delenv("ORACLE_CLIENT_LIB_DIR", raising=False)
    monkeypatch.delenv("ORACLE_CLIENT_PATH", raising=False)
    creds = resolve_oracle_credentials(_noop_log, "EXEC-1")
    assert creds is not None
    assert creds.client_lib == ""


def test_modo_thick_exige_client_lib_existente(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("ORACLE_READONLY_USER", "user")
    monkeypatch.setenv("ORACLE_READONLY_PASSWORD", "pass")
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    monkeypatch.setenv("ORACLE_CLIENT_LIB_DIR", str(tmp_path / "nao_existe"))
    assert resolve_oracle_credentials(_noop_log, "EXEC-1") is None

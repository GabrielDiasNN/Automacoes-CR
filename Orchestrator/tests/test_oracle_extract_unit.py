"""Testes unitários de lib/python/oracle_extract.py (fetch, serialize, hash, credenciais)."""

import json
import os
import sys
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "python"
    ),
)

from oracle_extract import (  # noqa: E402  pylint: disable=wrong-import-position
    OracleCredentials,
    compute_hash,
    fetch_all,
    read_last_hash,
    resolve_oracle_credentials,
    serialize_rows,
    write_state_tmp,
)


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

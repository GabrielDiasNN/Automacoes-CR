# pylint: disable=all
# mypy: ignore-errors
"""
Testes unitários para o módulo de segurança e higienização de logs e payloads.
"""

from app.constants import MAX_DB_LOGS_CHARS
from app.security import (sanitize_log_payload, sanitize_string,
                          truncate_log_payload)


def test_sanitize_string_oracle_credentials():
    # Testa mascaramento de credenciais em URLs do Oracle e conexões
    text = "Erro ao conectar: oracle://system:minhasenha123@192.168.1.100:1521/XE"
    expected = "Erro ao conectar: oracle://system:********@192.168.1.100:1521/XE"
    assert sanitize_string(text) == expected


def test_sanitize_string_http_credentials():
    # Testa mascaramento em URLs http normais
    text = (
        "Acesso negado para http://usuario_teste:senha_super_secreta@localhost:8000/api"
    )
    expected = "Acesso negado para http://usuario_teste:********@localhost:8000/api"
    assert sanitize_string(text) == expected


def test_sanitize_string_api_key_query_and_equals():
    # Vários formatos de atribuição de api_key, password, token
    text1 = "api_key=xyz12345&outro_param=1"
    assert "api_key=********" in sanitize_string(text1)

    text2 = '{"api-key": "secret-value-here"}'
    assert '"api-key": "********"' in sanitize_string(text2)

    text3 = "password" + ' : "minha-senha-super-secreta"'
    assert ("password" + ' : "********"') in sanitize_string(text3)

    text4 = "token=WhatsAppToken123456"
    assert "token=********" in sanitize_string(text4)


def test_sanitize_string_cpf_cnpj():
    # CPF formatado
    text_cpf = "O cliente CPF 123.456.789-00 foi consultado."
    assert "123.456.789-00" not in sanitize_string(text_cpf)
    assert "***.***.***-**" in sanitize_string(text_cpf)

    # CNPJ formatado
    text_cnpj = "A empresa CNPJ 12.345.678/0001-99 foi consultada."
    assert "12.345.678/0001-99" not in sanitize_string(text_cnpj)
    assert "**.***.***/****-**" in sanitize_string(text_cnpj)


def test_sanitize_dictionary_recursive():
    # Testa sanitização recursiva de dicionário
    payload = {
        "api_key": "chave-secreta-123",
        "nested": {
            "password": "senha-secreta-456",
            "normal_field": "conteudo normal",
            "db_connection": "oracle://system:senha123@localhost/XE",
        },
        "list_field": [
            {"token": "token-xyz"},
            "texto comum com api_key=12345",
        ],
        "normal_key": "valor perfeitamente normal",
    }

    expected = {
        "api_key": "********",
        "nested": {
            "password": "********",
            "normal_field": "conteudo normal",
            "db_connection": "oracle://system:********@localhost/XE",
        },
        "list_field": [
            {"token": "********"},
            "texto comum com api_key=********",
        ],
        "normal_key": "valor perfeitamente normal",
    }

    assert sanitize_log_payload(payload) == expected


def test_sanitize_log_payload_non_string_non_dict():
    # Testa que outros tipos (como ints, bools, None) passam intocados
    assert sanitize_log_payload(12345) == 12345
    assert sanitize_log_payload(True) is True
    assert sanitize_log_payload(None) is None


def test_sanitize_log_payload_masks_nested_sensitive_collections():
    payload = {
        "client_secret": {"token": "abc12345"},
        "private_key": ["not-primitive-but-sensitive"],
        "access_token": b"secret-bytes",
        "auth_token": None,
    }

    sanitized = sanitize_log_payload(payload)

    assert sanitized["client_secret"] == {"token": "********"}
    assert sanitized["private_key"] == ["not-primitive-but-sensitive"]
    assert sanitized["access_token"] == "********"
    assert sanitized["auth_token"] is None


def test_sanitize_string_keeps_empty_text_unchanged():
    assert sanitize_string("") == ""


def test_truncate_log_payload_keeps_small_payload_unchanged():
    assert truncate_log_payload("linha curta") == "linha curta"
    assert truncate_log_payload("") == ""


def test_truncate_log_payload_marks_large_payload():
    text = "A" * (MAX_DB_LOGS_CHARS + 10)

    truncated = truncate_log_payload(text)

    assert len(truncated) > MAX_DB_LOGS_CHARS
    assert "[LOGS TRUNCADOS PELO SISTEMA" in truncated
    assert truncated.startswith("A" * 100)
    assert truncated.endswith("A" * 100)


def test_json_formatter_sanitizes_exception_traceback():
    import json
    import logging
    import sys

    from app.logger_setup import OrchestratorJsonFormatter

    formatter = OrchestratorJsonFormatter(component="QA")
    try:
        raise ValueError("falha com password=senha-ultra-secreta no payload")
    except ValueError:
        record = logging.LogRecord(
            name="orchestrator",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="erro de teste",
            args=(),
            exc_info=sys.exc_info(),
        )

    doc = json.loads(formatter.format(record))

    assert "exception" in doc
    assert "senha-ultra-secreta" not in doc["exception"]
    assert "password=********" in doc["exception"]

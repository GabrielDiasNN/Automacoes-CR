# pylint: disable=all
# mypy: ignore-errors
"""
Testes unitários para o módulo de segurança e higienização de logs e payloads.
"""

from app.security import sanitize_log_payload, sanitize_string


def test_sanitize_string_oracle_credentials():
    # Testa mascaramento de credenciais em URLs do Oracle e conexões
    text = "Erro ao conectar: oracle://system:minhasenha123@192.168.1.100:1521/XE"
    expected = "Erro ao conectar: oracle://system:********@192.168.1.100:1521/XE"
    assert sanitize_string(text) == expected


def test_sanitize_string_http_credentials():
    # Testa mascaramento em URLs http normais
    text = "Acesso negado para http://usuario_teste:senha_super_secreta@localhost:8000/api"
    expected = "Acesso negado para http://usuario_teste:********@localhost:8000/api"
    assert sanitize_string(text) == expected


def test_sanitize_string_api_key_query_and_equals():
    # Vários formatos de atribuição de api_key, password, token
    text1 = "api_key=xyz12345&outro_param=1"
    assert "api_key=********" in sanitize_string(text1)

    text2 = '{"api-key": "secret-value-here"}'
    assert '"api-key": "********"' in sanitize_string(text2)

    text3 = 'password' + ' : "minha-senha-super-secreta"'
    assert ('password' + ' : "********"') in sanitize_string(text3)

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

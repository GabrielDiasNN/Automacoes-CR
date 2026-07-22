"""
Testes unitários para o módulo de segurança e higienização de logs e payloads.
"""

from app.constants import MAX_DB_LOGS_CHARS
from app.security import (
    mask_env_content,
    sanitize_log_payload,
    sanitize_string,
    truncate_log_payload,
)


def test_sanitize_string_oracle_credentials() -> None:
    # Testa mascaramento de credenciais em URLs do Oracle e conexões
    text = "Erro ao conectar: oracle://system:minhasenha123@192.168.1.100:1521/XE"
    expected = "Erro ao conectar: oracle://system:********@192.168.1.100:1521/XE"
    assert sanitize_string(text) == expected


def test_sanitize_string_http_credentials() -> None:
    # Testa mascaramento em URLs http normais
    text = (
        "Acesso negado para http://usuario_teste:senha_super_secreta@localhost:8000/api"
    )
    expected = "Acesso negado para http://usuario_teste:********@localhost:8000/api"
    assert sanitize_string(text) == expected


def test_sanitize_string_api_key_query_and_equals() -> None:
    # Vários formatos de atribuição de api_key, password, token
    text1 = "api_key=xyz12345&outro_param=1"
    assert "api_key=********" in sanitize_string(text1)

    text2 = '{"api-key": "secret-value-here"}'
    assert '"api-key": "********"' in sanitize_string(text2)

    text3 = "password" + ' : "minha-senha-super-secreta"'
    assert "password" + ' : "********"' in sanitize_string(text3)

    text4 = "token=WhatsAppToken123456"
    assert "token=********" in sanitize_string(text4)


def test_sanitize_string_cpf_cnpj() -> None:
    # CPF formatado
    text_cpf = "O cliente CPF 123.456.789-00 foi consultado."
    assert "123.456.789-00" not in sanitize_string(text_cpf)
    assert "***.***.***-**" in sanitize_string(text_cpf)

    # CNPJ formatado
    text_cnpj = "A empresa CNPJ 12.345.678/0001-99 foi consultada."
    assert "12.345.678/0001-99" not in sanitize_string(text_cnpj)
    assert "**.***.***/****-**" in sanitize_string(text_cnpj)


def test_sanitize_dictionary_recursive() -> None:
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


def test_sanitize_log_payload_non_string_non_dict() -> None:
    # Testa que outros tipos (como ints, bools, None) passam intocados
    assert sanitize_log_payload(12345) == 12345
    assert sanitize_log_payload(True) is True
    assert sanitize_log_payload(None) is None


def test_sanitize_log_payload_masks_nested_sensitive_collections() -> None:
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


def test_sanitize_string_keeps_empty_text_unchanged() -> None:
    assert sanitize_string("") == ""


def test_truncate_log_payload_keeps_small_payload_unchanged() -> None:
    assert truncate_log_payload("linha curta") == "linha curta"
    assert truncate_log_payload("") == ""


def test_truncate_log_payload_marks_large_payload() -> None:
    text = "A" * (MAX_DB_LOGS_CHARS + 10)

    truncated = truncate_log_payload(text)

    assert len(truncated) > MAX_DB_LOGS_CHARS
    assert "[LOGS TRUNCADOS PELO SISTEMA" in truncated
    assert truncated.startswith("A" * 100)
    assert truncated.endswith("A" * 100)


def test_json_formatter_sanitizes_exception_traceback() -> None:
    import json  # pylint: disable=import-outside-toplevel
    import logging  # pylint: disable=import-outside-toplevel
    import sys  # pylint: disable=import-outside-toplevel

    from app.logger_setup import (  # pylint: disable=import-outside-toplevel
        OrchestratorJsonFormatter,
    )

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


def test_sanitize_string_mascara_cpf_cnpj_cru_apenas_com_rotulo() -> None:
    # Achado #38: CPF/CNPJ sem pontuação só é mascarado quando há rótulo
    # explícito — mascarar qualquer sequência de 11/14 dígitos destruiria IDs.
    assert sanitize_string("cpf: 12345678901") == "cpf: ********"
    assert sanitize_string("CNPJ=12345678000199") == "CNPJ=********"


def test_sanitize_string_preserva_ids_numericos_sem_rotulo() -> None:
    # Guarda anti-falso-positivo do #38: exec_ids, timestamps e contadores não
    # podem ser corrompidos pela heurística de PII crua.
    for original in (
        "CRON_5_1784232000 disparado",
        "exec_id=EXEC_1784232000_AB12",
        "duracao 12345678901 ms",
        "NUMERO_OB 900001 seq 1",
    ):
        assert sanitize_string(original) == original


def test_sanitize_string_mascara_credencial_em_query_string() -> None:
    # Achado #41: o handshake WebSocket manda a API Key em ?key= (o protocolo
    # não permite header no browser). Se essa URL cair em log, a chave não podia
    # sair em claro.
    assert (
        sanitize_string("GET /ws/events?key=minha-chave-secreta 101")
        == "GET /ws/events?key=******** 101"
    )
    assert (
        sanitize_string("/ws/logs/EXEC_1?key=abc123&outro=ok")
        == "/ws/logs/EXEC_1?key=********&outro=ok"
    )


def test_sanitize_string_nao_mascara_query_param_nao_sensivel() -> None:
    original = "GET /api/beneficiamento/historico?limit=500 200 OK"
    assert sanitize_string(original) == original
    livre = "texto livre com key=valor normal"
    assert sanitize_string(livre) == livre


def test_sanitize_string_mascara_dsn_ezconnect_sem_scheme() -> None:
    # DSN Oracle EZConnect nativo (sem oracle://), com porta/servico ou hostname
    # puro, deve ser mascarado mesmo sem prefixo de esquema.
    assert (
        sanitize_string("conectando em system/senha123@dbprd:1521/PROD ok")
        == "conectando em system/********@dbprd:1521/PROD ok"
    )
    assert (
        sanitize_string("conectando em system/senha123@localhost/XE ok")
        == "conectando em system/********@localhost/XE ok"
    )
    assert (
        sanitize_string("conectando em system/senha123@dbserver ok")
        == "conectando em system/********@dbserver ok"
    )


def test_sanitize_string_nao_mascara_email_em_texto_livre() -> None:
    # A forma "usuario/senha@dominio.com" é ambigua com "identificador/senha@host"
    # do EZConnect, mas um FQDN nu sem porta/servico não deve ser mascarado, para
    # não corromper e-mails mencionados em mensagens de log/notificação.
    original = "Falha ao enviar e-mail para usuario/teste@dominio.com: SMTP timeout"
    assert sanitize_string(original) == original


def test_mask_env_content_mascara_oracle_connect_string() -> None:
    # ORACLE_CONNECT_STRING é a chave real usada em .env/.env.example para o DSN
    # Oracle; precisa ser reconhecida por _SENSITIVE_ENV_KEY_RE mesmo sem casar
    # literalmente "conn_str"/"connection_string".
    content = "ORACLE_CONNECT_STRING=system/secretpass@dbprd:1521/PROD\n"
    assert mask_env_content(content) == "ORACLE_CONNECT_STRING=********\n"

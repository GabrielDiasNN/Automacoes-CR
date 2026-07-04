# pylint: disable=protected-access
"""Auditoria de segurança da allowlist de variáveis de ambiente do worker."""

import worker

FORBIDDEN_KEYS = {
    "ORACLE_READONLY_PASSWORD",
    "ORACLE_READONLY_USER",
    "ORCHESTRATOR_API_KEY",
    "WHATSAPP_TOKEN",
    "SMTP_PASSWORD",
    "SECRET_KEY",
}


def test_allowed_env_keys_nao_contem_segredos() -> None:
    vazamentos = FORBIDDEN_KEYS & worker._ALLOWED_ENV_KEYS
    assert not vazamentos, f"Segredos na allowlist: {vazamentos}"

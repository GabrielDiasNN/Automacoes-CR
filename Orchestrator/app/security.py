# pylint: disable=all
# mypy: ignore-errors
"""
Módulo de segurança e sanitização do Orchestrator Central de Automações.

Fornece higienização central de logs e payloads para evitar o vazamento de segredos
(como API Keys, credenciais Oracle, tokens de canais e senhas) de acordo com o
Pilar de Segurança (Fase 6).
"""

import re
from typing import Any

# Regexes compiladas para performance
_URL_CREDENTIALS_RE = re.compile(r"\b([a-zA-Z]+://)([^/:\s@]+):([^/:\s@]+)(@[^/:\s@]+)")

# Suporta chave com ou sem aspas, e valor com ou sem aspas (e.g. "api_key": "segredo" ou api_key=segredo)
_SECRET_KEY_VALUE_RE = re.compile(
    r"(?i)(['\"]?)\b(api[_-]?key|password|senha|token|jwt|client[_-]?secret|private[_-]?key|conn[_-]?str|connection[_-]?string)\b\1(\s*[:=]+\s*)(['\"]?)([^'\"\s&,;]{3,})\4"
)

_CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")

# Filtro estrito para chaves confidenciais no dicionário (evita falsos positivos como normal_key ou db_connection)
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)^(api[_-]?key|password|senha|token|jwt|client[_-]?secret|private[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)$"
)


def sanitize_string(text: str) -> str:
    """
    Sanitiza uma string mascarando segredos, URLs com credenciais, CPF e CNPJ.
    """
    if not text:
        return text

    # 1. URL com credenciais (e.g., oracle://system:senha@host:1521/XE)
    text = _URL_CREDENTIALS_RE.sub(r"\1\2:********\4", text)

    # 2. Pares chave-valor de segredos (e.g. api_key com atribuicao)
    text = _SECRET_KEY_VALUE_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)}{m.group(4)}********{m.group(4)}",
        text,
    )

    # 3. CPF formatado
    text = _CPF_RE.sub("***.***.***-**", text)

    # 4. CNPJ formatado
    text = _CNPJ_RE.sub("**.***.***/****-**", text)

    return text


def sanitize_log_payload(payload: Any) -> Any:
    """
    Remove ou mascara dados sensíveis antes de registrar logs ou retornar payloads.
    Suporta strings, dicionários e listas de forma recursiva.
    """
    if isinstance(payload, str):
        return sanitize_string(payload)

    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            k_str = str(k)
            # Se a chave for sensível e o valor for primitivo, mascara diretamente
            if _SENSITIVE_KEY_RE.match(k_str):
                if isinstance(v, (str, int, float, bytes)):
                    sanitized[k] = "********"
                elif isinstance(v, (dict, list)):
                    sanitized[k] = sanitize_log_payload(v)
                else:
                    sanitized[k] = v
            else:
                sanitized[k] = sanitize_log_payload(v)
        return sanitized

    if isinstance(payload, list):
        return [sanitize_log_payload(item) for item in payload]

    return payload


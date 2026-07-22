"""
Módulo de segurança e sanitização do Orchestrator Central de Automações.

Fornece higienização central de logs e payloads para evitar o vazamento de segredos
(como API Keys, credenciais Oracle, tokens de canais e senhas) de acordo com o
Pilar de Segurança (Fase 6).
"""

# pylint: disable=relative-beyond-top-level

import re
from typing import Any

from .constants import MAX_DB_LOGS_CHARS

# Regexes compiladas para performance.
# Senha capturada de forma gulosa ([^/\s]+) até o ÚLTIMO '@' antes do host, para
# não vazar parte de senhas que contêm '@' (ex.: system:my@pass@host).
_URL_CREDENTIALS_RE = re.compile(r"\b([a-zA-Z]+://)([^/:\s@]+):([^/\s]+)@([^/:\s@]+)")

# DSN nativo Oracle EZConnect (user/senha@host[:porta][/servico]), sem scheme://.
# O host é restrito a formas que não coincidem com "usuario/senha@dominio.com"
# (endereço de e-mail em texto livre): exige porta, segmento de serviço após
# '/', ou host sem ponto (hostname puro) — um FQDN nu sem porta/serviço tem a
# mesma forma de um e-mail e não é mascarado, evitando corromper mensagens de
# log que mencionam endereços de e-mail.
_EZCONNECT_CREDENTIALS_RE = re.compile(
    r"\b([A-Za-z0-9_]+)/([^/@\s]+)@("
    r"[\w.\-]+:\d+(?:/[\w.\-]+)?"  # host[.sub]*:porta[/servico]
    r"|[\w.\-]+/[\w.\-]+"  # host[.sub]*/servico (sem porta)
    r"|(?![\w.\-]*\.[A-Za-z])[A-Za-z0-9_-]+"  # hostname puro, sem sufixo com ponto
    r")"
)

# Fonte única das chaves sensíveis, consumida tanto pela regex de texto livre
# (_SECRET_KEY_VALUE_RE) quanto pela de chave-de-dicionário (_SENSITIVE_KEY_RE) —
# evita a divergência de cobertura dos achados #22/#23 (antes cada uma cobria um
# subconjunto diferente: conn_str só na primeira, access_token/secret_key só na
# segunda).
_SENSITIVE_KEY_ALTERNATION = (
    r"api[_-]?key|password|senha|token|jwt|client[_-]?secret|private[_-]?key|"
    r"secret[_-]?key|access[_-]?token|auth[_-]?token|conn[_-]?str|"
    r"connection[_-]?string|connect[_-]?string|credential|dsn"
)

# Suporta chave/valor com ou sem aspas.
_SECRET_KEY_VALUE_RE = re.compile(
    r"(?i)(['\"]?)\b(" + _SENSITIVE_KEY_ALTERNATION + r")\b\1(\s*[:=]+\s*)"
    r"(['\"]?)([^'\"\s&,;]{3,})\4"
)

# Credencial em query string (ex.: o handshake WebSocket usa ?key=..., já que o
# protocolo não permite header no browser). Ancorado em '?'/'&' para mascarar só
# em posição de query param, sem afetar texto livre contendo "key=" (#41).
_URL_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:key|api[_-]?key|token|access[_-]?token|secret)=)([^&\s\"']+)"
)

_CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")

# CPF/CNPJ sem pontuação só é mascarado quando há RÓTULO explícito ao lado
# (ex.: "cpf: 12345678901"). Mascarar qualquer sequência de 11/14 dígitos
# destruiria IDs numéricos, timestamps e exec_ids nos logs — o rótulo é a
# heurística de contexto que mantém o falso-positivo perto de zero (#38).
_CPF_CNPJ_RAW_RE = re.compile(r"(?i)\b(cpf|cnpj)(\W{0,3})(\d{11}|\d{14})\b")

# Filtro estrito para chaves confidenciais no dicionário.
_SENSITIVE_KEY_RE = re.compile(r"(?i)^(" + _SENSITIVE_KEY_ALTERNATION + r")$")

# Chave de .env conta como sensível se CONTIVER um destes tokens em qualquer
# posição (ORCHESTRATOR_API_KEY, ORACLE_READONLY_PASSWORD, ORACLE_CONNECT_STRING...).
# Reusa _SENSITIVE_KEY_ALTERNATION (mesma fonte única citada acima) em vez de uma
# lista literal própria, para não repetir a divergência de cobertura dos achados
# #22/#23. Difere de _SENSITIVE_KEY_RE, que ancora a chave inteira, e de
# _SECRET_KEY_VALUE_RE, cujo \b não casa dentro de um identificador com prefixo
# (tudo é \w).
_SENSITIVE_ENV_KEY_RE = re.compile(r"(?i)(" + _SENSITIVE_KEY_ALTERNATION + r")")

ENV_MASK_PLACEHOLDER = "********"


def mask_env_content(content: str) -> str:
    """Mascara o VALOR das chaves sensíveis de um conteúdo de .env.

    Preserva comentários, linhas em branco e chaves não sensíveis (portas,
    limites, caminhos), mantendo o arquivo legível para diagnóstico sem expor
    credenciais a quem só deveria inspecionar a configuração.
    """
    if not content:
        return content

    masked_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            masked_lines.append(line)
            continue
        key, _, _value = line.partition("=")
        if _SENSITIVE_ENV_KEY_RE.search(key):
            masked_lines.append(f"{key}={ENV_MASK_PLACEHOLDER}")
        else:
            masked_lines.append(line)

    result = "\n".join(masked_lines)
    # splitlines() descarta a quebra final; preserva-a para não alterar o arquivo.
    if content.endswith(("\n", "\r")):
        result += "\n"
    return result


def sanitize_string(text: str) -> str:
    """
    Sanitiza uma string mascarando segredos, URLs com credenciais, CPF e CNPJ.
    """
    if not text:
        return text

    # 1. URL com credenciais (e.g., oracle://system:senha@host:1521/XE)
    text = _URL_CREDENTIALS_RE.sub(r"\1\2:********@\4", text)

    # 1b. DSN Oracle EZConnect sem scheme (e.g., system/senha@dbprd:1521/PROD)
    text = _EZCONNECT_CREDENTIALS_RE.sub(r"\1/********@\3", text)

    # 1c. Credencial em query string (e.g., /ws/events?key=<API_KEY>)
    text = _URL_QUERY_SECRET_RE.sub(r"\1********", text)

    # 2. Pares chave-valor de segredos (e.g. api_key com atribuicao)
    text = _SECRET_KEY_VALUE_RE.sub(
        lambda m: (
            f"{m.group(1)}{m.group(2)}{m.group(1)}"
            f"{m.group(3)}{m.group(4)}********{m.group(4)}"
        ),
        text,
    )

    # 3. CPF formatado
    text = _CPF_RE.sub("***.***.***-**", text)

    # 4. CNPJ formatado
    text = _CNPJ_RE.sub("**.***.***/****-**", text)

    # 5. CPF/CNPJ cru, apenas quando rotulado (ex.: "CPF 12345678901")
    text = _CPF_CNPJ_RAW_RE.sub(r"\1\2********", text)

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


def truncate_log_payload(text: str) -> str:
    """
    Trunca uma string de log caso ela exceda o limite MAX_DB_LOGS_CHARS.
    Mantém os primeiros 100KB e os últimos 100KB com um aviso no meio.
    """
    if not text or len(text) <= MAX_DB_LOGS_CHARS:
        return text

    half_limit = MAX_DB_LOGS_CHARS // 2
    trunc_msg = (
        "\n... [LOGS TRUNCADOS PELO SISTEMA "
        f"(EXCEDEU {MAX_DB_LOGS_CHARS} CARACTERES)] ...\n"
    )

    return text[:half_limit] + trunc_msg + text[-half_limit:]

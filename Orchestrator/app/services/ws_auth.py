"""Tokens efêmeros de handshake WebSocket.

O protocolo WebSocket no browser não permite enviar headers no handshake, então
a credencial precisa viajar na query string — onde pode acabar em logs de acesso
de proxies/servidores (achado #41). Em vez da API Key mestra, o Dashboard pede
um token de uso único e vida curta a este serviço e usa ele no ``?token=``.

INVARIANTE: o store é em memória DESTE processo, igual à janela do rate limiter
(ver ``RateLimitMiddleware``). Vale enquanto o Orchestrator rodar em um único
worker uvicorn — o caso atual. Com N workers, um token emitido por um processo
seria recusado por outro e o store precisaria migrar para um backend
compartilhado.
"""

from __future__ import annotations

import secrets
import threading
import time

# Vida curta: o Dashboard pede o token e conecta em seguida. Mantém a janela de
# exposição mínima mesmo se o valor vazar para algum log.
WS_TOKEN_TTL_SECONDS = 30

# Teto defensivo do store: emissões sem consumo (ex.: cliente que desiste de
# conectar) expiram sozinhas, mas o cap evita crescimento sob abuso.
_MAX_TOKENS = 1000

_tokens: dict[str, float] = {}
_lock = threading.Lock()


def _prune_expired(now: float) -> None:
    """Remove tokens vencidos. Chamador deve segurar _lock."""
    expirados = [token for token, expiry in _tokens.items() if expiry <= now]
    for token in expirados:
        _tokens.pop(token, None)


def issue_ws_token() -> tuple[str, int]:
    """Emite um token de uso único para o handshake WebSocket."""
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        _prune_expired(now)
        if len(_tokens) >= _MAX_TOKENS:
            # Descarta o mais próximo de expirar para manter o store limitado.
            mais_antigo = min(_tokens, key=lambda item: _tokens[item])
            _tokens.pop(mais_antigo, None)
        _tokens[token] = now + WS_TOKEN_TTL_SECONDS
    return token, WS_TOKEN_TTL_SECONDS


def consume_ws_token(token: str) -> bool:
    """Valida e CONSOME o token (uso único). False se inválido ou expirado."""
    if not token:
        return False
    now = time.monotonic()
    with _lock:
        _prune_expired(now)
        expiry = _tokens.pop(token, None)
    return expiry is not None and expiry > now


def reset_ws_tokens() -> None:
    """Limpa o store — usado por testes para isolamento."""
    with _lock:
        _tokens.clear()

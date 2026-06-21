# pylint: disable=all
# mypy: ignore-errors
"""
Middleware Stack do Orchestrator Central de Automacoes v5.0.

Camadas de seguranca e observabilidade:
  - RequestIdMiddleware: Injeta X-Request-Id unico em toda requisicao
  - TimingMiddleware: Loga tempo de resposta de cada endpoint
  - RateLimitMiddleware: Sliding window 60 req/min por IP (configuravel via .env)
  - Autenticacao timing-safe via hmac.compare_digest
  - Log de tentativas de autenticacao invalidas (deteccao de forca bruta)
"""

import collections
import hmac
import logging
import os
import time
import uuid
from contextvars import ContextVar

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("orchestrator")

# Variaveis de contexto para o Padrão Enterprise de Logs (Pilar L)
request_id_var: ContextVar[str] = ContextVar("request_id", default="SYSTEM")
exec_id_var: ContextVar[str] = ContextVar("exec_id", default="")
automation_name_var: ContextVar[str] = ContextVar("automation_name", default="")

RATE_LIMIT_EXEMPT_PATHS = {
    "/api/system/health",
}

# ---------------------------------------------------------------------------
# Autenticacao Timing-Safe
# ---------------------------------------------------------------------------

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(request: Request, api_key: str = Depends(api_key_header)):
    """Valida API Key com comparacao timing-safe (anti timing-attack)."""
    # Secure-by-Default: Se a key nao estiver no ENV, gera um valor aleatorio impossivel de usar.
    expected_key = os.environ.get("ORCHESTRATOR_API_KEY")
    if not expected_key:
        expected_key = f"MISSING_ENV_{uuid.uuid4()}"

    if api_key is None or not hmac.compare_digest(api_key, expected_key):
        client_ip = request.client.host if request.client else "unknown"
        req_id = getattr(request.state, "request_id", "UNK")
        logger.warning(
            f"[{req_id}] [AUTH_FAIL] Tentativa de acesso inválida de IP={client_ip} "
            f"path={request.url.path}"
        )
        raise HTTPException(
            status_code=403, detail="Acesso negado: API Key inválida ou ausente."
        )
    return api_key


# ---------------------------------------------------------------------------
# Request ID Middleware
# ---------------------------------------------------------------------------


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Injeta um X-Request-Id unico em toda requisicao para rastreabilidade."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4())[:12])
        request.state.request_id = request_id

        token = request_id_var.set(request_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            request_id_var.reset(token)


# ---------------------------------------------------------------------------
# Timing Middleware
# ---------------------------------------------------------------------------


class TimingMiddleware(BaseHTTPMiddleware):
    """Loga o tempo de resposta e adiciona header X-Process-Time."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["X-Process-Time"] = f"{elapsed_ms}ms"

        # Logar apenas requests da API (ignorar static e healthcheck)
        path = request.url.path
        if path.startswith("/api") and path != "/api/system/health":
            req_id = getattr(request.state, "request_id", "?")
            logger.info(
                f"[{req_id}] {request.method} {path} -> {response.status_code} ({elapsed_ms}ms)"
            )

        return response


# ---------------------------------------------------------------------------
# Rate Limit Middleware - Sliding Window por IP
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter por IP de origem.
    Limite: RATE_LIMIT_RPM requisicoes por minuto (default: 120).
    Aplica-se apenas a endpoints /api (nao afeta dashboard/static).

    IPs sem atividade por _STALE_TTL segundos sao removidos a cada _CLEANUP_EVERY
    requisicoes para evitar crescimento ilimitado do dicionario em memoria.
    """

    _STALE_TTL = 3600  # 1h sem atividade → elegível para poda
    _CLEANUP_EVERY = 500  # verifica IPs inativos a cada N requisições

    def __init__(self, app, rpm: int | None = None):
        super().__init__(app)
        self.rpm = rpm or int(os.environ.get("RATE_LIMIT_RPM", "120"))
        self._window: dict[str, collections.deque] = {}
        self._last_seen: dict[str, float] = {}
        self._window_seconds = 60
        self._request_count = 0

    def _sweep_stale_ips(self, now: float) -> None:
        """Remove entradas de IPs inativos além do TTL para evitar memory leak."""
        threshold = now - self._STALE_TTL
        stale = [ip for ip, ts in list(self._last_seen.items()) if ts < threshold]
        for ip in stale:
            self._window.pop(ip, None)
            self._last_seen.pop(ip, None)
        if stale:
            logger.debug(
                f"[RATE_LIMIT] Removidas {len(stale)} entradas inativas da janela deslizante."
            )

    async def dispatch(self, request: Request, call_next):
        # Aplicar rate limit somente em rotas /api
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        if request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self._window_seconds

        if client_ip not in self._window:
            self._window[client_ip] = collections.deque()

        dq = self._window[client_ip]
        self._last_seen[client_ip] = now

        # Remover timestamps fora da janela
        while dq and dq[0] < window_start:
            dq.popleft()

        if len(dq) >= self.rpm:
            logger.warning(
                f"[RATE_LIMIT] IP={client_ip} excedeu {self.rpm} req/min "
                f"path={request.url.path}"
            )
            return Response(
                content='{"detail":"Rate limit excedido. Tente novamente em 60 segundos."}',
                status_code=429,
                headers={"Content-Type": "application/json", "Retry-After": "60"},
            )

        dq.append(now)

        # Poda periódica de IPs inativos
        self._request_count += 1
        if self._request_count >= self._CLEANUP_EVERY:
            self._request_count = 0
            self._sweep_stale_ips(now)

        return await call_next(request)

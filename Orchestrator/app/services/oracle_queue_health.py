"""Sonda de saúde da fila Oracle (worker TSplus via SMB) com cache curto.

Módulo próprio, sem dependência de `scheduler_runtime` nem de `diagnostic_collectors`:
os dois o importam no topo, sem ciclo de import.

A sonda SMB é síncrona (até ~1,5 s), e /health/full + /diagnostics podem ser chamados
em rajada: sem cache, cada request bloquearia o worker HTTP por 1,5 s. O lock também
serializa as sondas concorrentes (um único chamador sonda; os demais recebem o
resultado já em cache).
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import threading
import time
from types import ModuleType
from typing import Any

logger = logging.getLogger("orchestrator")

HEALTH_TTL_SECONDS = 15.0
DEGRADED_HEALTH_TTL_SECONDS = 3.0

_LIB_PYTHON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib", "python")
)
_CACHE_KEY = "snapshot"
_lock = threading.Lock()
_probe_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

# Falhas do lado do Orchestrator ao usar lib/python/oracle_queue: o import (módulo
# ausente, com erro de sintaxe ou sem a função) e I/O ao resolver o caminho ou ao tocar
# a fila. A lib já captura as falhas da própria sonda SMB e devolve payload degradado.
ORACLE_QUEUE_LOAD_ERRORS = (ImportError, AttributeError, SyntaxError, OSError)


def load_oracle_queue_module() -> ModuleType:
    """Importa lib/python/oracle_queue. Pode levantar um dos `ORACLE_QUEUE_LOAD_ERRORS`.

    lib/python não está no `sys.path` do Orchestrator: entra aqui, no primeiro uso, e o
    módulo é resolvido por nome em tempo de execução (só quem usa a fila o carrega).
    """
    if _LIB_PYTHON not in sys.path:
        sys.path.insert(0, _LIB_PYTHON)
    return importlib.import_module("oracle_queue")


def probe_oracle_queue_health() -> dict[str, Any]:
    """Sonda síncrona da fila Oracle (SMB). Pode levantar um dos `ORACLE_QUEUE_LOAD_ERRORS`."""
    snapshot: dict[str, Any] = (
        load_oracle_queue_module().collect_worker_health_snapshot()
    )
    return snapshot


def is_oracle_queue_degraded(oracle_q: dict[str, Any] | None) -> bool:
    """True quando o modo queue está ativo e o worker TSplus está degradado/offline."""
    return bool(
        oracle_q
        and oracle_q.get("enabled")
        and (
            not oracle_q.get("reachable")
            or not oracle_q.get("alive")
            or oracle_q.get("oracle_ok") is False
        )
    )


def _ttl_for_snapshot(snapshot: dict[str, Any]) -> float:
    """Falhas e snapshots degradados usam TTL curto para não congelar erros por 15s."""
    if (
        snapshot.get("source") == "error"
        or snapshot.get("error") is not None
        or is_oracle_queue_degraded(snapshot)
    ):
        return DEGRADED_HEALTH_TTL_SECONDS
    return HEALTH_TTL_SECONDS


def degraded_oracle_queue_health(exc: BaseException) -> dict[str, Any]:
    """Payload degradado com as MESMAS 13 chaves de `oracle_queue.collect_worker_health_snapshot`.

    `enabled` segue o mesmo critério de `collect_worker_health_snapshot`: fora do
    modo queue a fila não está em uso (`alive=None`, `reachable=None`,
    `source="disabled"`), e a falha da sonda não pode aparecer como worker offline.
    """
    queue_mode = os.environ.get("ORACLE_DRIVER_MODE", "").strip().lower() == "queue"
    if not queue_mode:
        return {
            "enabled": False,
            "alive": None,
            "reachable": None,
            "source": "disabled",
            "age_seconds": None,
            "state": None,
            "oracle_ok": None,
            "version": None,
            "machine": None,
            "req_id": None,
            "pending_requests": 0,
            "active_procs": 0,
            "error": None,
        }
    return {
        "enabled": True,
        "alive": False,
        "reachable": False,
        "source": "error",
        "age_seconds": None,
        "state": None,
        "oracle_ok": None,
        "version": None,
        "machine": None,
        "req_id": None,
        "pending_requests": 0,
        "active_procs": 0,
        "error": f"{type(exc).__name__}: {exc}"[:180],
    }


def reset_oracle_queue_health_cache() -> None:
    """Descarta o cache da sonda (uso em testes e em trocas de configuração)."""
    with _lock:
        _cache.clear()


def _read_cached_snapshot() -> dict[str, Any] | None:
    with _lock:
        now = time.monotonic()
        cached = _cache.get(_CACHE_KEY)
        if cached is not None:
            cached_at, cached_snapshot = cached
            if now - cached_at < _ttl_for_snapshot(cached_snapshot):
                return dict(cached_snapshot)
    return None


def collect_oracle_queue_health(use_cache: bool = True) -> dict[str, Any]:
    """Status de vivacidade do worker Oracle na fila SMB (se ORACLE_DRIVER_MODE=queue).

    Não levanta nas falhas de import/sonda: viram payload degradado (alive=False).
    O resultado fica em cache por `HEALTH_TTL_SECONDS` (ou `DEGRADED_HEALTH_TTL_SECONDS`
    em falhas); `use_cache=False` força uma sonda nova fora do `_lock` de leitura para
    não bloquear leitores em cache durante o I/O SMB.
    """
    if use_cache:
        cached = _read_cached_snapshot()
        if cached is not None:
            return cached

    with _probe_lock:
        if use_cache:
            cached = _read_cached_snapshot()
            if cached is not None:
                return cached
        try:
            snapshot = probe_oracle_queue_health()
        except ORACLE_QUEUE_LOAD_ERRORS as exc:
            logger.warning(
                "Sonda de saúde da fila Oracle falhou; reportando degradado: %s: %s",
                type(exc).__name__,
                exc,
            )
            snapshot = degraded_oracle_queue_health(exc)
        probed_at = time.monotonic()
        with _lock:
            _cache[_CACHE_KEY] = (probed_at, snapshot)
        return dict(snapshot)

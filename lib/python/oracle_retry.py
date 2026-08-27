# pylint: disable=too-many-arguments,too-many-positional-arguments
# broad-exception-caught / import-outside-toplevel: o hook do stamina roda dentro
# do retry do Oracle e nao pode derrubar a extracao por um erro no proprio log;
# `automation_log` so entra no sys.path quando um script de dominio o insere.
# pylint: disable=broad-exception-caught, import-outside-toplevel
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any, TypeVar

import oracledb
import pybreaker
import stamina
import stamina.instrumentation
from pybreaker import CircuitBreakerError  # noqa: F401
from stamina.instrumentation import RetryDetails, RetryHook

__all__ = ["make_oracle_retry", "CircuitBreakerError"]

F = TypeVar("F", bound=Callable[..., Any])

_STRUCTURED_TOKENS = {"1", "true", "True"}


def _structured_enabled() -> bool:
    return os.environ.get("HUB_LOG_STRUCTURED", "").strip() in _STRUCTURED_TOKENS


def _retry_ctx() -> tuple[str, str, str, str]:
    """Contexto do evento lido do ambiente exportado pelo run.ps1 migrado."""
    return (
        os.environ.get("HUB_AUTOMATION", "").strip() or "?",
        os.environ.get("HUB_EXEC_ID", "").strip() or "manual",
        os.environ.get("HUB_TRACE_ID", "").strip() or "-",
        os.environ.get("HUB_STEP", "").strip() or "extract",
    )


def _make_on_retry_hook(max_attempts: int) -> RetryHook:
    """Hook do stamina: retentativa interna do Oracle vira `retry.attempt` no padrao.

    Substitui o `LoggingOnRetryHook` default do stamina, que emitia a chave crua
    `stamina.retry_scheduled` em WARNING -- ilegivel no dashboard e sem os campos
    `attempt`/`max_attempts` do schema.
    """

    def _hook(details: RetryDetails) -> None:
        automation, exec_id, trace_id, step = _retry_ctx()
        upcoming = details.retry_num + 1
        cause = type(details.caused_by).__name__
        msg = (
            f"Oracle: retentativa {upcoming}/{max_attempts} agendada em "
            f"{details.wait_for:.1f}s (motivo: {cause})"
        )
        if _structured_enabled():
            try:
                from automation_log import emit_event

                emit_event(
                    "retry.attempt",
                    "WARN",
                    msg,
                    automation=automation,
                    exec_id=exec_id,
                    trace_id=trace_id,
                    step=step,
                    extra={"attempt": upcoming, "max_attempts": max_attempts},
                )
                return
            except Exception:  # pragma: no cover - fallback defensivo
                pass
        sys.stderr.write(f"[RETRY] {msg}\n")
        sys.stderr.flush()

    return _hook


def make_oracle_retry(
    fail_max: int = 3,
    reset_timeout: float = 60,
    attempts: int = 3,
    wait_initial: float = 0.1,
    wait_max: float = 5.0,
    wait_jitter: float = 1.0,
) -> Callable[[F], F]:
    """Returns a decorator that applies CircuitBreaker + stamina.retry to an Oracle function.

    Outer layer: pybreaker.CircuitBreaker (opens after fail_max consecutive failures).
    Inner layer: stamina.retry (retries on oracledb.DatabaseError up to `attempts` times).

    Efeito colateral: registra o hook de instrumentacao do stamina que traduz a
    retentativa interna do Oracle no evento `retry.attempt` do padrao de logging.
    """
    breaker = pybreaker.CircuitBreaker(fail_max=fail_max, reset_timeout=reset_timeout)
    stamina.instrumentation.set_on_retry_hooks([_make_on_retry_hook(attempts)])

    def decorator(fn: F) -> F:
        retrying = stamina.retry(
            on=oracledb.DatabaseError,
            attempts=attempts,
            wait_initial=wait_initial,
            wait_max=wait_max,
            wait_jitter=wait_jitter,
        )(fn)
        return breaker(retrying)  # type: ignore[return-value]

    return decorator

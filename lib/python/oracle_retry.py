from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any, TypeVar, cast

import oracledb
import pybreaker
import stamina
import stamina.instrumentation
from automation_log import emit_event
from oracle_queue import OracleQueueTransientError
from pybreaker import CircuitBreakerError
from stamina.instrumentation import RetryDetails

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


# `set_on_retry_hooks` e estado GLOBAL do processo: so existe um conjunto de
# hooks para todo o stamina. Fixar `max_attempts` no closure do hook fazia a
# ultima chamada de `make_oracle_retry` reescrever o limite reportado por todas
# as funcoes ja decoradas -- um extrator com attempts=3 passava a logar
# "retentativa 2/5" depois que outro registrasse attempts=5. O limite passa a
# viver num registro por callable, resolvido no momento do evento; a chave e a
# mesma string que o stamina poe em `RetryDetails.name` ("<modulo>.<qualname>").
_MAX_ATTEMPTS_BY_CALLABLE: dict[str, int] = {}


def _callable_key(fn: Callable[..., Any]) -> str:
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', repr(fn))}"


def _on_retry_hook(details: RetryDetails) -> None:
    """Hook do stamina: retentativa interna do Oracle vira `retry.attempt` no padrao.

    Substitui o `LoggingOnRetryHook` default do stamina, que emitia a chave crua
    `stamina.retry_scheduled` em WARNING -- ilegivel no dashboard e sem os campos
    `attempt`/`max_attempts` do schema.
    """
    automation, exec_id, trace_id, step = _retry_ctx()
    upcoming = details.retry_num + 1
    max_attempts = _MAX_ATTEMPTS_BY_CALLABLE.get(details.name)
    exc = details.caused_by
    cause = type(exc).__name__
    kind = getattr(exc, "kind", None)
    if kind:
        cause = f"{cause}[kind={kind}]"
    detail = (
        str(getattr(exc, "message", exc) or "")
        .replace("\r", " ")
        .replace("\n", " ")[:180]
    )
    cause_desc = f"{cause}: {detail}" if detail else cause

    if max_attempts is None:
        # Retry que nao veio de make_oracle_retry: sem limite conhecido, o
        # envelope sairia com um `max_attempts` inventado. Rastro humano so.
        sys.stderr.write(
            f"[RETRY] {details.name}: retentativa {upcoming} agendada em "
            f"{details.wait_for:.1f}s (motivo: {cause_desc})\n"
        )
        sys.stderr.flush()
        return

    msg = (
        f"Oracle: retentativa {upcoming}/{max_attempts} agendada em "
        f"{details.wait_for:.1f}s (motivo: {cause_desc})"
    )
    if _structured_enabled():
        # Hook do stamina: roda dentro do retry do Oracle, e uma exceção que escape daqui
        # cancela a retentativa. Por isso qualquer falha do próprio log cai no stderr.
        try:
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
        # Residual: hook do stamina; exceção que escape daqui cancela a retentativa do Oracle, então falha do log cai no stderr.
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    sys.stderr.write(f"[RETRY] {msg}\n")
    sys.stderr.flush()


# Residual: assinatura pública com nomes usados em chamadas de automações e testes.
def make_oracle_retry(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    fail_max: int = 3,
    reset_timeout: float = 60,
    attempts: int = 3,
    wait_initial: float = 0.1,
    wait_max: float = 5.0,
    wait_jitter: float = 1.0,
) -> Callable[[F], F]:
    """Returns a decorator that applies CircuitBreaker + stamina.retry to an Oracle function.

    Outer layer: pybreaker.CircuitBreaker (opens after fail_max consecutive failures).
    Inner layer: stamina.retry (retries on oracledb.DatabaseError and
    OracleQueueTransientError up to `attempts` times).

    Efeito colateral: registra o hook de instrumentacao do stamina que traduz a
    retentativa interna do Oracle no evento `retry.attempt` do padrao de logging.
    O hook e sempre o MESMO objeto (idempotente entre chamadas); o `attempts`
    de cada funcao decorada vai para `_MAX_ATTEMPTS_BY_CALLABLE`, de modo que
    dois decoradores com limites distintos no mesmo processo reportem cada um
    o seu.
    """
    breaker = pybreaker.CircuitBreaker(fail_max=fail_max, reset_timeout=reset_timeout)
    stamina.instrumentation.set_on_retry_hooks([_on_retry_hook])

    def decorator(fn: F) -> F:
        _MAX_ATTEMPTS_BY_CALLABLE[_callable_key(fn)] = attempts
        retrying = stamina.retry(
            # Falha transitória da fila SMB (ORACLE_DRIVER_MODE=queue) equivale à
            # queda de sessão do driver nativo. Prazo esgotado não entra: a consulta
            # pode seguir no Oracle, e repetir dobraria a carga.
            on=(oracledb.DatabaseError, OracleQueueTransientError),
            attempts=attempts,
            wait_initial=wait_initial,
            wait_max=wait_max,
            wait_jitter=wait_jitter,
        )(fn)
        # pybreaker tipa o wrapper como Callable[..., Any]; ele preserva a assinatura de fn.
        return cast(F, breaker(retrying))

    return decorator

# pylint: disable=too-many-arguments,too-many-positional-arguments
from collections.abc import Callable
from typing import Any, TypeVar

import oracledb
import pybreaker
import stamina
from pybreaker import CircuitBreakerError  # noqa: F401

__all__ = ["make_oracle_retry", "CircuitBreakerError"]

F = TypeVar("F", bound=Callable[..., Any])


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
    """
    breaker = pybreaker.CircuitBreaker(fail_max=fail_max, reset_timeout=reset_timeout)

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

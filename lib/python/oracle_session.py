"""Queda de sessão e prazos para o Oracle Client 12.2 desta máquina.

Fonte única para o runner do Beneficiamento e para as ferramentas de
`Tools/oracle`. A rede até o Oracle derruba sessões em ~4-6 s (ORA-00028 /
ORA-03113), com ou sem atividade, e o Client 12.2 não impõe prazo de conexão
nem suporta `connection.call_timeout` (exige 18.1+): os prazos são emulados por
thread e `connection.cancel()`.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import oracledb

__all__ = [
    "SESSION_DROP_MARKERS",
    "WatchdogOutcome",
    "cancel_after",
    "connect_within",
    "is_session_drop",
    "run_with_cancel",
]

# DPY-1001/DPI-1010 ("not connected") são a mesma classe (conexão já perdida).
# O cancelamento por prazo (ORA-01013) não entra: é prazo estourado, não rede.
SESSION_DROP_MARKERS = (
    "ORA-00028",
    "ORA-03113",
    "ORA-03135",
    "DPY-1001",
    "DPY-4011",
    "DPI-1010",
    "DPI-1080",
)

# Tempo que se espera a thread desenrolar depois do `cancel()`, antes de dá-la
# por abandonada.
CANCEL_GRACE_SECONDS = 5.0
_MIN_WAIT_SECONDS = 0.05


def is_session_drop(error: BaseException | str) -> bool:
    """True se o erro é queda de sessão pela rede, e não defeito da consulta."""
    message = str(error).upper()
    return any(marker in message for marker in SESSION_DROP_MARKERS)


def connect_within(connect: Callable[[], Any], seconds: float) -> Any:
    """`connect()` com prazo: o driver não impõe um no client 12.2.

    A conexão roda numa thread daemon. Se o prazo estoura, levanta
    `TimeoutError`; a thread abandonada fecha a conexão sozinha se ela ainda
    vier a se estabelecer, sem vazar sessão nem ser usada por outra thread.
    """
    holder: dict[str, Any] = {}
    lock = threading.Lock()
    abandoned = False

    def target() -> None:
        try:
            connection = connect()
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            holder["error"] = exc
            return
        with lock:
            late = connection if abandoned else None
            if late is None:
                holder["connection"] = connection
        if late is not None:
            with contextlib.suppress(oracledb.Error):  # limpeza best effort
                late.close()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(max(seconds, _MIN_WAIT_SECONDS))
    with lock:
        if "connection" in holder:
            return holder["connection"]
        if "error" not in holder:
            abandoned = True
            raise TimeoutError(f"Conexão Oracle excedeu {seconds:g}s.")
    raise holder["error"]


@contextlib.contextmanager
def cancel_after(
    connection: Any, seconds: float, fired: threading.Event
) -> Iterator[None]:
    """Cancela a chamada em curso da conexão quando o prazo estoura.

    Um timer chama `connection.cancel()`, que interrompe `execute`/`fetch` no
    servidor. `fired` distingue o cancelamento do watchdog de um erro qualquer.
    """

    def fire() -> None:
        fired.set()
        with contextlib.suppress(oracledb.Error):  # cancelamento best effort
            connection.cancel()

    timer = threading.Timer(max(seconds, _MIN_WAIT_SECONDS), fire)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        # Se `fire` já estava rodando, espera o `cancel()` terminar antes de a
        # conexão ser fechada: `cancel` e `close` concorrentes não são seguros.
        timer.join(CANCEL_GRACE_SECONDS)


@dataclass
class WatchdogOutcome:
    """Resultado de `run_with_cancel`.

    `abandoned` só é True com `timed_out`: a thread seguia viva depois do
    `cancel()`, então o chamador NÃO pode fechar a conexão debaixo dela.
    """

    value: Any = None
    error: BaseException | None = None
    timed_out: bool = False
    abandoned: bool = False


def run_with_cancel(
    fn: Callable[[], Any],
    connection: Callable[[], Any | None],
    seconds: float,
    *,
    owns_connection: bool = False,
    abandoned_event: threading.Event | None = None,
) -> WatchdogOutcome:
    """Roda `fn()` numa thread; no prazo, cancela a conexão devolvida por
    `connection()` (pode ser None se `fn` ainda não conectou).

    Com `owns_connection`, a própria thread fecha a conexão ao terminar, sob o
    mesmo lock do `cancel()`: `fn` não deve fechá-la (cancel e close
    concorrentes não são seguros).

    `abandoned_event` é setado quando o prazo estoura; `fn` deve checá-lo logo
    após conectar e desistir em vez de executar sem watchdog.
    """
    outcome = WatchdogOutcome()
    lock = threading.Lock()
    if abandoned_event is not None:
        abandoned_event.clear()
    state = {"abandoned": False, "done": False}

    def target() -> None:
        try:
            outcome.value = fn()
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            outcome.error = exc
        with lock:
            state["done"] = True
            late = connection() if owns_connection or state["abandoned"] else None
            if late is not None:
                # Dona da conexão, ou chamador desistiu: ninguém mais a fecha.
                with contextlib.suppress(Exception):  # limpeza best effort
                    late.close()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(max(seconds, _MIN_WAIT_SECONDS))
    if not thread.is_alive():
        return outcome
    target_connection = connection()
    if target_connection is not None:
        # Qualquer falha do cancel (não só oracledb.Error) não pode mascarar o
        # timeout: o chamador decide pelo `timed_out`.
        with lock, contextlib.suppress(Exception):  # cancelamento best effort
            if not state["done"]:
                target_connection.cancel()
        thread.join(CANCEL_GRACE_SECONDS)
    with lock:
        abandoned = not state["done"]
        state["abandoned"] = abandoned
    if abandoned_event is not None:
        # `fn` checa o evento depois de conectar: conexão atrasada não executa.
        abandoned_event.set()
    return WatchdogOutcome(timed_out=True, abandoned=abandoned)

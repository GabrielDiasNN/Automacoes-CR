"""Queda de sessão e prazos para o Oracle.

Fonte única para o runner do Beneficiamento e para as ferramentas de
`Tools/oracle`. A rede até o Oracle derruba sessões em ~4-6 s (ORA-00028 /
ORA-03113), com ou sem atividade.

Prazos, por capacidade detectada do driver (ver `oracle_client.describe_driver_mode`):

- Thin Mode, ou Thick Mode com Oracle Client 18.1+: `connection.call_timeout`
  nativo, aplicado por `call_deadline`. Ele limita cada round-trip, não o total.
- Oracle Client abaixo de 18.1 (ex.: 12.2): `call_timeout` não existe. O prazo é
  emulado por thread e `connection.cancel()` (`cancel_after`/`run_with_cancel`).

`run_with_cancel` continua sendo o watchdog de tempo total (orçamento da
consulta inteira), mesmo com `call_timeout` disponível: o nativo não limita a
soma dos round-trips de uma consulta longa.

`connect_within` segue sendo o prazo de conexão: o driver não cobre o caso de
conexão que chega depois do prazo, então a thread continua necessária.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import oracledb
from oracle_client import describe_driver_mode

__all__ = [
    "SESSION_DROP_MARKERS",
    "CallTimeoutInfo",
    "WatchdogOutcome",
    "call_deadline",
    "call_timeout_aplicado",
    "cancel_after",
    "connect_within",
    "is_call_timeout",
    "is_session_drop",
    "query_deadline",
    "run_with_cancel",
    "supports_native_call_timeout",
]

# Versão mínima do Oracle Client com `connection.call_timeout` (Thick Mode).
CALL_TIMEOUT_MIN_CLIENT = (18, 1)

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

    lock = threading.Lock()
    encerrado = (
        False  # sob `lock`: o bloco já terminou, o cancel tardio não pode mais disparar
    )

    def fire() -> None:
        nonlocal encerrado
        with lock:
            if encerrado:
                return
            fired.set()
        with contextlib.suppress(oracledb.Error):  # cancelamento best effort
            connection.cancel()

    timer = threading.Timer(max(seconds, _MIN_WAIT_SECONDS), fire)
    timer.daemon = True
    timer.start()
    concluiu = False
    try:
        yield
        concluiu = True
    finally:
        with lock:
            encerrado = True
        timer.cancel()
        # Se `fire` já estava rodando, espera o `cancel()` terminar antes de a
        # conexão ser fechada: `cancel` e `close` concorrentes não são seguros.
        timer.join(CANCEL_GRACE_SECONDS)
        if concluiu and fired.is_set():
            # O prazo estourou no instante em que a chamada terminava: o cancel chegou
            # numa conexão já ociosa. Um ping consome o break pendente, senão a próxima
            # chamada na mesma conexão (ex.: pool do MCP) receberia ORA-01013.
            ping = getattr(connection, "ping", None)
            if ping is not None:
                with contextlib.suppress(oracledb.Error):
                    ping()


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


def supports_native_call_timeout() -> bool:
    """True no Thin Mode e no Thick Mode com Oracle Client 18.1 ou superior."""
    mode = describe_driver_mode()
    if mode.mode == "thin":
        return True
    return (
        mode.client_version is not None
        and mode.client_version[:2] >= CALL_TIMEOUT_MIN_CLIENT
    )


def is_call_timeout(error: BaseException | str) -> bool:
    """True se o erro é o prazo por chamada do driver (DPY-4024 no Thin, DPI-1067 no Thick)."""
    message = str(error).upper()
    return (
        "DPY-4024" in message or "DPI-1067" in message or "CALL TIMEOUT OF" in message
    )


@dataclass(frozen=True)
class CallTimeoutInfo:
    """Resultado da tentativa de aplicar `call_timeout`: aplicado e, se não, o motivo."""

    applied: bool
    warning: str = ""


@contextlib.contextmanager
def call_timeout_aplicado(connection: Any, seconds: float) -> Iterator[CallTimeoutInfo]:
    """Fonte única de `call_timeout`: aplica (piso de 1 ms) e zera ao sair.

    Falha do driver (DPI-1050 no Client 12.2) não é exceção: volta em `warning`, e
    quem chama decide o prazo alternativo. Zerar na saída evita prazo residual no
    próximo uso da conexão (pool/sessão reaproveitada).
    """
    try:
        connection.call_timeout = max(1, int(seconds * 1000))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        yield CallTimeoutInfo(applied=False, warning=str(exc))
        return
    try:
        yield CallTimeoutInfo(applied=True)
    finally:
        with contextlib.suppress(Exception):
            connection.call_timeout = 0


@contextlib.contextmanager
def query_deadline(
    connection: Any,
    per_call_seconds: float,
    total_seconds: float,
    fired: threading.Event,
) -> Iterator[CallTimeoutInfo]:
    """Prazo por chamada (`call_timeout`, quando o driver aceita) + watchdog do total.

    `call_timeout` limita cada round-trip; `cancel_after` limita a consulta inteira e
    é o único prazo no Client 12.2. `fired` indica que o watchdog cancelou.
    """
    with contextlib.ExitStack() as pilha:
        info = pilha.enter_context(
            call_timeout_aplicado(connection, min(per_call_seconds, total_seconds))
        )
        pilha.enter_context(cancel_after(connection, total_seconds, fired))
        try:
            yield info
        except oracledb.Error as exc:
            # Prazo por chamada do driver (DPY-4024/DPI-1067): mesmo sinal do
            # watchdog para o chamador, que converte em TimeoutError.
            if is_call_timeout(exc):
                fired.set()
            raise


@contextlib.contextmanager
def call_deadline(
    connection: Any, seconds: float, fired: threading.Event
) -> Iterator[None]:
    """Prazo por chamada: `call_timeout` nativo quando há suporte; senão `cancel_after`.

    `fired` é setado quando o prazo estoura, nos dois caminhos, para o chamador
    distinguir o timeout de um erro comum.
    """
    if not supports_native_call_timeout():
        with cancel_after(connection, seconds, fired):
            yield
        return
    with call_timeout_aplicado(connection, seconds) as info:
        if not info.applied:
            with cancel_after(connection, seconds, fired):
                yield
            return
        try:
            yield
        except oracledb.Error as exc:
            if is_call_timeout(exc):
                fired.set()
            raise

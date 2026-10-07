"""Acesso Oracle controlado para refresh de snapshots."""

# pylint: disable=missing-class-docstring,broad-exception-caught,too-many-locals

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv

from .settings import (
    FETCH_ARRAY_SIZE,
    FETCH_BATCH_SIZE,
    ORACLE_CALL_TIMEOUT_MS,
    REPO_ROOT,
    WALL_CLOCK_BUDGET_SECONDS,
)

logger = logging.getLogger(__name__)

# A rede até o Oracle desta máquina derruba sessões em ~4-6 s (ORA-00028 /
# ORA-03113), com ou sem atividade. No período mensal o fetch de ~17 mil linhas
# leva 5-7 s e caía nessa janela em ~2 de 5 execuções; os extratores de domínio
# já tentam de novo com conexão nova, o runner não tentava.
# Fonte única: `Tools/oracle/medir_sql_oracle.py` e `Tools/oracle/validar_partes_oracle.py`
# importam esta lista. DPY-1001/DPI-1010 ("not connected") são a mesma classe
# (conexão já perdida). O cancelamento do watchdog (ORA-01013) não entra: é
# prazo estourado, não rede.
SESSION_DROP_MARKERS = (
    "ORA-00028",
    "ORA-03113",
    "ORA-03135",
    "DPY-1001",
    "DPY-4011",
    "DPI-1010",
    "DPI-1080",
)
MAX_QUERY_ATTEMPTS = 3
# O Orchestrator mata o subprocesso do runner em 45 s. O orçamento de wall clock
# vale para o conjunto das tentativas: cada uma recebe só o que sobrou dele, e
# nova tentativa só começa se sobrar ao menos este mínimo (conexão + consulta).
MIN_RETRY_REMAINING_SECONDS = 3.0


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    duplicate_columns: dict[str, list[int]]
    metadata: dict[str, Any]


def _path_exists(path_value: str | None) -> bool:
    if not path_value:
        return False
    try:
        return Path(path_value).exists()
    except OSError:
        return False


def _make_unique_names(raw_names: list[str]) -> tuple[list[str], dict[str, list[int]]]:
    seen: dict[str, int] = {}
    unique_names: list[str] = []
    positions: dict[str, list[int]] = {}
    for index, name in enumerate(raw_names, start=1):
        seen[name] = seen.get(name, 0) + 1
        positions.setdefault(name, []).append(index)
        unique_names.append(name if seen[name] == 1 else f"{name}__{seen[name]}")
    duplicates = {name: idxs for name, idxs in positions.items() if len(idxs) > 1}
    return unique_names, duplicates


def connect_readonly() -> Any:
    load_dotenv(REPO_ROOT / ".env", override=True)
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get(
        "ORACLE_CLIENT_PATH"
    )
    tns_admin = os.environ.get("TNS_ADMIN")

    if not user or not password or not dsn:
        raise RuntimeError(
            "Ambiente Oracle incompleto. Verifique ORACLE_READONLY_USER, "
            "ORACLE_READONLY_PASSWORD e ORACLE_CONNECT_STRING."
        )

    if _path_exists(client_lib):
        try:
            oracledb.init_oracle_client(
                lib_dir=client_lib,
                config_dir=tns_admin if _path_exists(tns_admin) else None,
            )
        except Exception as e:
            logger.warning(
                "Falha ao inicializar Oracle Thick Mode (seguindo em Thin Mode): %s", e
            )

    return oracledb.connect(user=user, password=password, dsn=dsn)


def _is_session_drop(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in SESSION_DROP_MARKERS)


def execute_query(
    sql: str,
    parameters: Mapping[str, Any] | None = None,
    *,
    oracle_timeout_ms: int = ORACLE_CALL_TIMEOUT_MS,
    wall_clock_budget_seconds: float = WALL_CLOCK_BUDGET_SECONDS,
    max_rows: int | None = None,
) -> QueryResult:
    """Executa a consulta; sessão derrubada pela rede é tentada de novo com
    conexão nova. Erro de SQL, de credencial ou estouro do orçamento de tempo
    (`TimeoutError`) falham na hora. `wall_clock_budget_seconds` limita o total
    de todas as tentativas: cada uma recebe apenas o orçamento restante (e um
    `call_timeout` no máximo igual a ele)."""
    started = time.perf_counter()
    attempt = 1
    remaining = float(wall_clock_budget_seconds)
    attempt_timeout_ms = int(oracle_timeout_ms)
    while True:
        try:
            result = _execute_once(
                sql,
                parameters,
                oracle_timeout_ms=attempt_timeout_ms,
                wall_clock_budget_seconds=remaining,
                max_rows=max_rows,
            )
        # `oracledb.Error`, não só DatabaseError: DPY-1001 (e DPI-1010, remapeado
        # para ele) chega como InterfaceError, que não é subclasse de DatabaseError.
        except oracledb.Error as exc:
            elapsed = time.perf_counter() - started
            remaining = wall_clock_budget_seconds - elapsed
            if (
                not _is_session_drop(exc)
                or attempt >= MAX_QUERY_ATTEMPTS
                or remaining < MIN_RETRY_REMAINING_SECONDS
            ):
                raise
            attempt_timeout_ms = min(int(oracle_timeout_ms), int(remaining * 1000))
            logger.warning(
                "Sessao Oracle derrubada na tentativa %s/%s apos %.1fs; nova conexao.",
                attempt,
                MAX_QUERY_ATTEMPTS,
                elapsed,
            )
            attempt += 1
            continue
        result.metadata["attempts"] = attempt
        return result


def _connect_within(seconds: float) -> Any:
    """`connect_readonly()` com prazo: o driver não impõe um no client 12.2.

    A conexão roda numa thread daemon. Se o prazo estoura, levanta
    `TimeoutError`; a thread abandonada fecha a conexão sozinha se ela ainda
    vier a se estabelecer, sem vazar sessão nem ser usada por outra thread.
    """
    holder: dict[str, Any] = {}
    lock = threading.Lock()
    abandoned = False

    def target() -> None:
        try:
            connection = connect_readonly()
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
    thread.join(max(seconds, 0.05))
    with lock:
        if "connection" in holder:
            return holder["connection"]
        if "error" not in holder:
            abandoned = True
            raise TimeoutError(
                f"Conexão Oracle do Beneficiamento excedeu {seconds:g}s."
            )
    raise holder["error"]


@contextlib.contextmanager
def _cancel_after(
    connection: Any, seconds: float, fired: threading.Event
) -> Iterator[None]:
    """Cancela a chamada em curso da conexão quando o prazo estoura.

    Substitui o `call_timeout` (indisponível no Oracle Client 12.2): um timer
    chama `connection.cancel()`, que interrompe `execute`/`fetch` no servidor.
    `fired` distingue o cancelamento do watchdog de um erro qualquer do Oracle.
    """

    def fire() -> None:
        fired.set()
        with contextlib.suppress(oracledb.Error):  # cancelamento best effort
            connection.cancel()

    timer = threading.Timer(max(seconds, 0.05), fire)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        # Se `fire` já estava rodando, espera o `cancel()` terminar antes de a
        # conexão ser fechada: `cancel` e `close` concorrentes não são seguros.
        timer.join(5)


def _execute_once(
    sql: str,
    parameters: Mapping[str, Any] | None,
    *,
    oracle_timeout_ms: int,
    wall_clock_budget_seconds: float,
    max_rows: int | None,
) -> QueryResult:
    query_started_at = time.perf_counter()
    watchdog_fired = threading.Event()
    connection = _connect_within(wall_clock_budget_seconds)
    with connection, contextlib.ExitStack() as guards:
        timeout_applied = False
        timeout_warning = ""
        try:
            connection.call_timeout = int(oracle_timeout_ms)
            timeout_applied = True
        except Exception as exc:
            timeout_warning = str(exc)
        if not timeout_applied:
            # Oracle Client 12.2 não suporta call_timeout (DPI-1050): sem isto o
            # execute ficaria sem prazo e passaria dos 45 s do Orchestrator.
            guards.enter_context(
                _cancel_after(
                    connection,
                    wall_clock_budget_seconds
                    - (time.perf_counter() - query_started_at),
                    watchdog_fired,
                )
            )

        try:
            with connection.cursor() as cursor:
                cursor.arraysize = FETCH_ARRAY_SIZE
                cursor.execute(sql, dict(parameters or {}))
                if not cursor.description:
                    elapsed = time.perf_counter() - query_started_at
                    return QueryResult(
                        columns=[],
                        rows=[],
                        duplicate_columns={},
                        metadata={
                            "oracle_timeout_ms": int(oracle_timeout_ms),
                            "oracle_timeout_applied": timeout_applied,
                            "oracle_timeout_warning": timeout_warning,
                            "elapsed_seconds": round(elapsed, 4),
                            "row_count": 0,
                        },
                    )

                raw_names = [column[0] for column in cursor.description]
                columns, duplicate_columns = _make_unique_names(raw_names)
                rows: list[tuple[Any, ...]] = []

                while True:
                    if (
                        time.perf_counter() - query_started_at
                    ) > wall_clock_budget_seconds:
                        raise TimeoutError(
                            f"Consulta Beneficiamento excedeu {wall_clock_budget_seconds:g}s."
                        )
                    batch = cursor.fetchmany(FETCH_BATCH_SIZE)
                    if not batch:
                        break
                    if max_rows and max_rows > 0:
                        remaining = max_rows - len(rows)
                        if remaining <= 0:
                            break
                        rows.extend(batch[:remaining])
                        if len(rows) >= max_rows:
                            break
                    else:
                        rows.extend(batch)
        except oracledb.DatabaseError as exc:
            if watchdog_fired.is_set():
                raise TimeoutError(
                    f"Consulta Beneficiamento excedeu {wall_clock_budget_seconds:g}s "
                    "(cancelada pelo watchdog)."
                ) from exc
            raise

    elapsed = time.perf_counter() - query_started_at
    return QueryResult(
        columns=columns,
        rows=rows,
        duplicate_columns=duplicate_columns,
        metadata={
            "oracle_timeout_ms": int(oracle_timeout_ms),
            "oracle_timeout_applied": timeout_applied,
            "oracle_timeout_warning": timeout_warning,
            "oracle_watchdog_applied": not timeout_applied,
            "elapsed_seconds": round(elapsed, 4),
            "row_count": len(rows),
            "max_rows_limit": max_rows if max_rows and max_rows > 0 else None,
        },
    )

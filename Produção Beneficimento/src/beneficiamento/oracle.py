"""Acesso Oracle controlado para refresh de snapshots."""

# pylint: disable=missing-class-docstring,broad-exception-caught,too-many-locals

from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import oracledb
from dotenv import load_dotenv

from .settings import (
    FETCH_ARRAY_SIZE,
    FETCH_BATCH_SIZE,
    LIB_PYTHON_DIR,
    ORACLE_CALL_TIMEOUT_MS,
    REPO_ROOT,
    WALL_CLOCK_BUDGET_SECONDS,
)

# `oracle_session` vive em `lib/python`: o pacote resolve o caminho sozinho, sem
# depender de cada entrypoint (runner, API, testes, CLI) lembrar de injetá-lo.
if str(LIB_PYTHON_DIR) not in sys.path:
    sys.path.append(str(LIB_PYTHON_DIR))

from oracle_client import (  # noqa: E402  pylint: disable=wrong-import-position
    connect_adaptive,
)
from oracle_session import (  # noqa: E402  pylint: disable=wrong-import-position
    connect_within,
    is_call_timeout,
    is_session_drop,
    query_deadline,
)

logger = logging.getLogger(__name__)

# A rede até o Oracle desta máquina derruba sessões em ~4-6 s. No período
# mensal o fetch de ~17 mil linhas leva 5-7 s e caía nessa janela em ~2 de 5
# execuções: sessão derrubada é tentada de novo com conexão nova. Marcadores de
# queda e prazos para o Client 12.2: `lib/python/oracle_session.py`.
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


def _log_driver(message: str, level: str = "INFO") -> None:
    """Mensagens do driver adaptativo para o logger do runner."""
    if level == "WARN":
        logger.warning("%s", message)
    else:
        logger.info("%s", message)


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

    return connect_adaptive(
        user=user,
        password=password,
        dsn=dsn,
        client_lib=client_lib,
        tns_admin=tns_admin,
        log_fn=_log_driver,
    )


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
                not is_session_drop(exc)
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
    """`connect_readonly()` com prazo (ver `oracle_session.connect_within`)."""
    return connect_within(connect_readonly, seconds)


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
        # O orçamento corre desde o início da tentativa, então o tempo de conexão
        # (Thin/Thick, às vezes segundos na WAN) já sai do que resta para a consulta.
        remaining = wall_clock_budget_seconds - (time.perf_counter() - query_started_at)
        if remaining <= 0:
            raise TimeoutError(
                f"Orçamento de {wall_clock_budget_seconds:g}s esgotado antes da consulta."
            )
        # `call_timeout` limita cada round-trip; o watchdog limita o total da consulta.
        # Em Oracle Client 12.2 (DPI-1050) o watchdog é o único prazo. Fonte única
        # em oracle_session.query_deadline, que também zera o call_timeout ao sair.
        prazo = guards.enter_context(
            query_deadline(
                connection, oracle_timeout_ms / 1000, remaining, watchdog_fired
            )
        )
        timeout_applied = prazo.applied
        timeout_warning = prazo.warning

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
        except oracledb.Error as exc:
            # `is_call_timeout` cobre o prazo por chamada do driver: o `fired` de
            # query_deadline só é setado depois que este bloco termina, então sozinho
            # ele não veria o DPY-4024 desta mesma exceção.
            if watchdog_fired.is_set() or is_call_timeout(exc):
                raise TimeoutError(
                    f"Consulta Beneficiamento excedeu {wall_clock_budget_seconds:g}s "
                    "(prazo da chamada ou watchdog)."
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
            # O watchdog (query_deadline) é armado em toda tentativa, com ou sem `call_timeout`.
            "oracle_watchdog_applied": True,
            "elapsed_seconds": round(elapsed, 4),
            "row_count": len(rows),
            "max_rows_limit": max_rows if max_rows and max_rows > 0 else None,
        },
    )

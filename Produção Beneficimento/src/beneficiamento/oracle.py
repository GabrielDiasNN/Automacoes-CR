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
from pathlib import Path
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

from oracle_session import (  # noqa: E402  pylint: disable=wrong-import-position
    cancel_after,
    connect_within,
    is_session_drop,
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
                cancel_after(
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
        except oracledb.Error as exc:
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

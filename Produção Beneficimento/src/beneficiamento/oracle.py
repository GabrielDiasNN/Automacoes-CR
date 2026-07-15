"""Acesso Oracle controlado para refresh de snapshots."""
# pylint: disable=missing-class-docstring,broad-exception-caught,too-many-locals

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

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
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get("ORACLE_CLIENT_PATH")
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
    wall_clock_budget_seconds: int = WALL_CLOCK_BUDGET_SECONDS,
    max_rows: int | None = None,
) -> QueryResult:
    query_started_at = time.perf_counter()
    with connect_readonly() as connection:
        timeout_applied = False
        timeout_warning = ""
        try:
            connection.call_timeout = int(oracle_timeout_ms)
            timeout_applied = True
        except Exception as exc:
            timeout_warning = str(exc)

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
                if (time.perf_counter() - query_started_at) > wall_clock_budget_seconds:
                    raise TimeoutError(
                        f"Consulta Beneficiamento excedeu {wall_clock_budget_seconds}s."
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

    elapsed = time.perf_counter() - query_started_at
    return QueryResult(
        columns=columns,
        rows=rows,
        duplicate_columns=duplicate_columns,
        metadata={
            "oracle_timeout_ms": int(oracle_timeout_ms),
            "oracle_timeout_applied": timeout_applied,
            "oracle_timeout_warning": timeout_warning,
            "elapsed_seconds": round(elapsed, 4),
            "row_count": len(rows),
            "max_rows_limit": max_rows if max_rows and max_rows > 0 else None,
        },
    )

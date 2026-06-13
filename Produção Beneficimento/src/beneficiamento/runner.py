"""Runner controlado para gerar snapshots e carregar histórico do Beneficiamento."""

# pylint: disable=too-many-arguments,too-many-locals,broad-exception-caught,line-too-long,trailing-whitespace

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .analytics import build_analytics
from .data.writer import salvar_historico
from .oracle import QueryResult, execute_query
from .profile import profile_rows, rows_to_records, summarize_profiles
from .quality import assess_quality
from .settings import (ORACLE_CALL_TIMEOUT_MS, PERIOD_ORDER, SNAPSHOT_DIR,
                       WALL_CLOCK_BUDGET_SECONDS)
from .snapshot_store import snapshot_path, write_json_atomic
from .sql_repository import (apply_rownum_limit, bind_parameters,
                             load_sql_template, period_window)


def _load_sql_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def _next_month(current: date) -> date:
    if current.month == 12:
        return date(current.year + 1, 1, 1)
    return date(current.year, current.month + 1, 1)


def _dt_range_seconds(start_dt: datetime, end_dt: datetime) -> float:
    return max(0.0, (end_dt - start_dt).total_seconds())


def _is_timeout_like_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "ora-00028",
            "ora-01013",
            "dpy-4011",
            "dpi-1080",
            "consulta beneficiamento excedeu",
        )
    )


def _split_datetime_range(
    start_dt: datetime, end_dt: datetime
) -> tuple[datetime, datetime] | None:
    if end_dt <= start_dt:
        return None
    midpoint = start_dt + (end_dt - start_dt) / 2
    if midpoint <= start_dt or midpoint >= end_dt:
        return None
    return midpoint, end_dt


def _execute_query_in_monthly_slices(
    sql: str,
    start_date: date,
    end_date: date,
    *,
    oracle_timeout_ms: int,
    max_rows: int | None,
) -> QueryResult:
    """Executa a janela anual em fatias mensais com split adaptativo.

    Estrategia: cada mes vira uma fatia em ``pending_ranges`` (FIFO). Se uma
    fatia falha por timeout do Oracle (ver ``_is_timeout_like_failure``) e ainda
    tem mais de 1 hora de janela, ela e dividida ao meio e as duas metades sao
    reinseridas no inicio da fila (ordem temporal preservada). Falhas nao-timeout,
    janelas <= 1h ou indivisiveis sao propagadas. Os metadados de timeout sao
    consolidados ao final: ``oracle_timeout_applied`` so e True se todas as fatias
    aplicaram ``call_timeout`` no client.
    """
    all_rows: list[tuple[Any, ...]] = []
    columns: list[str] = []
    duplicate_columns: dict[str, list[int]] = {}
    slice_metadata: list[dict[str, Any]] = []
    timeout_applied_flags: list[bool] = []
    timeout_warnings: list[str] = []
    pending_ranges: list[tuple[datetime, datetime]] = []
    current = start_date
    while current < end_date:
        next_slice = min(_next_month(current), end_date)
        pending_ranges.append(
            (
                datetime.combine(current, time.min),
                datetime.combine(next_slice, time.min),
            )
        )
        current = next_slice
    row_limit_remaining = max_rows if max_rows and max_rows > 0 else None

    while pending_ranges:
        start_dt, end_dt = pending_ranges.pop(0)
        if row_limit_remaining is not None and row_limit_remaining <= 0:
            break

        params = {"dt_inicio": start_dt, "dt_fim": end_dt}
        try:
            result = execute_query(
                sql,
                params,
                oracle_timeout_ms=oracle_timeout_ms,
                wall_clock_budget_seconds=WALL_CLOCK_BUDGET_SECONDS,
                max_rows=row_limit_remaining,
            )
        except Exception as exc:
            remaining_seconds = _dt_range_seconds(start_dt, end_dt)
            split_range = _split_datetime_range(start_dt, end_dt)
            if (
                split_range is None
                or remaining_seconds <= 3600
                or not _is_timeout_like_failure(exc)
            ):
                raise
            midpoint, slice_end = split_range
            pending_ranges.insert(0, (midpoint, slice_end))
            pending_ranges.insert(0, (start_dt, midpoint))
            continue

        if not columns:
            columns = result.columns
            duplicate_columns = result.duplicate_columns
        all_rows.extend(result.rows)
        if row_limit_remaining is not None:
            row_limit_remaining -= len(result.rows)
        timeout_applied = bool(result.metadata.get("oracle_timeout_applied"))
        timeout_applied_flags.append(timeout_applied)
        warning = str(result.metadata.get("oracle_timeout_warning") or "").strip()
        if warning:
            timeout_warnings.append(warning)
        slice_metadata.append(
            {
                "dt_inicio": start_dt.isoformat(),
                "dt_fim": end_dt.isoformat(),
                "row_count": len(result.rows),
                "elapsed_seconds": result.metadata.get("elapsed_seconds"),
            }
        )

    total_elapsed = sum(
        float(item.get("elapsed_seconds") or 0) for item in slice_metadata
    )
    oracle_timeout_applied = (
        all(timeout_applied_flags) if timeout_applied_flags else False
    )
    if timeout_warnings:
        oracle_timeout_warning = "; ".join(dict.fromkeys(timeout_warnings))
    elif oracle_timeout_applied:
        oracle_timeout_warning = ""
    else:
        oracle_timeout_warning = (
            "uma ou mais fatias anuais nao aplicaram call_timeout no cliente Oracle"
        )
    return QueryResult(
        columns=columns,
        rows=all_rows,
        duplicate_columns=duplicate_columns,
        metadata={
            "oracle_timeout_ms": int(oracle_timeout_ms),
            "oracle_timeout_applied": oracle_timeout_applied,
            "oracle_timeout_warning": oracle_timeout_warning,
            "elapsed_seconds": round(total_elapsed, 4),
            "row_count": len(all_rows),
            "slice_count": len(slice_metadata),
            "slices": slice_metadata,
            "max_rows_limit": max_rows if max_rows and max_rows > 0 else None,
        },
    )


def _build_snapshot_payloads_from_result(
    period: str,
    result: QueryResult,
    *,
    sample_limit: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    records = rows_to_records(result.columns, result.rows)
    profiles = profile_rows(result.columns, result.rows, sample_limit)
    profile = summarize_profiles(profiles, len(result.rows), result.duplicate_columns)
    analytics = build_analytics(records)
    analytics["execucao_oracle"] = {"consulta_principal": result.metadata}
    analytics["qualidade"] = assess_quality(period, profile, records)
    analytics["snapshot"] = {
        "period": period,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return profile, analytics, records


def _classify_refresh_status(
    analytics: dict[str, Any], history_write_failed: bool
) -> str:
    if history_write_failed:
        return "partial_failure"

    quality_status = str((analytics.get("qualidade") or {}).get("status") or "").lower()
    oracle_meta = (analytics.get("execucao_oracle") or {}).get(
        "consulta_principal"
    ) or {}
    if quality_status in {"attention", "blocked"}:
        return "attention"
    if oracle_meta.get("oracle_timeout_applied") is False:
        return "attention"
    return "ok"


def build_snapshot_payloads(
    period: str,
    sql: str,
    parameters: dict[str, Any],
    *,
    oracle_timeout_ms: int,
    max_rows: int | None,
    sample_limit: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    result = execute_query(
        sql,
        parameters,
        oracle_timeout_ms=oracle_timeout_ms,
        wall_clock_budget_seconds=WALL_CLOCK_BUDGET_SECONDS,
        max_rows=max_rows,
    )
    return _build_snapshot_payloads_from_result(
        period, result, sample_limit=sample_limit
    )


def run_period(
    period: str,
    *,
    reference: date | None = None,
    sql_file: Path | None = None,
    output_json: Path | None = None,
    analytics_json: Path | None = None,
    snapshot_dir: Path = SNAPSHOT_DIR,
    oracle_timeout_ms: int = ORACLE_CALL_TIMEOUT_MS,
    max_rows: int | None = None,
    sample_limit: int = 3,
    use_rownum_limit: bool = False,
) -> tuple[Path, Path, str]:
    if period not in PERIOD_ORDER:
        raise ValueError(f"Periodo invalido: {period}")

    sql = _load_sql_file(sql_file) if sql_file else load_sql_template(period)
    sql = apply_rownum_limit(sql, max_rows) if use_rownum_limit and max_rows else sql
    parameters = {} if sql_file else bind_parameters(period, reference)
    window_start, window_end = period_window(period, reference)

    if period == "anual" and not sql_file:
        result = _execute_query_in_monthly_slices(
            sql,
            window_start,
            window_end,
            oracle_timeout_ms=oracle_timeout_ms,
            max_rows=max_rows,
        )
        profile, analytics, records = _build_snapshot_payloads_from_result(
            period,
            result,
            sample_limit=sample_limit,
        )
    else:
        profile, analytics, records = build_snapshot_payloads(
            period,
            sql,
            parameters,
            oracle_timeout_ms=oracle_timeout_ms,
            max_rows=max_rows,
            sample_limit=sample_limit,
        )

    history_write_failed = False
    history_write_error = ""
    snapshot_meta = analytics.setdefault("snapshot", {})

    # Salvar no SQLite Histórico de forma transparente e idempotente para garantir dados sempre atualizados
    try:
        qt_salvos = salvar_historico(records)
        snapshot_meta["historico_rows_saved"] = qt_salvos
        snapshot_meta["historico_write_status"] = "ok"
    except Exception as exc:
        history_write_failed = True
        history_write_error = str(exc)
        snapshot_meta["historico_rows_saved"] = 0
        snapshot_meta["historico_write_status"] = "partial_failure"
        snapshot_meta["historico_write_error"] = history_write_error
        print(
            f"Aviso: falha ao salvar dados no SQLite historico: {exc}", file=sys.stderr
        )

    refresh_status = _classify_refresh_status(analytics, history_write_failed)
    snapshot_meta["refresh_status"] = refresh_status
    snapshot_meta["status"] = refresh_status

    profile["sql_file"] = str(sql_file) if sql_file else f"template:{period}"
    profile["window"] = {
        "dt_inicio": window_start.isoformat(),
        "dt_fim": window_end.isoformat(),
    }
    analytics["window"] = profile["window"]

    profile_path = output_json or snapshot_path(period, "profile", snapshot_dir)
    analytics_path = analytics_json or snapshot_path(period, "analytics", snapshot_dir)
    write_json_atomic(profile_path, profile)
    write_json_atomic(analytics_path, analytics)
    return profile_path, analytics_path, refresh_status


def run_historical_range(
    start_date: date,
    end_date: date,
    *,
    oracle_timeout_ms: int = ORACLE_CALL_TIMEOUT_MS,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Carga retroativa fatiada por dia no historico SQLite.

    Itera dia a dia no intervalo [start_date, end_date], executando o template
    detalhado por fatia e gravando idempotentemente via ``salvar_historico``.
    Falhas de uma fatia sao registradas em ``erros`` sem abortar as demais; o
    status final e ``completed_with_errors`` se houver qualquer falha.
    """
    sql = load_sql_template("diario")  # Usa o template detalhado

    current = start_date
    total_inserted = 0
    fatias_processadas = 0
    erros = []

    print(f"Iniciando carga historica de {start_date} ate {end_date}...", flush=True)

    while current <= end_date:
        next_day = current + timedelta(days=1)
        params = {
            "dt_inicio": datetime.combine(current, time.min),
            "dt_fim": datetime.combine(next_day, time.min),
        }

        print(f"-> Executando fatia dia {current.isoformat()}... ", end="", flush=True)
        try:
            result = execute_query(
                sql,
                params,
                oracle_timeout_ms=oracle_timeout_ms,
                wall_clock_budget_seconds=WALL_CLOCK_BUDGET_SECONDS,
                max_rows=max_rows,
            )
            records = rows_to_records(result.columns, result.rows)
            inserted = salvar_historico(records)
            total_inserted += inserted
            fatias_processadas += 1
            print(
                f"OK ({len(records)} linhas lidas, {inserted} salvas/atualizadas no SQLite).",
                flush=True,
            )
        except Exception as exc:
            erros.append({"data": current.isoformat(), "erro": str(exc)})
            print(f"FALHA: {exc}", flush=True)

        current = next_day

    return {
        "status": "ok" if not erros else "completed_with_errors",
        "fatias_processadas": fatias_processadas,
        "total_linhas_salvas": total_inserted,
        "erros": erros,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera snapshots locais de producao do Beneficiamento e alimenta historico SQLite."
    )
    parser.add_argument("--period", choices=PERIOD_ORDER, default="diario")
    parser.add_argument("--sql-file", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--analytics-json", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--oracle-timeout-ms", type=int, default=ORACLE_CALL_TIMEOUT_MS)
    parser.add_argument("--sample-limit", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--use-rownum-limit", action="store_true")

    # Novos parametros de range historico retroativo
    parser.add_argument(
        "--range-start", type=str, default=None, help="Data inicial YYYY-MM-DD"
    )
    parser.add_argument(
        "--range-end", type=str, default=None, help="Data final YYYY-MM-DD"
    )

    args = parser.parse_args(argv)

    # Fluxo 1: Carga retroativa fatiada no SQLite historico se range for informado
    if args.range_start:
        try:
            start_date = datetime.strptime(args.range_start, "%Y-%m-%d").date()
            end_date = (
                datetime.strptime(args.range_end, "%Y-%m-%d").date()
                if args.range_end
                else date.today()
            )
        except ValueError:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_type": "ValueError",
                        "message": "As datas devem estar no formato YYYY-MM-DD.",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

        res = run_historical_range(
            start_date,
            end_date,
            oracle_timeout_ms=args.oracle_timeout_ms,
            max_rows=args.max_rows if args.max_rows > 0 else None,
        )
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["status"] == "ok" else 1

    # Fluxo 2: Geracao comum de snapshot operacional + gravacao no SQLite historico
    try:
        profile_path, analytics_path, refresh_status = run_period(
            args.period,
            sql_file=args.sql_file,
            output_json=args.output_json,
            analytics_json=args.analytics_json,
            snapshot_dir=args.snapshot_dir,
            oracle_timeout_ms=args.oracle_timeout_ms,
            max_rows=args.max_rows if args.max_rows > 0 else None,
            sample_limit=args.sample_limit,
            use_rownum_limit=args.use_rownum_limit,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "period": args.period,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": refresh_status,
                "refresh_status": refresh_status,
                "period": args.period,
                "profile_json": str(profile_path),
                "analytics_json": str(analytics_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if refresh_status in {"ok", "attention"} else 1

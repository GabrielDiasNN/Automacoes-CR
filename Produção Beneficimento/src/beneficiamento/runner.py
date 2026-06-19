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
    analytics_json: Path | None = None,
    snapshot_dir: Path = SNAPSHOT_DIR,
    oracle_timeout_ms: int = ORACLE_CALL_TIMEOUT_MS,
    max_rows: int | None = None,
    sample_limit: int = 3,
    use_rownum_limit: bool = False,
) -> tuple[Path, str]:
    if period not in PERIOD_ORDER:
        raise ValueError(f"Periodo invalido: {period}")

    sql = _load_sql_file(sql_file) if sql_file else load_sql_template(period)
    sql = apply_rownum_limit(sql, max_rows) if use_rownum_limit and max_rows else sql
    parameters = {} if sql_file else bind_parameters(period, reference)
    window_start, window_end = period_window(period, reference)

    _, analytics, records = build_snapshot_payloads(
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

    # O profile permanece apenas em memória (alimenta o quality gate acima);
    # não é mais persistido como artefato nem servido pela API.
    analytics["window"] = {
        "dt_inicio": window_start.isoformat(),
        "dt_fim": window_end.isoformat(),
    }

    analytics_path = analytics_json or snapshot_path(period, "analytics", snapshot_dir)
    write_json_atomic(analytics_path, analytics)
    return analytics_path, refresh_status


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
        analytics_path, refresh_status = run_period(
            args.period,
            sql_file=args.sql_file,
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
                "analytics_json": str(analytics_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if refresh_status in {"ok", "attention"} else 1

"""Mede o custo real (fetch completo) de uma consulta do acervo no Oracle.

Complementa `validar_sql_oracle.py`: aquele confirma que a consulta executa e
lê 1 linha; este mede quanto custa trazer o resultado inteiro. Cada execução
abre uma conexão nova (a rede derruba sessões longas, ORA-00028) e o resultado
é a mediana de N execuções, com o ruído (máx − mín) ao lado — só diferença
acima do ruído conta como melhora.

O usuário de leitura não enxerga `V$SQL`/`DISPLAY_CURSOR`, então a métrica é
tempo de parede do fetch completo; `--explain` mostra o plano estimado apenas
como hipótese. O `--dump` grava o resultado no formato lido por
`comparar_equivalencia.py`, para provar que uma reescrita não muda a saída.
A consulta passa antes pelo `guard_sql.py`; o único efeito de escrita é o
`--explain`, cujo `EXPLAIN PLAN` grava na `PLAN_TABLE` temporária da sessão.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "Produção Beneficimento" / "src"))

from beneficiamento.oracle import SESSION_DROP_MARKERS  # noqa: E402
from oracle_catalog import GuardError  # noqa: E402
from oracle_extract import (  # noqa: E402
    compute_hash,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from validar_sql_oracle import (  # noqa: E402
    _bind_names,
    _default_binds,
    _error_summary,
    _guard,
    _parse_bind_args,
    _single_statement,
    resolve_guard,
)

MEASURE_VERSION = "1.0.0"
DEFAULT_RUNS = 5
MIN_RUNS = 3
DEFAULT_TIMEOUT = 20
DEFAULT_ARRAYSIZE = 500
DEFAULT_MIN_GAIN_PCT = 2.0
MAX_ATTEMPTS = 3
# Erros de rede/sessão: repetir com conexão nova. Lista única em
# `beneficiamento/oracle.py` (o runner do Beneficiamento).
TRANSIENT_MARKERS = SESSION_DROP_MARKERS


@dataclass(frozen=True)
class MeasureOptions:
    """Parâmetros iguais para todas as execuções de uma medição."""

    runs: int
    timeout: int
    arraysize: int
    keep_first_rows: bool


def is_transient(message: str) -> bool:
    """True se o erro é queda de rede/sessão, e não defeito da consulta."""
    return any(marker in message for marker in TRANSIENT_MARKERS)


def summarize(times_ms: list[float]) -> dict[str, float | int]:
    """Mediana e ruído (máx − mín) de uma série de tempos, em ms."""
    if not times_ms:
        raise ValueError("Sem tempos para resumir")
    return {
        "n": len(times_ms),
        "median_ms": round(statistics.median(times_ms), 1),
        "min_ms": round(min(times_ms), 1),
        "max_ms": round(max(times_ms), 1),
        "noise_ms": round(max(times_ms) - min(times_ms), 1),
    }


def decide(
    baseline: dict[str, Any], candidate: dict[str, Any], min_gain_pct: float
) -> dict[str, Any]:
    """Classifica o candidato contra a baseline: MELHORA, NEUTRO ou PIOR.

    Só há melhora se o ganho da mediana superar o ruído da baseline **e** o
    ganho mínimo percentual; diferença menor é NEUTRO (reverter).
    """
    base_median = float(baseline["median_ms"])
    threshold = max(float(baseline["noise_ms"]), base_median * min_gain_pct / 100)
    gain = base_median - float(candidate["median_ms"])
    if gain > threshold:
        verdict = "MELHORA"
    elif gain < -threshold:
        verdict = "PIOR"
    else:
        verdict = "NEUTRO"
    return {
        "verdict": verdict,
        "gain_ms": round(gain, 1),
        "gain_pct": round(gain / base_median * 100, 1) if base_median else 0.0,
        "threshold_ms": round(threshold, 1),
    }


def _unique_names(names: list[str]) -> list[str]:
    """`A, A` vira `A, A__2`: `serialize_rows` indexa por nome e perderia a 1ª coluna."""
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        unique.append(name if seen[name] == 1 else f"{name}__{seen[name]}")
    return unique


def _failure(exc: BaseException) -> dict[str, Any]:
    message = _error_summary(exc)
    status = "transient" if is_transient(message) else "error"
    return {"status": status, "error": message}


def _drain(cursor: Any, arraysize: int, keep: bool) -> tuple[int, list[Any]]:
    """Busca todas as linhas; só as guarda quando o dump foi pedido."""
    count = 0
    kept: list[Any] = []
    while True:
        batch = cursor.fetchmany(arraysize)
        if not batch:
            return count, kept
        count += len(batch)
        if keep:
            kept.extend(batch)


def _timed_fetch(
    connection: Any,
    sql: str,
    binds: dict[str, Any],
    options: MeasureOptions,
    keep: bool,
) -> dict[str, Any]:
    cursor = connection.cursor()
    cursor.arraysize = options.arraysize
    cursor.prefetchrows = options.arraysize
    try:
        started = time.perf_counter()
        cursor.execute(sql, binds)
        execute_ms = (time.perf_counter() - started) * 1000
        description = cursor.description or []
        columns = _unique_names([column[0] for column in description])
        types = {
            name: column[1].name
            for name, column in zip(columns, description, strict=True)
        }
        count, rows = _drain(cursor, options.arraysize, keep)
        total_ms = (time.perf_counter() - started) * 1000
    finally:
        cursor.close()
    return {
        "status": "ok",
        "execute_ms": round(execute_ms, 1),
        "total_ms": round(total_ms, 1),
        "rows": count,
        "columns": columns,
        "types": types,
        "data": rows,
    }


def _run_watched(
    connection: Any,
    sql: str,
    binds: dict[str, Any],
    options: MeasureOptions,
    keep: bool,
) -> dict[str, Any]:
    """Executa numa thread e cancela a sessão se passar do prazo."""
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result.update(_timed_fetch(connection, sql, binds, options, keep))
        except (oracledb.Error, AttributeError, RuntimeError, ValueError) as exc:
            result.update(_failure(exc))

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(options.timeout)
    if thread.is_alive():
        with contextlib.suppress(oracledb.Error):  # cancelamento best effort
            connection.cancel()
        thread.join(5)
        # Thread ainda viva: o chamador não pode fechar a conexão debaixo dela.
        return {"status": "timeout", "abandoned": thread.is_alive()}
    return result


def _attempt(
    creds: Any,
    sql: str,
    binds: dict[str, Any],
    options: MeasureOptions,
    keep: bool,
) -> dict[str, Any]:
    try:
        connection = oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        )
    except oracledb.Error as exc:
        return _failure(exc)
    outcome: dict[str, Any] = {}
    try:
        outcome = _run_watched(connection, sql, binds, options, keep)
        return outcome
    finally:
        if not outcome.pop("abandoned", False):
            with contextlib.suppress(oracledb.Error):  # limpeza best effort
                connection.close()


def _run_with_retry(
    creds: Any,
    sql: str,
    binds: dict[str, Any],
    options: MeasureOptions,
    keep: bool,
) -> dict[str, Any]:
    """Repete com conexão nova em queda de rede; erro de SQL falha na hora."""
    outcome: dict[str, Any] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        outcome = _attempt(creds, sql, binds, options, keep)
        outcome["attempts"] = attempt
        if outcome["status"] != "transient":
            break
    return outcome


def measure(
    creds: Any, sql: str, binds: dict[str, Any], options: MeasureOptions
) -> dict[str, Any]:
    """Roda `options.runs` execuções e devolve runs, resumo e o dump (1ª boa)."""
    runs: list[dict[str, Any]] = []
    dump: dict[str, Any] | None = None
    for _ in range(options.runs):
        keep = options.keep_first_rows and dump is None
        outcome = _run_with_retry(creds, sql, binds, options, keep)
        if keep and outcome["status"] == "ok":
            dump = {
                "columns": outcome["columns"],
                "types": outcome["types"],
                "data": outcome["data"],
            }
        outcome.pop("data", None)
        outcome.pop("types", None)
        runs.append(outcome)
    good = [run for run in runs if run["status"] == "ok"]
    summary = summarize([run["total_ms"] for run in good]) if good else None
    row_counts = {run["rows"] for run in good}
    return {
        "runs": runs,
        "valid_runs": len(good),
        "summary": summary,
        "sufficient": len(good) >= MIN_RUNS,
        "row_count_stable": len(row_counts) <= 1,
        "dump": dump,
    }


def write_dump(dump: dict[str, Any], path: Path) -> dict[str, Any]:
    """Grava o resultado (JSON ou CSV) e devolve linhas, colunas e hash."""
    columns: list[str] = dump["columns"]
    # `default=str` cobre RAW/Decimal/date; sem a normalização única o hash
    # (json.dumps estrito em `compute_hash`) quebraria numa coluna `bytes`.
    rows = json.loads(json.dumps(serialize_rows(columns, dump["data"]), default=str))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    else:
        payload = {"columns": columns, "types": dump["types"], "rows": rows}
        path.write_text(
            json.dumps(payload, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    return {
        "path": str(path),
        "rows": len(rows),
        "columns": len(columns),
        "result_hash": compute_hash(rows),
    }


def explain_plan(creds: Any, sql: str, binds: dict[str, Any]) -> list[str]:
    """Plano estimado (EXPLAIN PLAN + DBMS_XPLAN.DISPLAY): hipótese, não métrica."""
    try:
        connection = oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        )
    except oracledb.Error as exc:
        return [f"plano indisponível: {_error_summary(exc)}"]
    try:
        cursor = connection.cursor()
        cursor.execute("EXPLAIN PLAN FOR " + sql, binds)
        cursor.execute("SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())")
        return [str(row[0]) for row in cursor.fetchall()]
    except oracledb.Error as exc:
        # Usuário de leitura pode não ter PLAN_TABLE; não derruba a medição pronta.
        return [f"plano indisponível: {_error_summary(exc)}"]
    finally:
        connection.close()


def _load_sql(path: Path) -> str:
    return str(_single_statement(path.read_bytes().decode("utf-8")))


def _check_runs(value: str) -> int:
    runs = int(value)
    if runs < MIN_RUNS or runs % 2 == 0:
        raise argparse.ArgumentTypeError(
            f"--runs deve ser ímpar e >= {MIN_RUNS} (mediana): {value}"
        )
    return runs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Arquivo .sql (uma consulta)")
    parser.add_argument("--runs", type=_check_runs, default=DEFAULT_RUNS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--arraysize", type=int, default=DEFAULT_ARRAYSIZE)
    parser.add_argument("--bind", action="append", default=[], help="NOME=VALOR")
    parser.add_argument("--dump", type=Path, help="Grava o resultado (.json ou .csv)")
    parser.add_argument("--explain", action="store_true", help="Plano estimado")
    parser.add_argument("--out", type=Path, help="Relatório JSON da medição")
    parser.add_argument(
        "--baseline", type=Path, help="Relatório anterior para decidir MELHORA/NEUTRO"
    )
    parser.add_argument("--min-gain", type=float, default=DEFAULT_MIN_GAIN_PCT)
    return parser


def _prepare(args: argparse.Namespace) -> tuple[str, dict[str, Any], Any]:
    """Guard, SQL normalizado, binds e credenciais; SystemExit se algo bloquear."""
    load_dotenv(ROOT / ".env")
    path = args.file.resolve()
    guard_code, guard_output = _guard(path, resolve_guard())
    if guard_code != 0:
        raise SystemExit(f"guard_sql.py bloqueou (exit {guard_code}): {guard_output}")
    try:
        sql = _load_sql(path)
    except (UnicodeDecodeError, GuardError) as exc:
        raise SystemExit(f"SQL ilegível: {_error_summary(exc)}") from exc
    binds = _default_binds(sql)
    explicit = _parse_bind_args(args.bind)
    binds.update({k: v for k, v in explicit.items() if k in binds})
    creds = resolve_oracle_credentials(lambda *_a, **_k: None, "medir-sql")
    if creds is None:
        raise SystemExit("Credenciais Oracle indisponíveis")
    init_thick_mode(creds, lambda *_a, **_k: None, "medir-sql")
    oracledb.defaults.fetch_lobs = False
    return sql, binds, creds


def _report(
    args: argparse.Namespace, sql: str, result: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema": "oracle-measure/v1",
        "measure_version": MEASURE_VERSION,
        "file": str(args.file),
        "bind_names": _bind_names(sql),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "arraysize": args.arraysize,
        "timeout_seconds": args.timeout,
        **{key: value for key, value in result.items() if key != "dump"},
    }


def main() -> int:
    args = _build_parser().parse_args()
    sql, binds, creds = _prepare(args)
    options = MeasureOptions(
        runs=args.runs,
        timeout=args.timeout,
        arraysize=args.arraysize,
        keep_first_rows=args.dump is not None,
    )
    result = measure(creds, sql, binds, options)
    report = _report(args, sql, result)
    if args.dump is not None and result["dump"] is not None:
        report["dump"] = write_dump(result["dump"], args.dump)
    if args.explain:
        report["plan"] = explain_plan(creds, sql, binds)
    if args.baseline is not None and result["summary"] is not None:
        base = json.loads(args.baseline.read_text(encoding="utf-8"))
        if not base.get("summary"):
            raise SystemExit("baseline sem execuções válidas (summary ausente)")
        report["decision"] = decide(base["summary"], result["summary"], args.min_gain)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["sufficient"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

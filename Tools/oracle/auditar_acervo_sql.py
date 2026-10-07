"""Varre o acervo SQL medindo cada consulta ativa e sinalizando o que pede atenção.

Roda `medir_sql_oracle.py` em cada `.sql` das pastas de consulta (as mesmas que o
`validar_sql_oracle.py` executa: sem `11_views_referencia_sgt` e
`12_manutencao_dml_restrito`) e classifica o resultado:

- FALHA: nenhuma execução válida (erro de SQL, guard, rede que não recuperou);
- INSTAVEL: menos de 3 execuções válidas (mediana pouco confiável);
- LENTA: mediana do fetch completo acima de 3 s (a rede derruba a sessão em ~4 a 6 s);
- VAZIA: 0 linhas — pode ser sentinela saudável ou filtro quebrado, e só a leitura da
  regra de negócio decide; não conta como aprovação;
- TETO_ATINGIDO: devolveu exatamente o teto `FETCH FIRST N ROWS ONLY`/`ROWNUM <= N`
  declarado no SQL, ou seja, o resultado pode estar truncado;
- LINHAS_INSTAVEIS: a contagem de linhas mudou entre as execuções da mesma medição.

Somente leitura (o medidor passa cada consulta pelo `guard_sql.py`). O JSON de saída é
evidência de uma rodada; não altera o catálogo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medir_sql_oracle import MAX_ATTEMPTS, _check_runs  # noqa: E402
from oracle_catalog import GuardError, sql_guard_text  # noqa: E402
from validar_sql_oracle import CONSULTAS_ROOT, _files  # noqa: E402

MEDIR = Path(__file__).resolve().parent / "medir_sql_oracle.py"
AUDIT_VERSION = "1.0.0"
SLOW_MS = 3000.0
# Folga por tentativa além do `timeout`: watchdog do medidor (+5 s) e conexão.
ATTEMPT_MARGIN_S = 25
MIN_VALID_RUNS = 3
CAP_RE = re.compile(r"FETCH\s+FIRST\s+(\d+)\s+ROWS?\s+ONLY|ROWNUM\s*<=\s*(\d+)", re.I)


def detect_row_cap(sql: str) -> int | None:
    """Teto de linhas declarado no SQL (`FETCH FIRST N ROWS ONLY` ou `ROWNUM <= N`).

    Ignora comentários e literais de texto; com vários candidatos vale o último (o do
    SELECT externo).
    Melhor esforço: `ROWNUM` dentro de subconsulta pode gerar um teto falso, por isso a
    marca TETO_ATINGIDO só sai quando o resultado tem pelo menos esse número de linhas.
    """
    try:
        text = str(sql_guard_text(sql))
    except GuardError:
        text = sql
    matches = list(CAP_RE.finditer(text))
    if not matches:
        return None
    last = matches[-1]
    return int(last.group(1) or last.group(2))


def classify(report: dict[str, Any] | None, cap: int | None) -> list[str]:
    """Marcas de atenção de um relatório do medidor (`None` = sem relatório)."""
    if report is None or not report.get("valid_runs"):
        return ["FALHA"]
    flags: list[str] = []
    if not report.get("sufficient"):
        flags.append("INSTAVEL")
    summary = report.get("summary") or {}
    if float(summary.get("median_ms", 0)) > SLOW_MS:
        flags.append("LENTA")
    rows = first_rows(report)
    if rows == 0:
        flags.append("VAZIA")
    if cap is not None and rows is not None and rows >= cap:
        flags.append("TETO_ATINGIDO")
    if not report.get("row_count_stable", True):
        flags.append("LINHAS_INSTAVEIS")
    return flags


def first_rows(report: dict[str, Any]) -> int | None:
    """Linhas da primeira execução válida, ou None se não houve nenhuma."""
    for run in report.get("runs", []):
        if run.get("status") == "ok":
            return int(run.get("rows", 0))
    return None


def _error_of(report: dict[str, Any] | None, stderr: str) -> str:
    if report is not None:
        for run in report.get("runs", []):
            if run.get("status") != "ok":
                return str(run.get("error") or run.get("status"))[:300]
        return ""
    return stderr.strip()[-300:]


def _measurer_deadline(runs: int, timeout: int) -> int:
    """Pior caso do medidor: `runs` execuções × `MAX_ATTEMPTS` tentativas cada."""
    return int(runs * MAX_ATTEMPTS * (timeout + ATTEMPT_MARGIN_S) + 60)


def audit_file(path: Path, runs: int, timeout: int) -> dict[str, Any]:
    """Mede um arquivo com o `medir_sql_oracle.py` e devolve o registro da rodada.

    Estouro do prazo do medidor vira FALHA deste arquivo; a varredura segue.
    """
    sql = path.read_text(encoding="utf-8")
    cap = detect_row_cap(sql)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "relatorio.json"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MEDIR),
                    str(path),
                    "--runs",
                    str(runs),
                    "--timeout",
                    str(timeout),
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=False,
                timeout=_measurer_deadline(runs, timeout),
            )
        except subprocess.TimeoutExpired:
            return {
                "file": path.relative_to(ROOT).as_posix(),
                "flags": ["FALHA"],
                "median_ms": None,
                "noise_ms": None,
                "rows": None,
                "row_cap": cap,
                "valid_runs": 0,
                "error": "timeout do medidor",
            }
        report = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None
    summary = (report or {}).get("summary") or {}
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "flags": classify(report, cap),
        "median_ms": summary.get("median_ms"),
        "noise_ms": summary.get("noise_ms"),
        "rows": first_rows(report) if report else None,
        "row_cap": cap,
        "valid_runs": (report or {}).get("valid_runs", 0),
        "error": _error_of(report, completed.stderr or completed.stdout),
    }


def summarize_flags(records: list[dict[str, Any]]) -> dict[str, int]:
    """Quantos arquivos têm cada marca; `OK` = sem nenhuma marca."""
    counter: Counter[str] = Counter()
    for record in records:
        flags = record["flags"] or ["OK"]
        counter.update(flags)
    return dict(sorted(counter.items()))


def _select(root: Path, part: int, parts: int, only: str | None) -> list[Path]:
    paths: list[Path] = list(_files(root, part, parts))
    if only:
        paths = [path for path in paths if only in path.as_posix()]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=CONSULTAS_ROOT)
    parser.add_argument("--runs", type=_check_runs, default=MIN_VALID_RUNS)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--part", type=int, default=1)
    parser.add_argument("--parts", type=int, default=1)
    parser.add_argument("--only", help="Só arquivos cujo caminho contém este texto")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = _select(args.root.resolve(), args.part, args.parts, args.only)
    records = [audit_file(path, args.runs, args.timeout) for path in paths]
    payload = {
        "schema": "oracle-audit/v1",
        "audit_version": AUDIT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "runs": args.runs,
        "slow_ms": SLOW_MS,
        "summary": summarize_flags(records),
        "results": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"files": len(records), "summary": payload["summary"]}))
    return 1 if any("FALHA" in record["flags"] for record in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Valida o acervo SQL contra o Oracle em modo somente leitura.

O verificador foi criado para a revisão do acervo de Beneficimento. Ele não
executa DDL/DML, não imprime credenciais e separa parse Oracle de smoke de
execução. O smoke executa o SQL original e lê só a primeira linha; isso
confirma resolução de nomes, tipos e o início do plano sem materializar um
relatório inteiro. Consultas que usam função de pacote continuam bloqueadas
pela guarda SQL até que sejam substituídas por expressões nativas.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "Produção Beneficimento" / "src"))

from beneficiamento.oracle import SESSION_DROP_MARKERS  # noqa: E402
from guard_sql import canonical_guard_file  # noqa: E402
from oracle_catalog import (  # noqa: E402
    GuardError,
    sql_guard_text,
    strip_sql_comments,
)
from oracle_extract import (  # noqa: E402
    init_thick_mode,
    resolve_oracle_credentials,
)

# Fonte única do caminho do acervo de consultas: as demais ferramentas importam daqui.
CONSULTAS_ROOT = ROOT / "docs" / "oracle-schema" / "consultas"
DEFAULT_TIMEOUT = 20
VALIDATOR_VERSION = "2.1.0"
# Status que contam como aprovação. Qualquer outro (timeout, guard, erro de
# smoke, encoding...) reprova a rodada: exit 0 só com evidência positiva.
PASSING_STATUSES = frozenset({"validated", "parse_ok"})
# Queda de sessão pela rede (ORA-00028/DPY-4011...): repetir com conexão nova.
MAX_ATTEMPTS = 3


def portable_command(argv: list[str]) -> list[str]:
    """Linha de comando da rodada sem caminho absoluto da máquina: o executável
    vira só o nome e argumentos dentro de `ROOT` ficam relativos a ele."""
    portable = [Path(sys.executable).name]
    for arg in argv:
        candidate = Path(arg)
        if candidate.is_absolute():
            try:
                arg = candidate.relative_to(ROOT).as_posix()
            except ValueError:
                arg = candidate.name
        portable.append(arg)
    return portable


def resolve_guard() -> Path:
    """Localiza o guard SQL usado pelos validadores.

    `ORACLE_SQL_GUARD` tem precedência. Sem ela, o padrão é o wrapper versionado
    `Tools/oracle/guard_sql.py`, que delega ao guard canônico da skill oracle-sql (fora
    do repositório). Guard ausente — o wrapper ou o canônico — é erro de
    ferramenta (`SystemExit`), não "consulta bloqueada": sem essa distinção o
    subprocess saía com código de erro e todo arquivo virava `blocked_guard`.
    """
    configured = os.environ.get("ORACLE_SQL_GUARD")
    guard = (
        Path(configured) if configured else ROOT / "Tools" / "oracle" / "guard_sql.py"
    )
    if not guard.is_file():
        raise SystemExit(
            f"guard_sql.py não encontrado em {guard}. Corrija ORACLE_SQL_GUARD "
            "ou restaure Tools/oracle/guard_sql.py."
        )
    if not configured:
        canonical = canonical_guard_file()
        if not canonical.is_file():
            raise SystemExit(
                f"guard_sql canônico não encontrado em {canonical}. Instale a "
                "skill oracle-sql ou aponte ORACLE_SQL_GUARD para outro guard."
            )
    return guard


@dataclass(frozen=True)
class RunOptions:
    """Parâmetros da rodada, iguais para todos os arquivos."""

    timeout: int
    execute: bool
    explicit_binds: dict[str, Any]
    guard: Path


def _log(*_args: Any, **_kwargs: Any) -> None:
    """Logger silencioso: nunca expõe DSN, usuário ou dados retornados."""


def _strip_comments(sql: str) -> str:
    """Remove comentarios respeitando literais e preserva hints `/*+ ... */`.

    Hints fazem parte do texto executavel: remove-los pode alterar o plano.
    Usa o scanner de `oracle_catalog` (literais '...', q'[...]', "..."), de modo
    que `NVL(A,'--')` nao seja truncado. Levanta `GuardError` se houver
    comentario ou literal sem fechamento.
    """
    stripped: str = strip_sql_comments(sql)
    return stripped


def _single_statement(sql: str) -> str:
    stripped = _strip_comments(sql).strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()
    return stripped


def _statement_terminators(sql: str) -> tuple[int, bool]:
    """Devolve (quantidade de ';' fora de literais, se o ultimo e terminal).

    Literais como `LISTAGG(..., '; ')` ou `q'[a;b]'` nao contam como
    separadores de instrucao.
    """
    guard: str = sql_guard_text(sql).rstrip()
    return guard.count(";"), guard.endswith(";")


def _error_summary(exc: BaseException) -> str:
    message = re.sub(r"\s+", " ", str(exc)).strip()
    return f"{type(exc).__name__}: {message[:500]}"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def content_sha256(value: bytes) -> str:
    """SHA-256 do conteúdo lógico do SQL, independente de CRLF/LF.

    O `.gitattributes` força `eol=lf` nos `.sql`; hashear os bytes do disco
    (CRLF no Windows com autocrlf) invalidaria a evidência a cada checkout.
    Fonte única: o gerador do catálogo importa esta função.
    """
    return _sha256(value.replace(b"\r\n", b"\n"))


def _bind_names(sql: str) -> list[str]:
    without_literals: str = sql_guard_text(sql)
    return sorted(
        {
            match.group(1).upper()
            for match in re.finditer(
                r"(?<!:):([A-Za-z][A-Za-z0-9_$#]*)\b", without_literals
            )
        }
    )


def _default_binds(sql: str) -> dict[str, Any]:
    now = datetime.now(UTC).replace(tzinfo=None)
    values: dict[str, Any] = {}
    for name in _bind_names(sql):
        upper = name.upper()
        if upper in {"DT_INICIO", "DATA_INICIO", "DATA_INICIAL"}:
            values[name] = now - timedelta(days=30)
        elif upper in {"DT_FIM", "DATA_FIM", "DATA_FINAL"}:
            values[name] = now
        elif upper in {"NF_ENTRADA", "NUMERO_NOTA", "NOTA", "FILIAL", "IDPESSOAFJ"}:
            values[name] = 1 if upper in {"FILIAL", "IDPESSOAFJ"} else 35919
        else:
            values[name] = 1
    return values


def _parse_iso_date(value: str) -> Any:
    """`YYYY-MM-DD[ HH:MM:SS]` vira `datetime`; senão o texto original.

    Texto em bind de data dependeria do NLS_DATE_FORMAT da sessão (ORA-01861).
    """
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?", value.strip()):
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return value
    return value


def _parse_bind_args(values: list[str] | None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError(f"Bind inválido, esperado NOME=VALOR: {item}")
        name, value = item.split("=", 1)
        name = name.strip().upper()
        if not name:
            raise ValueError(f"Bind inválido, nome vazio: {item}")
        try:
            parsed[name] = int(value)
        except ValueError:
            try:
                parsed[name] = float(value)
            except ValueError:
                parsed[name] = _parse_iso_date(value)
    return parsed


def _guard(path: Path, guard: Path) -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, str(guard), "--arquivo", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode, output[-1000:]


def _files(root: Path, part: int, parts: int) -> list[Path]:
    candidates = sorted(root.rglob("*.sql"))
    candidates = [
        path
        for path in candidates
        if "11_views_referencia_sgt" not in path.parts
        and "12_manutencao_dml_restrito" not in path.parts
    ]
    if parts < 1 or not 1 <= part <= parts:
        raise ValueError("part deve estar entre 1 e parts")
    size = (len(candidates) + parts - 1) // parts
    return candidates[(part - 1) * size : part * size]


def _connect(creds: Any) -> Any:
    return oracledb.connect(
        user=creds.user,
        password=creds.password,
        dsn=creds.dsn,
    )


def _run_with_watchdog(
    connection: Any, sql: str, timeout: int, binds: dict[str, Any]
) -> dict[str, Any]:
    """Parseia e executa o smoke; cancela a sessão se exceder o prazo."""

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def target() -> None:
        try:
            cursor = connection.cursor()
            started = time.perf_counter()
            cursor.parse(sql)
            parse_ms = round((time.perf_counter() - started) * 1000, 1)
            result.update({"parse": "pass", "parse_ms": parse_ms})

            # Executa o SQL original (embrulhar em SELECT * FROM (...) dava
            # ORA-00918 com colunas duplicadas e quebrava WITH FUNCTION) e
            # busca so a primeira linha.
            cursor.prefetchrows = 1
            cursor.arraysize = 1
            started = time.perf_counter()
            try:
                cursor.execute(sql, binds)
                description = cursor.description or []
                rows = cursor.fetchmany(1)
            finally:
                cursor.close()
            execute_ms = round((time.perf_counter() - started) * 1000, 1)
            result.update(
                {
                    "smoke": "pass",
                    "execute_ms": execute_ms,
                    "rows": len(rows),
                    "columns": len(description),
                }
            )
        except (
            oracledb.Error,
            AttributeError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            error["value"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        with contextlib.suppress(oracledb.Error):  # cancelamento best effort
            connection.cancel()
        thread.join(5)
        # Thread ainda viva: o chamador não pode fechar a conexão debaixo dela.
        return {
            "parse": "unknown",
            "smoke": "timeout",
            "abandoned": thread.is_alive(),
        }
    if "value" in error:
        exc = error["value"]
        if result.get("parse") == "pass":
            result.update({"smoke": "error", "error": _error_summary(exc)})
            return result
        return {"parse": "fail", "smoke": "error", "error": _error_summary(exc)}
    return result


def _finish(result: dict[str, Any], started_clock: float) -> dict[str, Any]:
    result["finished_at_utc"] = datetime.now(UTC).isoformat()
    result["duration_ms"] = round((time.perf_counter() - started_clock) * 1000, 1)
    return result


def _oracle_stage(
    sql: str, guard_code: int, creds: Any, options: RunOptions
) -> dict[str, Any]:
    """Parse (e smoke, se pedido e permitido pelo guard) numa conexão nova."""
    connection = None
    abandoned = False
    try:
        connection = _connect(creds)
        if not options.execute or guard_code == 3:
            cursor = connection.cursor()
            started = time.perf_counter()
            cursor.parse(sql)
            blocked = guard_code == 3
            return {
                "parse": "pass",
                "parse_ms": round((time.perf_counter() - started) * 1000, 1),
                "smoke": "blocked_custom_function" if blocked else "not_requested",
                "status": "blocked_custom_function" if blocked else "parse_ok",
            }
        binds = _default_binds(sql)
        # `--bind` vale para a rodada inteira; só entra no arquivo que tem o
        # placeholder — o driver rejeita bind sobrando (DPY-4008).
        binds.update({k: v for k, v in options.explicit_binds.items() if k in binds})
        outcome = _run_with_watchdog(connection, sql, options.timeout, binds)
        abandoned = bool(outcome.pop("abandoned", False))
        if outcome.get("smoke") == "pass":
            outcome["status"] = "validated"
        elif outcome.get("parse") == "pass":
            outcome["status"] = "parse_ok_smoke_" + str(outcome.get("smoke", "error"))
        else:
            outcome["status"] = str(outcome.get("smoke", "error"))
        return outcome
    except (oracledb.Error, OSError, RuntimeError, ValueError) as exc:
        return {"status": "oracle_error", "error": _error_summary(exc)}
    finally:
        if connection is not None and not abandoned:
            with contextlib.suppress(oracledb.Error):  # limpeza best effort
                connection.close()


def _oracle_stage_with_retry(
    sql: str, guard_code: int, creds: Any, options: RunOptions
) -> dict[str, Any]:
    """`_oracle_stage` repetido com conexão nova em queda de sessão pela rede."""
    outcome: dict[str, Any] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        outcome = _oracle_stage(sql, guard_code, creds, options)
        outcome["attempts"] = attempt
        error = str(outcome.get("error", ""))
        # A queda pode vir no parse (`error`), no smoke (`parse_ok_smoke_error`)
        # ou na conexão (`oracle_error`): decide pela mensagem, não pelo status.
        if not any(marker in error for marker in SESSION_DROP_MARKERS):
            break
    return outcome


def _validate_one(path: Path, creds: Any, options: RunOptions) -> dict[str, Any]:
    started_clock = time.perf_counter()
    raw_bytes = path.read_bytes()
    raw_hash = content_sha256(raw_bytes)
    result: dict[str, Any] = {
        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(raw_bytes),
        "raw_sha256": raw_hash,
        "guard_input_sha256": raw_hash,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "validator_version": VALIDATOR_VERSION,
    }
    try:
        sql = _single_statement(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        result.update({"status": "encoding_error", "error": _error_summary(exc)})
        return _finish(result, started_clock)
    except GuardError as exc:
        result.update({"status": "sql_scan_error", "error": _error_summary(exc)})
        return _finish(result, started_clock)

    normalized_hash = _sha256(sql.encode("utf-8"))
    guard_code, guard_output = _guard(path, options.guard)
    result.update(
        {
            "normalized_sha256": normalized_hash,
            "parse_input_sha256": normalized_hash,
            "bind_names": _bind_names(sql),
            "guard_exit": guard_code,
            "guard_output": guard_output,
        }
    )
    # 0 = liberado; 3 = so parse (funcao customizada); qualquer outro codigo
    # diferente de zero e bloqueio (fail-closed).
    if guard_code not in (0, 3):
        result["status"] = "blocked_guard"
        return _finish(result, started_clock)

    count, trailing = _statement_terminators(sql)
    if count > 1 or (count and not trailing):
        result["status"] = "blocked_multiple_statements"
        return _finish(result, started_clock)

    result.update(_oracle_stage_with_retry(sql, guard_code, creds, options))
    return _finish(result, started_clock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=CONSULTAS_ROOT)
    parser.add_argument(
        "--file",
        type=Path,
        help="Valida somente um arquivo SQL dentro de --root",
    )
    parser.add_argument("--part", type=int, default=1)
    parser.add_argument("--parts", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument(
        "--bind",
        action="append",
        default=[],
        help="Bind explícito no formato NOME=VALOR; pode ser repetido",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # argparse preserva a forma relativa informada pelo operador; normalize-a
    # antes de comparar os caminhos com ROOT e de calcular a evidência JSON.
    args.root = args.root.resolve()
    explicit_binds = _parse_bind_args(args.bind)
    # O .env precisa estar carregado antes de resolve_guard (ORACLE_SQL_GUARD).
    load_dotenv(ROOT / ".env")
    options = RunOptions(
        timeout=args.timeout,
        execute=not args.parse_only,
        explicit_binds=explicit_binds,
        guard=resolve_guard(),
    )

    creds = resolve_oracle_credentials(_log, "validar-acervo-sql")
    if creds is None:
        print(json.dumps({"status": "credentials_unavailable"}, ensure_ascii=False))
        return 2
    init_thick_mode(creds, _log, "validar-acervo-sql")

    if args.file is not None:
        path = args.file.resolve()
        try:
            path.relative_to(args.root)
        except ValueError as exc:
            raise SystemExit("--file deve estar dentro de --root") from exc
        paths = [path]
    else:
        paths = _files(args.root, args.part, args.parts)
    results = [_validate_one(path, creds, options) for path in paths]
    summary: dict[str, int] = {}
    for item in results:
        status = str(item.get("status", "unknown"))
        summary[status] = summary.get(status, 0) + 1
    payload = {
        "schema": "oracle-sql-validation/v2",
        "validator_version": VALIDATOR_VERSION,
        "root": str(args.root.relative_to(ROOT)).replace("\\", "/"),
        "part": args.part,
        "parts": args.parts,
        "file": (
            str(args.file.resolve().relative_to(ROOT)).replace("\\", "/")
            if args.file is not None
            else None
        ),
        "timeout_seconds": args.timeout,
        "parse_only": args.parse_only,
        "bind_names": sorted(explicit_binds),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "command": portable_command(sys.argv),
        "summary": summary,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "complete", "summary": summary}, ensure_ascii=False))
    return 0 if results and set(summary) <= PASSING_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())

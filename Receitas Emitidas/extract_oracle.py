# pylint: disable=line-too-long, too-many-locals, broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "2.8.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "ipc-stdio, thick-mode-padronizado",
#   "description": "Extrai receitas emitidas via Direct Oracle (Query CTE Nativa) com Thick Mode garantido",
#   "reliability": "Base64-Bridge-Logs, SQL-Correlation-DNA, Retry-On-Failure, Circuit-Breaker"
# }
import json
import os
import sys
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
import oracledb
from automation_log import make_logger
from oracle_extract import (
    OracleCredentials,
    compute_hash,
    fetch_all,
    init_thick_mode,
    read_last_hash,
    resolve_oracle_credentials,
    serialize_rows,
    write_state_tmp,
)
from oracle_retry import CircuitBreakerError, make_oracle_retry

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

log = make_logger("PY-EXTRACT")

# --- RESILIENCIA DE CONEXAO ---
_oracle_retry = make_oracle_retry()


@_oracle_retry
def _fetch(
    creds: OracleCredentials, sql: str, exec_id: str
) -> tuple[list[str], list[Any]]:
    try:
        return fetch_all(creds, sql, exec_id, log)
    except oracledb.Error as e:
        if e.args:
            error_obj = e.args[0]
            log(
                f"Erro SQL Oracle (ORA-{error_obj.code}): {error_obj.message}",
                "ERROR",
                exec_id,
            )
        else:
            log(f"Erro SQL Oracle desconhecido: {e}", "ERROR", exec_id)
        log(f"DNA da Query: {sql[:200]}...", "DEBUG", exec_id)
        raise


def _receitas_sort_key(record: dict[str, Any]) -> Any:
    return (
        str(record.get("NUMERO_OB", "")),
        str(record.get("REDUZIDO", "")),
        str(record.get("GRUPO", "")),
        str(record.get("INICIO_TING", "")),
    )


def extract() -> None:
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    creds = resolve_oracle_credentials(log, exec_id)
    if creds is None:
        sys.exit(1)

    init_thick_mode(creds, log, exec_id)

    sql_file = os.path.join(os.path.dirname(__file__), "SQL-ReceitasEmitidas.sql")
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    sql = sql.replace(
        "/*+ FIRST_ROWS(1000) */", f"/*+ FIRST_ROWS(1000) ExecId:{exec_id} */"
    )

    try:
        columns, rows = _fetch(creds, sql, exec_id)
        data = serialize_rows(columns, rows, sort_key=_receitas_sort_key)

        current_hash = compute_hash(data)
        log(
            f"Hash calculado para {len(data)} registros: {current_hash}",
            "DEBUG",
            exec_id,
        )

        state_path = os.path.join(os.path.dirname(__file__), "receitas_state.json")
        last_hash = read_last_hash(state_path)
        state_tmp_path = state_path + ".tmp"

        if last_hash and current_hash == last_hash:
            if os.path.exists(state_tmp_path):
                log(
                    "Sem novas alterações, mas detectado estado temporário pendente de notificação.",
                    "INFO",
                    exec_id,
                )
            else:
                log(
                    "Sem alterações relevantes detectadas (Idempotência).",
                    "INFO",
                    exec_id,
                )
                sys.exit(2)

        write_state_tmp(state_path, current_hash)

        json_payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        sys.stdout.write(json_payload)
        sys.stdout.flush()
        log(f"Extração concluída: {len(data)} registros.", "INFO", exec_id)

    except CircuitBreakerError:
        log(
            "Circuit Breaker Aberto: Falhas persistentes no banco de dados.",
            "ERROR",
            exec_id,
        )
        sys.exit(1)
    except Exception as e:
        log(f"Erro fatal na extracao: {e}", "ERROR", exec_id)
        sys.exit(1)


if __name__ == "__main__":
    extract()

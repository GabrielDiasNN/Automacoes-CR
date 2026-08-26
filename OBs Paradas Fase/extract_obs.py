# pylint: disable=line-too-long, broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "1.2.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "exit-0=dados-novos, exit-2=idempotente, exit-1=erro",
#   "description": "Extrai OBs paradas na fase via Oracle (PKGBENF0001), grava obs_result.json"
# }
import json
import os
import sys
from datetime import datetime
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
from automation_log import ensure_utf8_streams, make_logger
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

ensure_utf8_streams()

log = make_logger("OBP-EXTRACT")
_oracle_retry = make_oracle_retry()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "obs_result.json")
STATE_FILE = os.path.join(SCRIPT_DIR, "obs_state.json")


@_oracle_retry
def _fetch(
    creds: OracleCredentials, sql: str, exec_id: str
) -> tuple[list[str], list[Any]]:
    return fetch_all(creds, sql, exec_id, log, batch_size=1000)


def _obs_sort_key(record: dict[str, Any]) -> Any:
    return (record.get("NUMERO_OB") or "", record.get("FASE_ATUAL") or "")


def extract() -> None:
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    creds = resolve_oracle_credentials(log, exec_id)
    if creds is None:
        sys.exit(1)

    init_thick_mode(creds, log, exec_id)

    sql_file = os.path.join(SCRIPT_DIR, "SQL-ObsParadasFase.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL nao encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)
    with open(sql_file, encoding="utf-8") as f:
        sql = f.read()

    try:
        columns, rows = _fetch(creds, sql, exec_id)
        data = serialize_rows(columns, rows, sort_key=_obs_sort_key)
        current_hash = compute_hash({"rows": data})

        if read_last_hash(STATE_FILE) == current_hash:
            log("Sem alteracoes (idempotencia).", "INFO", exec_id)
            sys.exit(2)

        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "rows": data,
                    "total": len(data),
                    "extracted_at": datetime.now().isoformat(),
                    "hash": current_hash,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        write_state_tmp(STATE_FILE, current_hash)

        log(f"Extracao concluida: {len(data)} OBs.", "INFO", exec_id)
        sys.exit(0)

    except CircuitBreakerError:
        log("Circuit Breaker aberto: falhas persistentes no Oracle.", "ERROR", exec_id)
        sys.exit(1)
    except Exception as e:
        log(f"Erro fatal na extracao: {e}", "ERROR", exec_id)
        sys.exit(1)


if __name__ == "__main__":
    extract()

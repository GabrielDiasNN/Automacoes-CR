# pylint: disable=line-too-long, broad-exception-caught, bare-except, import-error, wrong-import-position
# {
#   "version": "1.1.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "exit-0=dados-novos, exit-2=idempotente, exit-1=erro",
#   "description": "Extrai OBs paradas na fase via Oracle (PKGBENF0001), grava obs_result.json"
# }
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python"))
from automation_log import make_logger
from oracle_retry import make_oracle_retry, CircuitBreakerError
from oracle_client import init_oracle_thick_mode

import oracledb

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

log = make_logger("OBP-EXTRACT")
_oracle_retry = make_oracle_retry()

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "obs_result.json")
STATE_FILE  = os.path.join(SCRIPT_DIR, "obs_state.json")


@_oracle_retry
def connect_and_execute(user: str, password: str, dsn: str, sql: str, exec_id: str) -> tuple[list[str], list[Any]]:
    log(f"Conectando ao Oracle ({dsn})...", "INFO", exec_id)
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows: list[Any] = []
        while True:
            batch = cursor.fetchmany(1000)
            if not batch:
                break
            rows.extend(batch)
        log(f"Query OK — {len(rows)} linhas retornadas.", "INFO", exec_id)
        return columns, rows


def _serialize_rows(columns: list[str], rows: list[Any]) -> tuple[list[dict[str, Any]], str]:
    """Converte linhas Oracle em dicts e retorna (data, sha256_hex)."""
    data: list[dict[str, Any]] = []
    for row in rows:
        record: dict[str, Any] = dict(zip(columns, row))
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()
            elif isinstance(value, str) and value:
                record[key] = value.strip()
        data.append(record)
    data.sort(key=lambda x: (str(x.get("NUMERO_OB", "")), str(x.get("FASE_ATUAL", ""))))
    payload_str = json.dumps({"rows": data}, ensure_ascii=False, sort_keys=True)
    return data, hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def _last_hash() -> str:
    if not os.path.exists(STATE_FILE):
        return ""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return str(json.load(f).get("last_hash", ""))
    except Exception:
        return ""


def extract() -> None:
    exec_id    = sys.argv[1] if len(sys.argv) > 1 else "manual"
    user       = os.environ.get("ORACLE_READONLY_USER")
    password   = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn        = os.environ.get("ORACLE_CONNECT_STRING", "dbprd")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get("ORACLE_CLIENT_PATH")
    tns_admin  = os.environ.get("TNS_ADMIN")

    if not all([user, password, dsn]):
        log("Credenciais Oracle ausentes.", "ERROR", exec_id)
        sys.exit(1)
    if not client_lib or not os.path.exists(client_lib):
        log("ORACLE_CLIENT_LIB_DIR invalido.", "ERROR", exec_id)
        sys.exit(1)

    assert user is not None and password is not None
    init_oracle_thick_mode(client_lib, tns_admin, lambda msg, lvl="INFO": log(msg, lvl, exec_id))

    sql_file = os.path.join(SCRIPT_DIR, "SQL-ObsParadasFase.sql")
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    try:
        columns, rows = connect_and_execute(user, password, dsn, sql, exec_id)
        data, current_hash = _serialize_rows(columns, rows)

        if _last_hash() == current_hash:
            log("Sem alteracoes (idempotencia).", "INFO", exec_id)
            sys.exit(2)

        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"rows": data, "total": len(data),
                 "extracted_at": datetime.now().isoformat(), "hash": current_hash},
                f, ensure_ascii=False, indent=2,
            )

        state_tmp = STATE_FILE + ".tmp"
        with open(state_tmp, "w", encoding="utf-8") as f:
            json.dump({"last_hash": current_hash, "updated_at": datetime.now().isoformat()}, f)

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

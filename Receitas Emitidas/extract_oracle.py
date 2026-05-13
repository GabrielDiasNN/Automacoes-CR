# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, too-many-locals, f-string-without-interpolation, broad-exception-caught, bare-except, too-many-statements, unused-import
# {
#   "version": "2.7.1",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "ipc-stdio, thick-mode-padronizado",
#   "description": "Extrai receitas emitidas via Direct Oracle (Query CTE Nativa) com Thick Mode garantido",
#   "reliability": "Base64-Bridge-Logs, SQL-Correlation-DNA, Retry-On-Failure, Circuit-Breaker"
# }
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

import oracledb
import pybreaker
import stamina

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    raw_msg = f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}"
    sys.stderr.write(f"{raw_msg}\n")
    sys.stderr.flush()


# --- RESILIENCIA DE CONEXAO ---
db_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)


@db_breaker
@stamina.retry(on=oracledb.DatabaseError, attempts=3)
def connect_and_execute(
    user: str, password: str, dsn: str, sql: str, exec_id: str
) -> tuple[list[str], list[Any]]:
    log(
        f"Conectando ao Oracle (DSN: {dsn}) para extração Nativa (com Circuit Breaker)...",
        "INFO",
        exec_id,
    )
    try:
        with oracledb.connect(user=user, password=password, dsn=dsn) as connection:
            cursor = connection.cursor()
            log("Executando extração oficial otimizada...", "INFO", exec_id)
            try:
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                log(f"Query executada com sucesso. Linhas retornadas: {len(rows)}", "INFO", exec_id)
                return columns, rows
            except oracledb.Error as e:
                error_obj, = e.args
                log(f"Erro SQL Oracle (ORA-{error_obj.code}): {error_obj.message}", "ERROR", exec_id)
                # Log da query (parcial para seguranca)
                log(f"DNA da Query: {sql[:200]}...", "DEBUG", exec_id)
                raise
    except oracledb.Error as e:
        log(f"Erro de Conexao Oracle: {e}", "ERROR", exec_id)
        raise


def extract() -> None:
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING", "dbprd")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    tns_admin = os.environ.get("TNS_ADMIN")

    if not all([user, password, dsn]):
        log("Credenciais Oracle ausentes no ambiente.", "ERROR", exec_id)
        sys.exit(1)

    if not client_lib or not os.path.exists(client_lib):
        log(f"ORACLE_CLIENT_LIB_DIR invalido.", "ERROR", exec_id)
        sys.exit(1)

    try:
        oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
        log(f"Thick Mode ativado.", "INFO", exec_id)
    except Exception as e:
        log(f"Aviso Thick client: {e}", "WARN", exec_id)

    sql_file = os.path.join(os.path.dirname(__file__), "SQL-ReceitasEmitidas.sql")
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    sql = sql.replace(
        "/*+ FIRST_ROWS(1000) */", f"/*+ FIRST_ROWS(1000) ExecId:{exec_id} */"
    )

    try:
        columns, rows = connect_and_execute(user, password, dsn, sql, exec_id)

        data = []
        for row in rows:
            record = dict(zip(columns, row))
            for key, value in record.items():
                if isinstance(value, datetime):
                    record[key] = value.isoformat()
                elif isinstance(value, str) and value:
                    record[key] = value.strip()
            data.append(record)

        # Ordenacao deterministica multi-coluna para garantir estabilidade absoluta do hash
        data.sort(key=lambda x: (
            str(x.get("NUMERO_OB", "")),
            str(x.get("REDUZIDO", "")),
            str(x.get("GRUPO", "")),
            str(x.get("INICIO_TING", ""))
        ))

        json_payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        current_hash = hashlib.sha256(json_payload.encode("utf-8")).hexdigest()
        log(f"Hash calculado para {len(data)} registros: {current_hash}", "DEBUG", exec_id)

        state_path = os.path.join(os.path.dirname(__file__), "receitas_state.json")
        last_state_data = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    last_state_data = json.load(f)
            except:
                pass

        last_hash = last_state_data.get("last_hash")

        state_tmp_path = state_path + ".tmp"
        if last_hash and current_hash == last_hash:
            if os.path.exists(state_tmp_path):
                log("Sem novas alterações, mas detectado estado temporário pendente de notificação.", "INFO", exec_id)
            else:
                log("Sem alterações relevantes detectadas (Idempotência).", "INFO", exec_id)
                sys.exit(2)

        state_data = {
            "last_hash": current_hash,
            "updated_at": datetime.now().isoformat(),
        }
        # Salva apenas no temporario. O commit oficial ocorre no run.ps1 apos sucesso.
        with open(state_tmp_path, "w", encoding="utf-8") as f:
            json.dump(state_data, f, ensure_ascii=False, indent=4, sort_keys=True)

        sys.stdout.write(json_payload)
        sys.stdout.flush()
        log(f"Extração concluída: {len(data)} registros.", "INFO", exec_id)

    except pybreaker.CircuitBreakerError:
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



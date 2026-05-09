# -*- coding: utf-8 -*-
# {
#   "version": "2.7.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "ipc-stdio, thick-mode-padronizado",
#   "description": "Extrai receitas emitidas via Direct Oracle (Query CTE Nativa) com Thick Mode garantido",
#   "reliability": "Base64-Bridge-Logs, SQL-Correlation-DNA, Retry-On-Failure, Circuit-Breaker"
# }
import os
import sys
import json
import oracledb
from datetime import datetime
import base64
import hashlib
import stamina
import pybreaker
import time

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message, level="INFO", exec_id="manual"):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    raw_msg = f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

# --- RESILIENCIA DE CONEXAO ---
db_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)

@db_breaker
@stamina.retry(on=oracledb.DatabaseError, attempts=3)
def connect_and_execute(user, password, dsn, sql, exec_id):
    log("Conectando ao Oracle para extracao Nativa (com Circuit Breaker)...", "INFO", exec_id)
    with oracledb.connect(user=user, password=password, dsn=dsn) as connection:
        cursor = connection.cursor()
        log("Executando extracao oficial otimizada...", "INFO", exec_id)
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        return columns, rows

def extract():
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
        log(f"ORACLE_CLIENT_LIB_DIR invalido.", "ERROR", exec_id); sys.exit(1)

    try:
        oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
        log(f"Thick Mode ativado.", "INFO", exec_id)
    except Exception as e:
        log(f"Aviso Thick client: {e}", "WARN", exec_id)

    sql_file = os.path.join(os.path.dirname(__file__), "SQL-ReceitasEmitidas.sql")
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    sql = sql.replace("/*+ FIRST_ROWS(1000) */", f"/*+ FIRST_ROWS(1000) ExecId:{exec_id} */")

    try:
        columns, rows = connect_and_execute(user, password, dsn, sql, exec_id)
        
        data = []
        for row in rows:
            record = dict(zip(columns, row))
            for key, value in record.items():
                if isinstance(value, datetime): record[key] = value.isoformat()
                elif isinstance(value, str) and value: record[key] = value.strip()
            data.append(record)
            
        json_payload = json.dumps(data, ensure_ascii=False)
        current_hash = hashlib.sha256(json_payload.encode('utf-8')).hexdigest()
        
        state_path = os.path.join(os.path.dirname(__file__), "receitas_state.json")
        last_state_data = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f: last_state_data = json.load(f)
            except: pass
        
        last_hash = last_state_data.get("last_hash")
        
        if last_hash and current_hash == last_hash:
            log("Sem alteracoes relevantes detectadas (Idempotencia).", "INFO", exec_id)
            state_data = {"last_hash": current_hash, "updated_at": datetime.now().isoformat()}
            with open(state_path, "w", encoding="utf-8") as f: json.dump(state_data, f, ensure_ascii=False, indent=4)
            sys.exit(2)
            
        state_data = {"last_hash": current_hash, "updated_at": datetime.now().isoformat()}
        with open(state_path, "w", encoding="utf-8") as f: json.dump(state_data, f, ensure_ascii=False, indent=4)
            
        sys.stdout.write(json_payload)
        sys.stdout.flush()
        log(f"Extracao concluida: {len(data)} registros.", "INFO", exec_id)
        
    except pybreaker.CircuitBreakerError:
        log("Circuit Breaker Aberto: Falhas persistentes no banco de dados.", "ERROR", exec_id); sys.exit(1)
    except Exception as e:
        log(f"Erro fatal na extracao: {e}", "ERROR", exec_id); sys.exit(1)

if __name__ == "__main__":
    extract()

# -*- coding: utf-8 -*-
# {
#   "version": "2.6.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "ipc-stdio, thick-mode-padronizado",
#   "description": "Extrai receitas emitidas via Direct Oracle (Query CTE Nativa) com Thick Mode garantido",
#   "reliability": "Base64-Bridge-Logs, SQL-Correlation-DNA, Retry-On-Failure"
# }
import os
import sys
import json
import oracledb
from datetime import datetime
import base64
import hashlib

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message, level="INFO", exec_id="manual"):
    """Envia logs em Base64 para o stderr (Isolamento total)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    # Usando ASCII no prefixo para evitar problemas de encoding no terminal antes do decode
    raw_msg = f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def extract():
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING", "dbprd")
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    tns_admin = os.environ.get("TNS_ADMIN")

    # Validacao de pre-requisitos obrigatorios
    if not all([user, password, dsn]):
        log("Credenciais Oracle ausentes no ambiente (ORACLE_READONLY_USER, ORACLE_READONLY_PASSWORD, ORACLE_CONNECT_STRING).", "ERROR", exec_id)
        sys.exit(1)

    if not client_lib or not os.path.exists(client_lib):
        log(f"ORACLE_CLIENT_LIB_DIR invalido ou ausente: '{client_lib}'. Thick Mode impossivel. Abortando para evitar falha DPY-3015.", "ERROR", exec_id)
        sys.exit(1)

    if not tns_admin or not os.path.exists(tns_admin):
        log(f"TNS_ADMIN invalido ou ausente: '{tns_admin}'. Thick Mode impossivel sem tnsnames.ora. Abortando.", "ERROR", exec_id)
        sys.exit(1)

    # Garantir Thick Mode - falha explicita se nao conseguir (nao ha fallback para Thin Mode)
    try:
        oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
        log(f"Thick Mode ativado. client_lib='{client_lib}' tns_admin='{tns_admin}'", "INFO", exec_id)
    except Exception as e:
        log(f"ERRO CRITICO: Nao foi possivel ativar Thick Mode: {e}", "ERROR", exec_id)
        sys.exit(1)

    sql_file = os.path.join(os.path.dirname(__file__), "SQL-ReceitasEmitidas.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL nao encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)

    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    # Adiciona o ExecId para rastreabilidade no Oracle (Skill: SQL-Correlation-DNA)
    sql = sql.replace("/*+ FIRST_ROWS(1000) */", f"/*+ FIRST_ROWS(1000) ExecId:{exec_id} */")

    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        connection = None
        try:
            if retry_count > 0:
                log(f"Tentativa {retry_count + 1} de {max_retries}...", "WARN", exec_id)
            
            log("Conectando ao Oracle para extracao Nativa (Pure-Python)...", "INFO", exec_id)
            connection = oracledb.connect(user=user, password=password, dsn=dsn)
            cursor = connection.cursor()
            
            log("Executando extracao oficial otimizada...", "INFO", exec_id)
            cursor.execute(sql)
            
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            
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
                    with open(state_path, "r", encoding="utf-8") as f:
                        last_state_data = json.load(f)
                except:
                    pass
            
            last_hash = last_state_data.get("last_hash")
            
            if last_hash and current_hash == last_hash:
                log("Sem alteracoes relevantes detectadas no ciclo (Idempotencia).", "INFO", exec_id)
                # Atualiza apenas timestamp e mantem o hash
                state_data = {"last_hash": current_hash, "updated_at": datetime.now().isoformat()}
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(state_data, f, ensure_ascii=False, indent=4)
                sys.exit(2) # ExitCode 2 indica sucesso, mas sem necessidade de notificacao
                
            # Atualiza o state antes do output
            state_data = {"last_hash": current_hash, "updated_at": datetime.now().isoformat()}
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=4)
                
            # O Payload sai pelo Stdout limpo para o Orquestrador ler
            sys.stdout.write(json_payload)
            sys.stdout.flush()
            log(f"Extracao concluida: {len(data)} registros.", "INFO", exec_id)
            return # Sucesso total
            
        except Exception as e:
            retry_count += 1
            log(f"Erro na extracao (Tentativa {retry_count}/{max_retries}): {e}", "ERROR", exec_id)
            if retry_count >= max_retries:
                sys.exit(1)
            import time
            time.sleep(5)
        finally:
            if connection:
                try: connection.close()
                except: pass

if __name__ == "__main__":
    extract()


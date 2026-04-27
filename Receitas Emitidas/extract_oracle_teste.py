# -*- coding: utf-8 -*-
# {
#   "version": "1.0.0-TEST",
#   "skill": "python-oracle-migration",
#   "contract": "ipc-stdio",
#   "description": "Script de teste de conexao Oracle e fluxo JSON",
#   "reliability": "Base64-Bridge-Logs"
# }
import os
import sys
import json
import oracledb
from datetime import datetime
import base64

# Configuracao de encoding para garantir interoperabilidade no Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message, level="INFO", exec_id="TEST-CONN"):
    """Envia logs em Base64 para o stderr."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    raw_msg = f"[{ts}] [PY-TEST] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def normalize_record(record):
    """Normaliza tipos de dados para compatibilidade JSON."""
    new_record = {}
    for key, value in record.items():
        if isinstance(value, datetime):
            new_record[key] = value.isoformat()
        elif isinstance(value, str) and value:
            new_record[key] = value.strip()
        else:
            new_record[key] = value
    return new_record

def init_oracle(exec_id):
    """Configura o ambiente e modo de operacao do driver."""
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    tns_admin = os.environ.get("TNS_ADMIN")

    if tns_admin:
        os.environ["TNS_ADMIN"] = tns_admin
        log(f"TNS_ADMIN configurado: {tns_admin}", "INFO", exec_id)

    if client_lib and os.path.exists(client_lib):
        try:
            oracledb.init_oracle_client(lib_dir=client_lib)
            log(f"Modo Thick ativado via: {client_lib}", "INFO", exec_id)
        except Exception as e:
            log(f"Aviso ao iniciar modo Thick (tentando Thin): {e}", "WARN", exec_id)
    else:
        log("Iniciando em modo Thin (nativo Python)", "INFO", exec_id)

def extract_test():
    """Valida conexao e retorna JSON no stdout."""
    exec_id = "TEST-CONN"
    
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = os.environ.get("ORACLE_CONNECT_STRING")

    if not all([user, password, dsn]):
        log("Variaveis de ambiente ORACLE_READONLY_USER, PASSWORD ou CONNECT_STRING ausentes.", "ERROR", exec_id)
        sys.exit(1)

    init_oracle(exec_id)
    
    # Query minima para validacao de fumaa (Smoke Test)
    sql = "SELECT SYSDATE AS AGORA, 'CONEXAO_OK' AS STATUS FROM DUAL"
    
    connection = None
    try:
        log(f"Tentando conectar a: {dsn}", "INFO", exec_id)
        connection = oracledb.connect(user=user, password=password, dsn=dsn)
        cursor = connection.cursor()
        
        log("Executando query de teste...", "INFO", exec_id)
        cursor.execute(sql)
        
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        data = [normalize_record(dict(zip(columns, row))) for row in rows]
            
        # Saida JSON pura no stdout
        sys.stdout.write(json.dumps(data, ensure_ascii=False))
        sys.stdout.flush()
        
        log(f"Sucesso! Registros retornados: {len(data)}", "INFO", exec_id)
        
    except Exception as e:
        log(f"Erro na conexao ou query: {str(e)}", "ERROR", exec_id)
        sys.exit(1)
    finally:
        if connection:
            connection.close()
            log("Conexo encerrada.", "INFO", exec_id)

if __name__ == "__main__":
    extract_test()

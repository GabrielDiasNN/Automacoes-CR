# {
#   "version": "1.1.0",
#   "skill": "python-oracle-migration",
#   "contract": "direct-oracle-fetch",
#   "description": "Extrai dados diretamente do Oracle via oracledb (File-Payload)",
#   "reliability": "Base64-Bridge-Logs"
# }
import os
import sys
import json
import oracledb
import time
from datetime import datetime
import base64

# Forca UTF-8 para stdout e stderr para garantir interoperabilidade
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message, level="INFO", exec_id="manual"):
    """Envia logs em Base64 para o stderr para garantir integridade total."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    raw_msg = f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def extract():
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = "dbprd" 
    client_lib = r"C:\ORACLE\product\12.2.0\client_2"
    tns_admin = r"C:\ORACLE\product\12.2.0\client_1\network\admin"

    if not all([user, password]):
        log("Credenciais (ORACLE_*) ausentes no ambiente.", "ERROR", exec_id)
        sys.exit(1)

    os.environ["TNS_ADMIN"] = tns_admin
    
    if os.path.exists(client_lib):
        try:
            oracledb.init_oracle_client(lib_dir=client_lib)
            log("Modo Thick ativado", "INFO", exec_id)
        except Exception as e:
            log("Aviso ao iniciar modo Thick: " + str(e), "WARN", exec_id)

    sql_file = os.path.join(script_dir, "SQL-MontagemTerceirizados.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL não encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)
        
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql = f.read()

    connection = None
    try:
        log("Conectando ao Oracle via TNS Alias '" + dsn + "'...", "INFO", exec_id)
        connection = oracledb.connect(user=user, password=password, dsn=dsn)
        cursor = connection.cursor()
        cursor.arraysize = 100
        
        log("Executando extracao nativa...", "INFO", exec_id)
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        data = []
        for row in rows:
            record = dict(zip(columns, row))
            for key, value in record.items():
                if isinstance(value, str):
                    record[key] = value.strip()
                elif isinstance(value, datetime):
                    record[key] = value.isoformat()
            data.append(record)
            
        data_file = os.path.join(script_dir, f".data_{exec_id}.json")
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            
        log("Extracao nativa concluida: " + str(len(data)) + " registros.", "INFO", exec_id)
        
    except Exception as e:
        log("Erro fatal na extracao via TNS: " + str(e), "ERROR", exec_id)
        sys.exit(1)
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    extract()

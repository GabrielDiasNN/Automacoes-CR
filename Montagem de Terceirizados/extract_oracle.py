# {
#   "version": "1.2.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "direct-oracle-fetch, thick-mode-padronizado, retry-on-failure",
#   "description": "Extrai dados diretamente do Oracle via oracledb com Thick Mode garantido e Retry",
#   "reliability": "Base64-Bridge-Logs"
# }
import os
import sys
import json
import oracledb
import time
from datetime import datetime
import base64
from dotenv import load_dotenv

# Carregar ambiente (.env) do projeto raiz
# O arquivo .env esta 1 nivel acima da pasta da automacao
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

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
    
    # Portabilidade: Utilizar caminhos dinamicos ou de ambiente
    client_lib = os.environ.get("ORACLE_CLIENT_PATH")
    tns_admin = os.environ.get("TNS_ADMIN")

    if not all([user, password, client_lib, tns_admin]):
        log("Dependencias de ambiente (ORACLE_*, TNS_ADMIN) ausentes.", "ERROR", exec_id)
        sys.exit(1)

    os.environ["TNS_ADMIN"] = tns_admin
    
    if os.path.exists(client_lib):
        try:
            oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
            log("Modo Thick ativado", "INFO", exec_id)
        except Exception as e:
            log("Aviso ao iniciar modo Thick: " + str(e), "WARN", exec_id)

    sql_file = os.path.join(script_dir, "SQL-MontagemTerceirizados.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL nao encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)
        
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql = f.read()

    connection = None
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        connection = None
        try:
            if retry_count > 0:
                import time
                wait_sec = [30, 60, 120][min(retry_count - 1, 2)]
                log(f"Tentativa {retry_count + 1}/{max_retries} apos {wait_sec}s...", "WARN", exec_id)
                time.sleep(wait_sec)

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

            log(f"Extracao nativa concluida: {len(data)} registros.", "INFO", exec_id)
            return  # Sucesso

        except Exception as e:
            retry_count += 1
            log(f"Erro na extracao (Tentativa {retry_count}/{max_retries}): {e}", "ERROR", exec_id)
            if retry_count >= max_retries:
                log(f"[RETRY_ESGOTADO] Extracao falhou definitivamente apos {max_retries} tentativas.", "ERROR", exec_id)
                sys.exit(1)
        finally:
            if connection:
                try: connection.close()
                except: pass

if __name__ == "__main__":
    extract()

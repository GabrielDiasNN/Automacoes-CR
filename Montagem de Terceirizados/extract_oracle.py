# {
#   "version": "1.2.1",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "direct-oracle-fetch, thick-mode-padronizado, retry-on-failure",
#   "description": "Extrai dados do Oracle com Thick Mode e Retry",
#   "reliability": "Base64-Bridge-Logs"
# }
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

import oracledb
from dotenv import load_dotenv

# Carregar ambiente (.env) do projeto raiz
# O arquivo .env esta 1 nivel acima da pasta da automacao.
# override=True alinha a execucao direta ao contrato do Orchestrator,
# evitando que variaveis stale da sessao atual vencam o .env do repositorio.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

# Forca UTF-8 para stdout e stderr para garantir interoperabilidade
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
    """Envia logs para o stderr."""
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    raw_msg = f"[{ts}] [PY-EXTRACT] [{level}] [ExecId:{exec_id}] {message}"
    sys.stderr.write(f"{raw_msg}\n")
    sys.stderr.flush()

def extract() -> None:
    """Funcao principal de extracao."""
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    exec_id: str = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir = os.path.dirname(os.path.abspath(__file__))

    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = "dbprd"

    # Portabilidade: Utilizar caminhos dinamicos ou de ambiente
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get("ORACLE_CLIENT_PATH")
    tns_admin = os.environ.get("TNS_ADMIN")

    if not user or not password or not client_lib or not tns_admin:
        log(
            "Dependencias de ambiente (ORACLE_*, TNS_ADMIN) ausentes.", "ERROR", exec_id
        )
        sys.exit(1)

    os.environ["TNS_ADMIN"] = tns_admin

    if os.path.exists(client_lib):
        try:
            oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
            log("Modo Thick ativado", "INFO", exec_id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            log("Aviso ao iniciar modo Thick: " + str(e), "WARN", exec_id)

    sql_file = os.path.join(script_dir, "SQL-MontagemTerceirizados.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL nao encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)

    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    connection = None
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        connection = None
        try:
            if retry_count > 0:
                wait_sec = [30, 60, 120][min(retry_count - 1, 2)]
                log(
                    f"Tentativa {retry_count + 1}/{max_retries} apos {wait_sec}s...",
                    "WARN",
                    exec_id,
                )
                time.sleep(wait_sec)

            log("Conectando ao Oracle via TNS Alias '" + dsn + "'...", "INFO", exec_id)
            connection = oracledb.connect(user=user, password=password, dsn=dsn)
            cursor = connection.cursor()
            cursor.arraysize = 100

            log("Executando extracao nativa...", "INFO", exec_id)
            cursor.execute(sql)

            if not cursor.description:
                log("Nenhum dado retornado da consulta.", "WARN", exec_id)
                return

            columns = [col[0] for col in cursor.description]

            data = []

            def _clean_val(v: Any) -> Any:
                if isinstance(v, str):
                    return v.strip()
                if isinstance(v, datetime):
                    return v.isoformat()
                return v

            while True:
                batch = cursor.fetchmany(5000)
                if not batch:
                    break
                for row in batch:
                    data.append({col: _clean_val(val) for col, val in zip(columns, row)})

            data_file = os.path.join(script_dir, f".data_{exec_id}.json")
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            log(f"Extracao nativa concluida: {len(data)} registros.", "INFO", exec_id)
            return  # Sucesso

        except Exception as e:  # pylint: disable=broad-exception-caught
            retry_count += 1
            log(
                f"Erro na extracao (Tentativa {retry_count}/{max_retries}): {e}",
                "ERROR",
                exec_id,
            )
            if retry_count >= max_retries:
                log(
                    f"Extracao falhou apos {max_retries} tentativas.",
                    "ERROR",
                    exec_id,
                )
                sys.exit(1)
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

if __name__ == "__main__":
    extract()

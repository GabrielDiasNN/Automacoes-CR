# pylint: disable=import-error
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
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python"))
from automation_log import make_logger
from oracle_retry import make_oracle_retry, CircuitBreakerError
from oracle_client import init_oracle_thick_mode

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


log = make_logger("PY-EXTRACT")

_oracle_retry = make_oracle_retry(attempts=3, wait_initial=30.0, wait_max=120.0, wait_jitter=0.0)


@_oracle_retry
def connect_and_execute(
    user: str, password: str, dsn: str, sql: str, exec_id: str
) -> tuple[list[str], list[Any]]:
    log("Conectando ao Oracle via TNS Alias '" + dsn + "'...", "INFO", exec_id)
    with oracledb.connect(user=user, password=password, dsn=dsn) as connection:
        cursor = connection.cursor()
        cursor.arraysize = 100
        log("Executando extracao nativa...", "INFO", exec_id)
        cursor.execute(sql)
        if not cursor.description:
            return [], []
        columns = [col[0] for col in cursor.description]
        rows = []
        while True:
            batch = cursor.fetchmany(5000)
            if not batch:
                break
            rows.extend(batch)
        return columns, rows


def extract() -> None:
    """Funcao principal de extracao."""
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    exec_id: str = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir = os.path.dirname(os.path.abspath(__file__))

    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = "dbprd"

    # Portabilidade: Utilizar caminhos dinamicos ou de ambiente
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get(
        "ORACLE_CLIENT_PATH"
    )
    tns_admin = os.environ.get("TNS_ADMIN")

    if not user or not password or not client_lib or not tns_admin:
        log(
            "Dependencias de ambiente (ORACLE_*, TNS_ADMIN) ausentes.", "ERROR", exec_id
        )
        sys.exit(1)

    os.environ["TNS_ADMIN"] = tns_admin

    if os.path.exists(client_lib):
        init_oracle_thick_mode(client_lib, tns_admin, lambda msg, lvl="INFO": log(msg, lvl, exec_id))

    sql_file = os.path.join(script_dir, "SQL-MontagemTerceirizados.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL nao encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)

    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    def _clean_val(v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    try:
        columns, rows = connect_and_execute(user, password, dsn, sql, exec_id)
    except CircuitBreakerError:
        log("Circuit Breaker Aberto: Banco de dados inacessivel.", "ERROR", exec_id)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        log(f"Extracao falhou: {e}", "ERROR", exec_id)
        sys.exit(1)

    if not columns:
        log("Nenhum dado retornado da consulta.", "WARN", exec_id)
        return

    data = [{col: _clean_val(val) for col, val in zip(columns, row)} for row in rows]

    data_file = os.path.join(script_dir, f".data_{exec_id}.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    log(f"Extracao nativa concluida: {len(data)} registros.", "INFO", exec_id)


if __name__ == "__main__":
    extract()

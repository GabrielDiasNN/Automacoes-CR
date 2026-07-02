# pylint: disable=import-error, wrong-import-position
# {
#   "version": "1.3.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "direct-oracle-fetch, thick-mode-padronizado, retry-on-failure",
#   "description": "Extrai dados do Oracle com Thick Mode e Retry",
#   "reliability": "Base64-Bridge-Logs"
# }
import json
import os
import sys
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
from automation_log import make_logger
from dotenv import load_dotenv
from oracle_extract import (
    OracleCredentials,
    fetch_all,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from oracle_retry import CircuitBreakerError, make_oracle_retry

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

_oracle_retry = make_oracle_retry(
    attempts=3, wait_initial=30.0, wait_max=120.0, wait_jitter=0.0
)


@_oracle_retry
def _fetch(
    creds: OracleCredentials, sql: str, exec_id: str
) -> tuple[list[str], list[Any]]:
    log(f"Conectando ao Oracle via TNS Alias '{creds.dsn}'...", "INFO", exec_id)
    log("Executando extracao nativa...", "INFO", exec_id)
    return fetch_all(creds, sql, exec_id, log, batch_size=5000, cursor_arraysize=100)


def extract() -> None:
    """Funcao principal de extracao."""
    exec_id: str = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir = os.path.dirname(os.path.abspath(__file__))

    creds = resolve_oracle_credentials(
        log, exec_id, force_dsn="dbprd", require_tns_admin=True
    )
    if creds is None:
        log(
            "Dependencias de ambiente (ORACLE_*, TNS_ADMIN) ausentes.", "ERROR", exec_id
        )
        sys.exit(1)

    os.environ["TNS_ADMIN"] = str(creds.tns_admin)

    init_thick_mode(creds, log, exec_id)

    sql_file = os.path.join(script_dir, "SQL-MontagemTerceirizados.sql")
    if not os.path.exists(sql_file):
        log(f"Arquivo SQL nao encontrado: {sql_file}", "ERROR", exec_id)
        sys.exit(1)

    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    try:
        columns, rows = _fetch(creds, sql, exec_id)
    except CircuitBreakerError:
        log("Circuit Breaker Aberto: Banco de dados inacessivel.", "ERROR", exec_id)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        log(f"Extracao falhou: {e}", "ERROR", exec_id)
        sys.exit(1)

    if not columns:
        log("Nenhum dado retornado da consulta.", "WARN", exec_id)
        return

    data = serialize_rows(columns, rows)

    data_file = os.path.join(script_dir, f".data_{exec_id}.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    log(f"Extracao nativa concluida: {len(data)} registros.", "INFO", exec_id)


if __name__ == "__main__":
    extract()

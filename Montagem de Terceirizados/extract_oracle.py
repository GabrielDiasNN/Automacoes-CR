# Import de lib/python via sys.path.insert() dinamico abaixo forca estas duas
# desabilitacoes: o pylint nao resolve o path em tempo de analise estatica.
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
from automation_log import ensure_utf8_streams, make_logger
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

ensure_utf8_streams()

log = make_logger("PY-EXTRACT")

# Alinhado aos defaults em 08/09/2026, como as outras 5 automacoes. Ate entao
# este era o UNICO dos 6 extratores a sobrescrever o perfil:
# `attempts=3, wait_initial=30.0, wait_max=120.0, wait_jitter=0.0`.
#
# A revisao de qualidade procurou a razao em git log -S, CONTEXT.md,
# CHANGELOG.md, manifesto e run.ps1 e nao achou nenhuma. O dono do sistema
# esclareceu a causa raiz: MT-02 foi a PRIMEIRA automacao do repositorio,
# escrita antes de `lib/python/oracle_retry.py` consolidar um perfil padrao —
# o override e legado, nao decisao deliberada de resiliencia para esta query.
#
# Mudanca de comportamento (importante ao investigar falha de conexao aqui):
# o pior caso de espera entre tentativas cai de ~30s+60s+120s para ~0.1s+0.2s
# com teto de 5s e jitter de ate 1s. A automacao passa a desistir em segundos,
# nao em minutos. Uma indisponibilidade transitoria do Oracle mais longa que o
# teto agora falha o ciclo em vez de aguardar — que e exatamente o
# comportamento das outras 5 contra o mesmo banco. O CircuitBreaker externo
# (fail_max=3, reset_timeout=60) nao muda.
_oracle_retry = make_oracle_retry()


@_oracle_retry
def _fetch(
    creds: OracleCredentials, sql: str, exec_id: str
) -> tuple[list[str], list[Any]]:
    log(f"Conectando ao Oracle via TNS Alias '{creds.dsn}'...", "INFO", exec_id)
    log("Executando extracao nativa...", "INFO", exec_id)
    return fetch_all(creds, sql, exec_id, log, batch_size=5000)


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

    with open(sql_file, encoding="utf-8") as f:
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

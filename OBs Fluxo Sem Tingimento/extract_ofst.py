# pylint: disable=broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "1.0.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "exit-0=ha-obs-novas, exit-2=nada-a-notificar, exit-1=erro",
#   "description": "Extrai OBs fluxo 204 (sem tingimento), confronta com estoque do deposito 95, grava ofst_result.json"
# }
"""Extrator de producao do OFST-06.

Fluxo: OBs (fluxo 204, emitidas, nao montadas, pedido comercial sem sufixo R/S)
-> estoque agregado do deposito 95 por codigo reduzido -> avaliacao
(validators.avaliar_ob) -> ofst_result.json.

Idempotencia por OB, nao por lote: `ofst_state.json` guarda os IDs ja
notificados. Com execucao a cada 60 min, um hash do lote inteiro re-notificaria
a mesma OB a cada flutuacao de estoque — aqui so entra na mensagem OB que ainda
nao foi avisada. O commit do state e do run.ps1 (tmp -> final), so apos o envio
confirmado.
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from automation_log import ensure_utf8_streams, make_logger
from dotenv import load_dotenv
from errors import DadoIncompletoError, SchemaInvalidoError
from models import AvaliacaoOb, EstoqueDeposito, ObSemTingimento, ResumoExecucao
from oracle_extract import (
    OracleCredentials,
    fetch_all,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from oracle_retry import CircuitBreakerError, make_oracle_retry
from queries import SQL_OBS_PATH, build_estoque_sql, chunk_codigos, load_sql
from validators import (
    alocar_estoque,
    dedupe_obs,
    merge_notified_state,
    priorizar_obs,
    validate_estoque_row,
    validate_ob_query,
)

ensure_utf8_streams()

# Import-HubEnv (run.ps1) ja exporta as variaveis para o processo filho, mas o
# script tambem e documentado para execucao standalone (README) — carrega o
# .env diretamente nesse caso, mesmo padrao de Montagem de Terceirizados/extract_oracle.py.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

log = make_logger("OFST-EXTRACT")
_oracle_retry = make_oracle_retry()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "ofst_result.json")
STATE_FILE = os.path.join(SCRIPT_DIR, "ofst_state.json")


@_oracle_retry
def _fetch(
    creds: OracleCredentials,
    sql: str,
    exec_id: str,
    params: dict[str, Any] | None = None,
) -> tuple[list[str], list[Any]]:
    return fetch_all(creds, sql, exec_id, log, batch_size=1000, params=params)


def _read_notified(state_path: str) -> dict[str, str]:
    """Le os IDs de OB ja notificados. State corrompido = tratar como vazio (re-notifica)."""
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, encoding="utf-8") as f:
            notified = json.load(f).get("notified", {})
        return {str(k): str(v) for k, v in notified.items()}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _fetch_obs(
    creds: OracleCredentials, exec_id: str, resumo: ResumoExecucao
) -> list[ObSemTingimento]:
    """Busca, coage e valida as OBs em uma unica passada (via validate_ob_query).

    `validate_ob_query` ja devolve os objetos coagidos em `relatorio.obs` — nao
    ha necessidade de rodar `coerce_ob_row` de novo aqui sobre o retorno cru.
    """
    columns, rows = _fetch(creds, load_sql(SQL_OBS_PATH), exec_id)
    data = serialize_rows(columns, rows, sort_key=lambda r: r.get("NUMERO_OB") or 0)
    relatorio = validate_ob_query(columns, data)
    if not relatorio.ok and relatorio.problemas:
        # Schema quebrado aborta; linha ruim isolada e apenas logada e pulada adiante.
        if any("Colunas obrigatorias ausentes" in p for p in relatorio.problemas):
            raise SchemaInvalidoError(relatorio.problemas[0])
        for problema in relatorio.problemas:
            resumo.falhas.append(problema)
            log(f"OB pulada: {problema}", "WARN", exec_id)

    obs, duplicados = dedupe_obs(relatorio.obs)
    for id_ob in duplicados:
        log(
            f"OB #{id_ob} duplicada no retorno da query (fan-out de join) — "
            f"linha extra descartada.",
            "WARN",
            exec_id,
        )
    return obs


def _fetch_estoque(
    creds: OracleCredentials, codigos: list[int], exec_id: str
) -> dict[int, EstoqueDeposito]:
    """Busca o estoque agregado dos codigos em lotes que cabem numa lista IN do Oracle."""
    estoques: dict[int, EstoqueDeposito] = {}
    for lote in chunk_codigos(codigos):
        sql, params = build_estoque_sql(lote)
        log(
            f"Consultando estoque do deposito 95 para {len(lote)} peca(s)...",
            "INFO",
            exec_id,
        )
        columns, rows = _fetch(creds, sql, exec_id, params)
        for record in serialize_rows(columns, rows):
            try:
                estoque = validate_estoque_row(record)
            except DadoIncompletoError as exc:
                log(f"Estoque descartado: {exc}", "WARN", exec_id)
                continue
            if estoque.tem_fan_out:
                log(
                    f"Peca {estoque.codigo_reduzido}: fan-out de join "
                    f"({estoque.linhas_brutas} linhas -> {estoque.quantidade} pecas distintas). "
                    f"Usando a contagem distinta.",
                    "WARN",
                    exec_id,
                )
            estoques[estoque.codigo_reduzido] = estoque
    return estoques


def _avaliar_todas(
    obs: list[ObSemTingimento], estoques: dict[int, EstoqueDeposito], exec_id: str
) -> list[AvaliacaoOb]:
    """Prioriza (lojas antes da matriz, por data de entrega) e aloca o estoque
    sequencialmente — a ordem das avaliacoes e a ordem final da mensagem."""
    avaliacoes = alocar_estoque(priorizar_obs(obs), estoques)
    for avaliacao in avaliacoes:
        log(f"OB #{avaliacao.ob.id_ob} -> {avaliacao.motivo}", "INFO", exec_id)
    return avaliacoes


def _write_result(
    novas: list[AvaliacaoOb], resumo: ResumoExecucao, notified: dict[str, str]
) -> None:
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": [
                    {
                        "NUMERO_OB": a.ob.id_ob,
                        "CODIGO_REDUZIDO_CRU": a.ob.codigo_reduzido_cru,
                        "CODIGO_ARTIGO_CRU": a.ob.codigo_artigo_cru,
                        "TOTAL_PECAS": a.ob.total_pecas,
                        "KILOS_PROGRAMADOS": a.ob.kilos_programados,
                        "QTD_PECAS_DISPONIVEIS": a.disponivel,
                        "DT_ENTREGA": a.ob.dt_entrega,
                        "NOME_CLIENTE": a.ob.nome_cliente,
                    }
                    for a in novas
                ],
                "total": len(novas),
                "resumo": {
                    "total_obs": resumo.total_obs,
                    "total_notificaveis": resumo.total_notificaveis,
                    "total_sem_estoque": resumo.total_sem_estoque,
                    "total_falhas": len(resumo.falhas),
                    "falhas": resumo.falhas,
                    "tempo_consulta_ms": resumo.tempo_consulta_ms,
                },
                "extracted_at": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(STATE_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(
            {"notified": notified, "updated_at": datetime.now().isoformat()},
            f,
            ensure_ascii=False,
            indent=2,
        )


def extract() -> None:
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    creds = resolve_oracle_credentials(log, exec_id)
    if creds is None:
        sys.exit(1)
    init_thick_mode(creds, log, exec_id)

    resumo = ResumoExecucao()
    inicio = time.perf_counter()

    try:
        obs = _fetch_obs(creds, exec_id, resumo)
        resumo.total_obs = len(obs)
        if not obs:
            log("Nenhuma OB de fluxo 204 emitida e nao montada.", "INFO", exec_id)
            sys.exit(2)

        estoques = _fetch_estoque(
            creds, sorted({ob.codigo_reduzido_cru for ob in obs}), exec_id
        )
        avaliacoes = _avaliar_todas(obs, estoques, exec_id)
        resumo.tempo_consulta_ms = int((time.perf_counter() - inicio) * 1000)

        notificaveis = [a for a in avaliacoes if a.notificar]
        resumo.total_notificaveis = len(notificaveis)
        resumo.total_sem_estoque = len(avaliacoes) - len(notificaveis)

        # Idempotencia: poda por presenca na query (OB montada sai da query e
        # some do state), nunca por notificabilidade — ver merge_notified_state.
        previamente = _read_notified(STATE_FILE)
        novas = [a for a in notificaveis if str(a.ob.id_ob) not in previamente]
        notified = merge_notified_state(
            previamente, avaliacoes, novas, datetime.now().isoformat()
        )

        if not novas:
            log(
                f"{len(notificaveis)} OB(s) prontas, todas ja notificadas. Idempotencia confirmada.",
                "INFO",
                exec_id,
            )
            sys.exit(2)

        _write_result(novas, resumo, notified)
        log(
            f"Extracao concluida: {resumo.total_obs} OBs analisadas, "
            f"{len(novas)} nova(s) a notificar, {resumo.total_sem_estoque} sem estoque, "
            f"{len(resumo.falhas)} falha(s). Tempo: {resumo.tempo_consulta_ms}ms.",
            "INFO",
            exec_id,
        )
        sys.exit(0)

    except SchemaInvalidoError as e:
        log(f"Contrato da query quebrado: {e}", "ERROR", exec_id)
        sys.exit(1)
    except CircuitBreakerError:
        log("Circuit Breaker aberto: falhas persistentes no Oracle.", "ERROR", exec_id)
        sys.exit(1)
    # SystemExit (dos sys.exit acima) herda de BaseException e nao e capturado
    # pelo "except Exception" abaixo — propaga naturalmente.
    except Exception as e:
        log(f"Erro fatal na extracao: {e}", "ERROR", exec_id)
        sys.exit(1)


if __name__ == "__main__":
    extract()

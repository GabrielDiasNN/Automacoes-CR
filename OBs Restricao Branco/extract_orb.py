# import-error e wrong-import-position: import de lib/python via sys.path.insert()
# dinamico (linhas 28-31), que o pylint nao resolve em tempo de analise estatica.
# pylint: disable=broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "1.1.0",
#   "skill": "python-oracle-migration, protocolo-valeg",
#   "contract": "exit-0=ha-obs-novas, exit-2=nada-a-notificar, exit-1=erro",
#   "description": "Extrai OBs brancas, confronta com peças de restrições 3/4 e grava orb_result.json"
# }
"""Extrator de producao do ORB-07.

Fluxo: OBs emitidas, não montadas, classificadas como BRANCO (6) ou BRANCO
2 FIBRAS (9), sem pedido comercial R/S -> estoque de finalidades 3/4 no
depósito 95 por reduzido -> priorização e alocação -> orb_result.json.

Idempotencia por OB, nao por lote: `orb_state.json` guarda, para cada OB ja
notificada, o carimbo do aviso e a RESERVA de estoque criada por ele (reduzido +
quantidade). Com execucao a cada 120 min, um hash do lote inteiro re-notificaria
a mesma OB a cada flutuacao de estoque — aqui so entra na mensagem OB que ainda
nao foi avisada, e o saldo dela segue descontado nos ciclos seguintes (ver
`reservas_vivas`/`JANELA_RESERVA_HORAS` em validators.py). O commit do state e
do run.ps1 (tmp -> final), so apos o envio confirmado.
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
from models import (
    CLASSIFICACOES_BRANCO_ALVO,
    FINALIDADES_PECA_ALVO,
    AvaliacaoOb,
    EstoqueDeposito,
    ObRestricaoBranco,
    ReservaNotificacao,
    ResumoExecucao,
)
from oracle_extract import (
    OracleCredentials,
    fetch_all,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from oracle_retry import CircuitBreakerError, make_oracle_retry
from queries import (
    SQL_OBS_PATH,
    build_estoque_sql,
    build_finalidades_sql,
    chunk_codigos,
    load_sql,
)
from validators import (
    JANELA_RESERVA_HORAS,
    alocar_estoque,
    dedupe_obs,
    merge_notified_state,
    parse_notified_state,
    priorizar_obs,
    reservas_por_reduzido,
    reservas_vivas,
    serialize_notified_state,
    validate_estoque_rows,
    validate_finalidades_query,
    validate_ob_query,
)

ensure_utf8_streams()

# Import-HubEnv (run.ps1) ja exporta as variaveis para o processo filho, mas o
# script tambem e documentado para execucao standalone (README) — carrega o
# .env diretamente nesse caso, mesmo padrao de Montagem de Terceirizados/extract_oracle.py.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

log = make_logger("ORB-EXTRACT")
_oracle_retry = make_oracle_retry()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "orb_result.json")
STATE_FILE = os.path.join(SCRIPT_DIR, "orb_state.json")


@_oracle_retry
def _fetch(
    creds: OracleCredentials,
    sql: str,
    exec_id: str,
    params: dict[str, Any] | None = None,
) -> tuple[list[str], list[Any]]:
    return fetch_all(creds, sql, exec_id, log, batch_size=1000, params=params)


def _read_notified(state_path: str) -> dict[str, ReservaNotificacao]:
    """Le as reservas das OBs ja notificadas.

    JSON realmente invalido = tratar como vazio (re-notifica). O formato ANTIGO
    (`{"185719": "<iso>"}`) NAO e corrupcao: `parse_notified_state` o aceita como
    reserva de quantidade desconhecida, senao as OBs ja avisadas voltariam ao
    grupo como aviso duplicado na primeira execucao apos o deploy.
    """
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, encoding="utf-8") as f:
            notified = json.load(f).get("notified", {})
        return parse_notified_state(notified)
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _fetch_obs(
    creds: OracleCredentials, exec_id: str, resumo: ResumoExecucao
) -> list[ObRestricaoBranco]:
    """Busca, coage e valida as OBs em uma unica passada (via validate_ob_query).

    `validate_ob_query` ja devolve os objetos coagidos em `relatorio.obs` — nao
    ha necessidade de rodar `coerce_ob_row` de novo aqui sobre o retorno cru.
    """
    columns, rows = _fetch(creds, load_sql(SQL_OBS_PATH), exec_id)
    data = serialize_rows(columns, rows, sort_key=lambda r: r.get("NUMERO_OB") or 0)
    resumo.total_lidas = len(data)
    relatorio = validate_ob_query(columns, data)
    if not relatorio.ok and relatorio.problemas:
        # Schema quebrado aborta; linha ruim isolada e apenas logada e pulada adiante.
        if not relatorio.schema_ok:
            raise SchemaInvalidoError(relatorio.problemas[0])
        for problema in relatorio.problemas:
            resumo.falhas.append(problema)
            log(f"OB pulada: {problema}", "WARN", exec_id)

    obs, duplicados, divergencias = dedupe_obs(relatorio.obs)
    for id_ob in duplicados:
        log(
            f"OB #{id_ob} duplicada no retorno da query (fan-out de join) — "
            f"linha extra descartada.",
            "WARN",
            exec_id,
        )
    # Duplicata com linhas DIVERGENTES nunca ocorreu em producao; e este log que
    # vai revelar a frequencia real e permitir avaliar a regra de desempate.
    for divergencia in divergencias:
        log(
            f"OB #{divergencia.id_ob}: linhas duplicadas divergem em "
            f"{', '.join(divergencia.campos)} — mantida a de maior prioridade "
            f"({divergencia.mantida}); descartada ({divergencia.descartada}).",
            "WARN",
            exec_id,
        )
    return obs


def _fetch_finalidades(creds: OracleCredentials, exec_id: str) -> dict[int, str]:
    """Resolve as descricoes das finalidades de peca contabilizadas pela ORB-07.

    O conjunto e FIXO por regra de negocio: FINALIDADES_PECA_ALVO = {3, 4}.
    SGTPRD.COR_FINALIDADE lista para as classes brancas um conjunto maior — que
    inclui a finalidade 1 (SEM RESTRICAO) — mas ampliar o saldo com ela nao e
    permitido. O cadastro e consultado apenas para (a) obter as descricoes
    oficiais e (b) falhar de forma observavel se 3 ou 4 deixarem de ser
    compativeis com as classes 6/9.
    """
    sql, params = build_finalidades_sql(CLASSIFICACOES_BRANCO_ALVO)
    columns, rows = _fetch(creds, sql, exec_id, params)
    cadastro = validate_finalidades_query(
        CLASSIFICACOES_BRANCO_ALVO, serialize_rows(columns, rows)
    )

    ausentes = [f for f in FINALIDADES_PECA_ALVO if f not in cadastro]
    if ausentes:
        raise DadoIncompletoError(
            "COR_FINALIDADE nao lista mais a(s) finalidade(s) "
            f"{', '.join(str(f) for f in ausentes)} como compativel(eis) com as "
            f"classificacoes {', '.join(str(c) for c in CLASSIFICACOES_BRANCO_ALVO)} "
            "— revisar a regra antes de seguir."
        )

    finalidades = {f: cadastro[f] for f in FINALIDADES_PECA_ALVO}
    ignoradas = sorted(set(cadastro) - set(FINALIDADES_PECA_ALVO))
    log(
        "Finalidades contabilizadas: "
        + "; ".join(f"{c} — {d}" for c, d in finalidades.items())
        + (
            f" (ignoradas por regra de negocio: {', '.join(str(f) for f in ignoradas)})"
            if ignoradas
            else ""
        ),
        "INFO",
        exec_id,
    )
    return finalidades


def _fetch_estoque(  # pylint: disable=too-many-locals
    creds: OracleCredentials,
    codigos: list[int],
    finalidades: dict[int, str],
    exec_id: str,
) -> dict[int, EstoqueDeposito]:
    """Busca o estoque agregado dos codigos em lotes que cabem numa lista IN do Oracle.

    A query devolve, por reduzido, uma linha total (GROUPING SETS) e uma linha
    por finalidade — agrupadas aqui antes de validar, ja que o veredito de
    coerencia (`validate_estoque_rows`) precisa das duas visoes juntas.
    """
    estoques: dict[int, EstoqueDeposito] = {}
    codigos_finalidades = sorted(finalidades)
    for lote in chunk_codigos(codigos):
        sql, params = build_estoque_sql(lote, codigos_finalidades)
        log(
            f"Consultando estoque do deposito 95 para {len(lote)} peca(s) "
            f"em {len(codigos_finalidades)} finalidade(s) compativeis...",
            "INFO",
            exec_id,
        )
        columns, rows = _fetch(creds, sql, exec_id, params)
        por_codigo: dict[Any, list[dict[str, Any]]] = {}
        for record in serialize_rows(columns, rows):
            por_codigo.setdefault(record.get("CODIGO_REDUZIDO_PROD"), []).append(record)
        for registros in por_codigo.values():
            try:
                estoque = validate_estoque_rows(registros, finalidades)
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
    obs: list[ObRestricaoBranco],
    estoques: dict[int, EstoqueDeposito],
    reservado: dict[int, int],
    vivas: dict[str, ReservaNotificacao],
    exec_id: str,
) -> list[AvaliacaoOb]:
    """Prioriza (lojas antes da matriz, por data de entrega) e aloca o estoque
    sequencialmente — a ordem das avaliacoes e a ordem final da mensagem.

    `reservado` e o que OBs anunciadas em ciclos anteriores ainda seguram;
    `vivas` sao essas mesmas OBs (por id), para `alocar_estoque` pular a
    deducao duplicada do saldo ja descontado via `reservado`."""
    avaliacoes = alocar_estoque(priorizar_obs(obs), estoques, reservado, vivas)
    for avaliacao in avaliacoes:
        log(f"OB #{avaliacao.ob.id_ob} -> {avaliacao.motivo}", "INFO", exec_id)
    return avaliacoes


def _record_counts(resumo: ResumoExecucao, novas_count: int) -> dict[str, int]:
    """Contadores canonicos do padrao de logging (docs/logging-standard.md).

    O run.ps1 le este bloco de orb_result.json e o embute no evento
    execution.end -- a fonte da verdade do resultado da execucao.
    """
    qualified = resumo.total_notificaveis
    return {
        "read": resumo.total_lidas or resumo.total_obs,
        "validated": resumo.total_obs,
        "rejected": len(resumo.falhas),
        "qualified": qualified,
        "notified": novas_count,
        "skipped": resumo.total_sem_estoque,
        "suppressed": max(qualified - novas_count, 0),
    }


def _write_result(novas: list[AvaliacaoOb], resumo: ResumoExecucao) -> None:
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": [
                    {
                        "NUMERO_OB": a.ob.id_ob,
                        "CODIGO_REDUZIDO_CRU": a.ob.codigo_reduzido_cru,
                        "CODIGO_ARTIGO_CRU": a.ob.codigo_artigo_cru,
                        "CODIGO_FLUXO": a.ob.codigo_fluxo,
                        "CODIGO_COR_TINGIMENTO": a.ob.codigo_cor_tingimento,
                        "CD_CLASSIFICACAO_COR": a.ob.codigo_classificacao_cor,
                        "DS_CLASSIFICACAO_COR": a.ob.descricao_classificacao_cor,
                        "RESTRICOES_DISPONIVEIS": [
                            {"codigo": codigo, "descricao": descricao}
                            for codigo, descricao in a.restricoes_disponiveis
                        ],
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
                "record_counts": _record_counts(resumo, len(novas)),
                "extracted_at": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _write_counts(resumo: ResumoExecucao, novas_count: int) -> None:
    """Escreve orb_result.json minimo nas saidas sem OB nova (exit 2).

    O run.ps1 le `record_counts` daqui para o evento execution.end mesmo quando
    nao ha linhas a notificar -- caso contrario o desfecho mais comum ("nada a
    notificar") ficaria sem contadores.
    """
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": [],
                "total": 0,
                "record_counts": _record_counts(resumo, novas_count),
                "extracted_at": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _write_state_tmp(notified: dict[str, ReservaNotificacao]) -> None:
    """Prepara o próximo state; o run.ps1 decide quando fazer o commit."""
    with open(STATE_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(
            {
                "notified": serialize_notified_state(notified),
                "updated_at": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def extract() -> None:  # pylint: disable=too-many-locals,too-many-statements
    """Executa extração, alocação e preparação idempotente do ciclo."""
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
            if resumo.falhas:
                # Linhas VIERAM da query mas nenhuma sobreviveu a coerce_ob_row
                # (`resumo.falhas` so' e populado por linha rejeitada — query
                # vazia de verdade nunca o preenche). Sinal de schema/dado fora
                # do contrato, nao de "nada a notificar": tratar como exit 2
                # commitaria orb_state.json.tmp vazio e apagaria TODAS as
                # reservas de idempotencia vivas, re-anunciando ao grupo as OBs
                # ja avisadas assim que o dado normalizar. Aborta sem tocar
                # no state (nem tmp e escrito) para o proximo ciclo reavaliar
                # com o state intacto.
                log(
                    f"{len(resumo.falhas)} linha(s) retornadas pela query, "
                    "nenhuma sobreviveu a validacao — abortando sem tocar no "
                    "state (idempotencia preservada).",
                    "ERROR",
                    exec_id,
                )
                sys.exit(1)
            _write_state_tmp({})
            _write_counts(resumo, 0)
            log("Nenhuma OB branca emitida e não montada.", "INFO", exec_id)
            sys.exit(2)

        finalidades = _fetch_finalidades(creds, exec_id)
        estoques = _fetch_estoque(
            creds,
            sorted({ob.codigo_reduzido_cru for ob in obs}),
            finalidades,
            exec_id,
        )

        # A reserva das OBs ja anunciadas e descontada ANTES da alocacao: a
        # Expedicao nao separa as pecas ao receber o aviso, entao a promessa
        # "pronta para montagem" tem de valer entre ciclos. A expiracao acontece
        # aqui, num lugar so' — OB cuja reserva venceu sai do state por completo
        # e volta a concorrer pelo estoque neste mesmo ciclo.
        agora = datetime.now().isoformat()
        previamente = _read_notified(STATE_FILE)
        vivas = reservas_vivas(previamente, agora)
        expiradas = sorted(set(previamente) - set(vivas))
        if expiradas:
            log(
                f"{len(expiradas)} reserva(s) vencida(s) apos {JANELA_RESERVA_HORAS}h "
                f"(OB(s) {', '.join(expiradas)}) — estoque liberado e OB(s) de volta "
                f"a concorrer.",
                "WARN",
                exec_id,
            )
        reservado = reservas_por_reduzido(vivas)
        for codigo, quantidade in sorted(reservado.items()):
            log(
                f"Peca {codigo}: {quantidade} un reservadas por OB(s) ja anunciadas.",
                "INFO",
                exec_id,
            )

        avaliacoes = _avaliar_todas(obs, estoques, reservado, vivas, exec_id)
        resumo.tempo_consulta_ms = int((time.perf_counter() - inicio) * 1000)

        notificaveis = [a for a in avaliacoes if a.notificar]
        resumo.total_notificaveis = len(notificaveis)
        resumo.total_sem_estoque = len(avaliacoes) - len(notificaveis)

        # Idempotencia: poda por presenca na query (OB montada sai da query e
        # some do state), nunca por notificabilidade — ver merge_notified_state.
        novas = [a for a in notificaveis if str(a.ob.id_ob) not in vivas]
        notified = merge_notified_state(vivas, avaliacoes, novas, agora)
        _write_state_tmp(notified)

        if not novas:
            _write_counts(resumo, 0)
            detalhe = (
                f"{len(notificaveis)} OB(s) prontas, todas ja notificadas. "
                "Idempotencia confirmada."
            )
            log(
                detalhe,
                "INFO",
                exec_id,
            )
            sys.exit(2)

        _write_result(novas, resumo)
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

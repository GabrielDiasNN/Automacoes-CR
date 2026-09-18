"""Coletor de triagem de falhas de execucao do Orchestrator.

Uso (a partir da raiz do repositorio, com o Python do .venv):

    .venv\\Scripts\\python .claude\\skills\\log-triage\\triagem.py coletar [--horas 24]
    .venv\\Scripts\\python .claude\\skills\\log-triage\\triagem.py logs <exec_id> [--linhas 120]
    .venv\\Scripts\\python .claude\\skills\\log-triage\\triagem.py requeue <exec_id> --motivo "..."

`coletar` e `logs` sao somente leitura. `requeue` e a UNICA acao mutavel e exige
`--motivo`; ela reenfileira uma execucao terminal pela rota oficial
POST /api/executions/{id}/requeue (mesma validacao do botao do dashboard).

A API Key nunca e passada por argumento: e lida de ORCHESTRATOR_API_KEY no .env.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

# Status terminais que representam falha (espelha EXECUTION_FAILED_STATUSES de
# Orchestrator/app/constants.py; EXPIRED fica fora de proposito -- e tick
# descartado por congestionamento de queue_group, nao automacao que falhou).
STATUS_FALHA = ("ERROR", "TIMEOUT", "TERMINATED", "FAILED_BY_REBOOT")

# Tetos dos Query params de GET /api/executions e /{id}/logs
# (Orchestrator/app/routers/executions.py). Passar acima deles nao e "pedir
# mais": e 422, que antes virava relatorio silenciosamente cego.
LIMITE_LINHAS_LOG = 5000
LIMITE_POR_PAGINA = 200

# Status que representam entrega efetiva (espelha EXECUTION_DELIVERED_STATUSES).
# PARTIAL conta: o entregavel principal saiu, so um canal secundario degradou.
STATUS_ENTREGUE = ("SUCCESS", "PARTIAL")

# Formato em que a API devolve datas (`format_dt_br`, schemas/common.py). Nao e
# ISO: ordenar essa string direto ordena por dia do mes antes do mes e do ano.
FORMATO_DATA_API = "%d/%m/%Y %H:%M:%S"

# Assinaturas de log que caracterizam causa transitoria (rede, Oracle, lock).
# Usadas apenas como PISTA para o agente: nenhuma decisao de requeue e tomada
# por este script.
PISTAS_TRANSITORIAS = (
    "ora-12170",
    "ora-03113",
    "ora-03114",
    "ora-12541",
    "ora-12514",
    "tns:",
    "dpy-4011",
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "circuitbreaker",
    "circuit breaker",
)

# Assinaturas que indicam defeito deterministico: requeue cego repete a falha.
PISTAS_DETERMINISTICAS = (
    "traceback (most recent call last)",
    "modulenotfounderror",
    "importerror",
    "syntaxerror",
    "attributeerror",
    "keyerror",
    "typeerror",
    "ora-00904",
    "ora-00942",
    "ora-01722",
    "invalid identifier",
    "table or view does not exist",
    "cannot find path",
    "is not recognized as",
    # Defeito do engine WhatsApp contra a API interna do WhatsApp Web: quebra
    # deterministicamente em toda tentativa. Sem estas assinaturas, o log de
    # uma falha dessas era classificado como transitorio (a mensagem tambem
    # carrega o "timeout" do handshake) e convidava a requeue cego.
    "must include an id property",
    "cannot read properties of undefined",
    "is not a function",
    "window.store",
)


def ler_env() -> dict[str, str]:
    """Parser minimo de .env -- mesma semantica de Lib-Config/driver.py."""
    env: dict[str, str] = {}
    caminho = ROOT / ".env"
    if not caminho.exists():
        return env
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        if "=" not in linha or linha.strip().startswith("#"):
            continue
        chave, valor = linha.split("=", 1)
        valor = re.sub(r"\s+#.*$", "", valor.strip()).strip().strip('"').strip("'")
        env[chave.strip()] = valor
    return env


ENV = ler_env()
BASE = "http://127.0.0.1:" + ENV.get("HUB_API_PORT", "8000")
API_KEY = ENV.get("ORCHESTRATOR_API_KEY", "")


def _requisicao(
    rota: str, metodo: str = "GET", corpo: dict[str, Any] | None = None
) -> Any:
    rota = rota if rota.startswith("/") else "/" + rota
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    cabecalhos = {"X-API-Key": API_KEY}
    if dados is not None:
        cabecalhos["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE + rota, data=dados, headers=cabecalhos, method=metodo
    )
    # Esquema e host sao fixos (http://127.0.0.1) e nao vem de entrada externa.
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def _classificar(linhas: list[str]) -> str:
    """Pista heuristica sobre a natureza da falha, a partir do log."""
    texto = "\n".join(linhas).lower()
    tem_det = any(pista in texto for pista in PISTAS_DETERMINISTICAS)
    tem_tra = any(pista in texto for pista in PISTAS_TRANSITORIAS)
    if tem_det and not tem_tra:
        return "provavel_deterministica"
    if tem_tra and not tem_det:
        return "provavel_transitoria"
    if tem_tra and tem_det:
        return "ambigua"
    return "indefinida"


def _linhas_relevantes(linhas: list[str], maximo: int) -> list[str]:
    """Ultimas `maximo` linhas nao vazias -- onde o erro terminal aparece."""
    uteis = [linha.rstrip() for linha in linhas if linha.strip()]
    return uteis[-maximo:]


def _ordenar_por_fim(falha: dict[str, Any]) -> datetime:
    """Chave de ordenacao cronologica real a partir do `finished_at` da API.

    `finished_at` chega como `DD/MM/YYYY HH:MM:SS`, entao comparar a string
    ordenava por dia do mes: 30/09 vinha depois de 01/10, e a falha mais antiga
    aparecia no topo da lista que o agente le como "mais recentes primeiro".
    """
    bruto = str(falha.get("finished_at") or "").strip()
    try:
        return datetime.strptime(bruto, FORMATO_DATA_API)
    except ValueError:
        # Execucao sem `finished_at` (ou em formato inesperado) vai para o fim
        # da lista ordenada por recencia, nao para o topo.
        return datetime.min


def _buscar_logs(exec_id: str, linhas: int) -> tuple[list[str], str | None]:
    """Ultimas linhas do log de uma execucao, mais o erro que impediu a leitura.

    Devolve `(linhas, erro)`. O erro e explicito porque antes qualquer 429, 5xx
    ou 422 virava lista vazia: o relatorio saia com `envelope: {}` e
    `pista: "indefinida"`, indistinguivel de execucao que realmente nao logou
    nada, e o agente concluia "o log nao diz nada" em vez de "nao consegui ler".
    """
    # `linhas * 3` estourava o teto `le=5000` do Query acima de 1666 linhas, e
    # `linhas <= 0` violava `ge=1`; nos dois casos a API respondia 422.
    janela = min(max(linhas, 1) * 3, LIMITE_LINHAS_LOG)
    try:
        cabeca = _requisicao("/api/executions/" + exec_id + "/logs?offset=0&limit=1")
        total = int(cabeca.get("total_lines", 0))
        offset = max(0, total - janela)
        rota = "/api/executions/" + exec_id + f"/logs?offset={offset}&limit={janela}"
        pagina = _requisicao(rota)
    except urllib.error.HTTPError as exc:
        return [], f"HTTP {exc.code} ao ler o log ({exc.reason})"
    except (urllib.error.URLError, OSError) as exc:
        return [], "transporte ao ler o log: " + str(exc)
    except ValueError as exc:
        return [], "resposta invalida ao ler o log: " + str(exc)
    brutas = pagina.get("lines") or []
    return _linhas_relevantes([str(linha) for linha in brutas], max(linhas, 1)), None


def _resumir_envelope(linhas: list[str]) -> dict[str, Any]:
    """Extrai o essencial do log estruturado (JSONL do padrao de logging).

    O `execution.end` de cada automacao carrega `outcome_reason` e a lista de
    `steps` com `ok`/`duration_ms`. Sem este resumo, o relatorio joga linhas
    JSON de 1-2 KB cada na janela do agente e o diagnostico se perde no ruido.
    """
    resumo: dict[str, Any] = {}
    erros: list[str] = []
    for linha in linhas:
        texto = linha.strip()
        if not texto.startswith("{"):
            continue
        try:
            evento = json.loads(texto)
        except json.JSONDecodeError:
            continue
        if not isinstance(evento, dict):
            continue
        if evento.get("event") == "execution.end":
            resumo["outcome_code"] = evento.get("outcome_code")
            resumo["outcome_reason"] = evento.get("outcome_reason")
            resumo["trace_id"] = evento.get("trace_id")
            resumo["record_counts"] = evento.get("record_counts")
            passos = evento.get("steps") or []
            resumo["steps_falhos"] = [
                passo.get("step")
                for passo in passos
                if isinstance(passo, dict) and passo.get("ok") is False
            ]
        elif str(evento.get("level", "")).upper() in ("ERRO", "ERROR", "FATAL"):
            mensagem = str(evento.get("message") or "").strip()
            if mensagem and mensagem not in erros:
                erros.append(mensagem)
    if erros:
        resumo["mensagens_erro"] = erros[-5:]
    return resumo


def _resumir(
    item: dict[str, Any], log: list[str], log_erro: str | None, incluir_bruto: bool
) -> dict[str, Any]:
    """Achata uma execucao da API no registro de triagem."""
    registro: dict[str, Any] = {
        "exec_id": item.get("id"),
        "automacao": item.get("automation_name"),
        "automation_id": item.get("automation_id"),
        "status": item.get("status"),
        "exit_code": item.get("exit_code"),
        "failure_reason": item.get("failure_reason"),
        "recovery_action": item.get("recovery_action"),
        "retry_count": item.get("retry_count"),
        "max_retries": item.get("max_retries"),
        "requeue_allowed": item.get("requeue_allowed"),
        "requeue_block_reason": item.get("requeue_block_reason"),
        "queue_group": item.get("queue_group"),
        "started_at": item.get("started_at"),
        "finished_at": item.get("finished_at"),
        "requested_by": item.get("requested_by"),
        "pista": _classificar(log),
        "envelope": _resumir_envelope(log),
    }
    # Presente somente quando a leitura do log falhou. Sem este campo, "log
    # ilegivel" e "log vazio" chegavam identicos ao agente.
    if log_erro:
        registro["log_erro"] = log_erro
    # O log bruto e opcional de proposito: cada linha JSONL tem 1-2 KB e o
    # `envelope` ja carrega outcome_reason, steps falhos e mensagens de erro.
    # Incluir tudo por padrao enchia a janela do agente agendado de ruido.
    if incluir_bruto:
        registro["log_final"] = log
    return registro


def _listar_status(desde: str, status: str) -> tuple[list[dict[str, Any]], str | None]:
    """Todas as paginas de um status de falha na janela.

    Antes a coleta pedia uma unica pagina com `per_page=200` (o teto do Query) e
    ignorava `pages`, entao uma automacao em crashloop com 350 falhas rendia 200
    registros e um `total_falhas` que reportava 200 como se fosse o total --
    justamente no cenario em que a contagem de reincidencia decide entre
    requeue e "isto e defeito, abra PR".
    """
    itens: list[dict[str, Any]] = []
    pagina_atual = 1
    while True:
        rota = (
            f"/api/executions?status={status}&per_page={LIMITE_POR_PAGINA}"
            f"&page={pagina_atual}&date_from={desde}"
        )
        try:
            pagina = _requisicao(rota)
        except urllib.error.HTTPError as exc:
            return itens, f"{status}: HTTP {exc.code} ({exc.reason})"
        except (urllib.error.URLError, OSError) as exc:
            return itens, f"{status}: transporte ({exc})"
        itens.extend(pagina.get("items") or [])
        try:
            total_paginas = int(pagina.get("pages", 1))
        except (TypeError, ValueError):
            total_paginas = 1
        if pagina_atual >= total_paginas:
            return itens, None
        pagina_atual += 1


def _coletar_falhas(
    desde: str, linhas: int, incluir_bruto: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    """Varre cada status de falha e devolve os registros e os erros parciais.

    Erro em um status nao aborta a coleta dos outros: antes, um 422 pontual
    descartava tudo que ja tinha sido coletado e o relatorio saia como se a API
    estivesse fora do ar.
    """
    falhas: list[dict[str, Any]] = []
    erros: list[str] = []
    for status in STATUS_FALHA:
        itens, erro = _listar_status(desde, status)
        if erro:
            erros.append(erro)
        for item in itens:
            log, log_erro = _buscar_logs(str(item.get("id")), linhas)
            falhas.append(_resumir(item, log, log_erro, incluir_bruto))
    falhas.sort(key=_ordenar_por_fim, reverse=True)
    return falhas, erros


def _ultima_entrega(automation_id: int) -> tuple[str | None, str | None]:
    """Execucao entregue mais recente de uma automacao, sem filtro de janela.

    Devolve `(finished_at, status)`. Deliberadamente SEM `date_from`: a pergunta
    e "esta automacao voltou a funcionar?", e a resposta pode estar fora da
    janela triada.
    """
    melhor: dict[str, Any] | None = None
    for status in STATUS_ENTREGUE:
        rota = (
            f"/api/executions?automation_id={automation_id}"
            f"&status={status}&per_page=1&page=1"
        )
        try:
            pagina = _requisicao(rota)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            continue
        itens = pagina.get("items") or []
        if not itens:
            continue
        candidato = itens[0]
        if melhor is None or _ordenar_por_fim(candidato) > _ordenar_por_fim(melhor):
            melhor = candidato
    if melhor is None:
        return None, None
    return str(melhor.get("finished_at") or ""), str(melhor.get("status") or "")


def _estado_por_automacao(falhas: list[dict[str, Any]]) -> dict[str, Any]:
    """Cruza cada automacao que falhou na janela com sua ultima entrega.

    Sem isto, o relatorio so mostrava falhas e o agente inferia recuperacao por
    AUSENCIA de falha nova -- que tambem acontece com automacao desabilitada, com
    cron que nao disparou ou com worker que nao pegou a tarefa. `recuperada`
    responde com evidencia positiva: existe entrega posterior a ultima falha.
    """
    estado: dict[str, Any] = {}
    for falha in falhas:
        nome = str(falha.get("automacao") or "Desconhecido")
        fim = _ordenar_por_fim(falha)
        registro = estado.get(nome)
        if registro is None:
            estado[nome] = {
                "automation_id": falha.get("automation_id"),
                "falhas_na_janela": 1,
                "ultima_falha": falha.get("finished_at"),
                "_fim": fim,
            }
            continue
        registro["falhas_na_janela"] += 1
        if fim > registro["_fim"]:
            registro["ultima_falha"] = falha.get("finished_at")
            registro["_fim"] = fim

    for registro in estado.values():
        automation_id = registro.get("automation_id")
        ultima_falha = registro.pop("_fim")
        if not isinstance(automation_id, int):
            registro["recuperada"] = None
            registro["ultimo_sucesso"] = None
            continue
        entrega, status_entrega = _ultima_entrega(automation_id)
        registro["ultimo_sucesso"] = entrega
        registro["ultimo_sucesso_status"] = status_entrega
        if entrega is None:
            # Nenhuma entrega registrada: nao e "nao recuperada", e "nunca
            # entregou" -- distincao que muda o diagnostico.
            registro["recuperada"] = False
            continue
        fim_entrega = _ordenar_por_fim({"finished_at": entrega})
        registro["recuperada"] = fim_entrega > ultima_falha
    return estado


def _contar_reincidencia(falhas: list[dict[str, Any]]) -> dict[str, int]:
    """Falhas por automacao, da mais reincidente para a menos."""
    reincidencia: dict[str, int] = {}
    for falha in falhas:
        nome = str(falha.get("automacao") or "Desconhecido")
        reincidencia[nome] = reincidencia.get(nome, 0) + 1
    return dict(sorted(reincidencia.items(), key=lambda par: par[1], reverse=True))


def cmd_coletar(horas: int, linhas: int, incluir_bruto: bool) -> int:
    """Monta o relatorio de triagem em JSON no stdout."""
    # `isoformat()` com a HORA, nao `.date()`: `date_from` e parseado com
    # `datetime.fromisoformat` no backend e aceita timestamp completo. Cortar a
    # hora fazia `--horas 14` as 08:00 comecar a meia-noite do dia anterior --
    # janela real de ~32 h com `janela_horas` reportando 14, e o agente (que tem
    # requeue autonomo e raciocina sobre "nao reincidente na janela") reavaliando
    # falha que a execucao das 19:00 ja tinha tratado.
    inicio = datetime.now() - timedelta(hours=horas)
    desde = inicio.isoformat(timespec="seconds")
    try:
        saude = _requisicao("/api/system/health/full")
    except urllib.error.HTTPError as exc:
        # HTTPError ANTES de URLError, de quem e subclasse: a API RESPONDEU (429
        # do RateLimitMiddleware, 500 de health degradado). Dizer "nao respondeu"
        # aqui fazia o agente agendado parar e reportar que o Orchestrator estava
        # fora do ar -- mesma distincao que driver.py:88 preserva.
        erro = {"erro": f"API respondeu HTTP {exc.code} ({exc.reason}) em {BASE}"}
        print(json.dumps(erro, ensure_ascii=False))
        return 1
    except (urllib.error.URLError, OSError) as exc:
        erro = {"erro": "API nao respondeu em " + BASE + ": " + str(exc)}
        print(json.dumps(erro, ensure_ascii=False))
        return 1

    falhas, erros_parciais = _coletar_falhas(desde, linhas, incluir_bruto)
    relatorio: dict[str, Any] = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "janela_horas": horas,
        "janela_inicio": desde,
        "saude": {
            "database": saude.get("database"),
            "scheduler": saude.get("scheduler"),
            "worker": saude.get("worker"),
            "pending_tasks": saude.get("pending_tasks"),
        },
        "total_falhas": len(falhas),
        "reincidencia_por_automacao": _contar_reincidencia(falhas),
        "estado_por_automacao": _estado_por_automacao(falhas),
        "falhas": falhas,
    }
    # Coleta incompleta e dado de primeira classe: sem isto, um relatorio ao qual
    # faltava um status inteiro era indistinguivel de um relatorio completo, e o
    # agente decidia requeue sobre contagem de reincidencia subestimada.
    if erros_parciais:
        relatorio["coleta_incompleta"] = True
        relatorio["erros_parciais"] = erros_parciais
    logs_ilegiveis = sum(1 for falha in falhas if falha.get("log_erro"))
    if logs_ilegiveis:
        relatorio["logs_ilegiveis"] = logs_ilegiveis
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return 0


def cmd_logs(exec_id: str, linhas: int) -> int:
    """Imprime as ultimas linhas do log de uma execucao."""
    log, erro = _buscar_logs(exec_id, linhas)
    if erro:
        print("[FALHA] " + exec_id + ": " + erro)
        return 1
    if not log:
        print("[OK] " + exec_id + " nao registrou log (execucao sem saida).")
        return 0
    print("\n".join(log))
    return 0


def cmd_requeue(exec_id: str, motivo: str) -> int:
    """Reenfileira uma execucao terminal pela rota oficial de requeue."""
    corpo = {"reason": motivo, "requested_by": "AGENTE_TRIAGEM"}
    try:
        resposta = _requisicao("/api/executions/" + exec_id + "/requeue", "POST", corpo)
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        print(f"[FALHA] requeue recusado (HTTP {exc.code}): {detalhe}")
        return 1
    except (urllib.error.URLError, OSError) as exc:
        print("[FALHA] API nao respondeu: " + str(exc))
        return 1
    print(json.dumps(resposta, ensure_ascii=False, indent=2))
    return 0


def _inteiro_positivo(valor: str) -> int:
    """Valida `--horas`/`--linhas` na borda do CLI.

    Clampar silenciosamente `--linhas 0` para o minimo entregava um relatorio
    sintaticamente valido e sem diagnostico nenhum (nenhum `execution.end` cabe
    em 3 linhas). Recusar na entrada diz ao operador o que aconteceu.
    """
    try:
        numero = int(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{valor}' nao e um inteiro.") from exc
    if numero < 1:
        raise argparse.ArgumentTypeError("deve ser >= 1.")
    return numero


def _construir_parser() -> argparse.ArgumentParser:
    """CLI com os tres subcomandos (coletar, logs, requeue)."""
    parser = argparse.ArgumentParser(description="Triagem de falhas do Orchestrator.")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_col = sub.add_parser("coletar", help="Relatorio JSON das falhas da janela.")
    p_col.add_argument("--horas", type=_inteiro_positivo, default=24)
    p_col.add_argument("--linhas", type=_inteiro_positivo, default=60)
    p_col.add_argument(
        "--bruto",
        action="store_true",
        help="Inclui as linhas de log cruas, alem do envelope resumido.",
    )

    p_log = sub.add_parser("logs", help="Ultimas linhas do log de uma execucao.")
    p_log.add_argument("exec_id")
    p_log.add_argument("--linhas", type=_inteiro_positivo, default=120)

    p_req = sub.add_parser("requeue", help="Reenfileira uma execucao terminal.")
    p_req.add_argument("exec_id")
    p_req.add_argument("--motivo", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Despacha o subcomando e devolve o exit code do processo."""
    # Sem isto o stdout redirecionado para arquivo sai em cp1252 no Windows e o
    # JSON do relatorio fica ilegivel para quem o consome (acentos das
    # mensagens de log das automacoes).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _construir_parser().parse_args(argv)
    if not API_KEY:
        print("[FALHA] ORCHESTRATOR_API_KEY ausente no .env da raiz.")
        return 1

    if args.comando == "coletar":
        return cmd_coletar(int(args.horas), int(args.linhas), bool(args.bruto))
    if args.comando == "logs":
        return cmd_logs(str(args.exec_id), int(args.linhas))
    return cmd_requeue(str(args.exec_id), str(args.motivo))


if __name__ == "__main__":
    sys.exit(main())

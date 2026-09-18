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


def _buscar_logs(exec_id: str, linhas: int) -> list[str]:
    janela = max(linhas * 3, linhas)
    try:
        cabeca = _requisicao("/api/executions/" + exec_id + "/logs?offset=0&limit=1")
        total = int(cabeca.get("total_lines", 0))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return []
    offset = max(0, total - janela)
    rota = "/api/executions/" + exec_id + f"/logs?offset={offset}&limit={janela}"
    try:
        pagina = _requisicao(rota)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return []
    brutas = pagina.get("lines") or []
    return _linhas_relevantes([str(linha) for linha in brutas], linhas)


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
    item: dict[str, Any], log: list[str], incluir_bruto: bool
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
    # O log bruto e opcional de proposito: cada linha JSONL tem 1-2 KB e o
    # `envelope` ja carrega outcome_reason, steps falhos e mensagens de erro.
    # Incluir tudo por padrao enchia a janela do agente agendado de ruido.
    if incluir_bruto:
        registro["log_final"] = log
    return registro


def _coletar_falhas(
    desde: str, linhas: int, incluir_bruto: bool
) -> list[dict[str, Any]]:
    """Varre cada status de falha e devolve os registros de triagem."""
    falhas: list[dict[str, Any]] = []
    for status in STATUS_FALHA:
        rota = f"/api/executions?status={status}&per_page=200&date_from={desde}"
        pagina = _requisicao(rota)
        for item in pagina.get("items") or []:
            log = _buscar_logs(str(item.get("id")), linhas)
            falhas.append(_resumir(item, log, incluir_bruto))
    falhas.sort(key=lambda falha: str(falha.get("finished_at") or ""), reverse=True)
    return falhas


def _contar_reincidencia(falhas: list[dict[str, Any]]) -> dict[str, int]:
    """Falhas por automacao, da mais reincidente para a menos."""
    reincidencia: dict[str, int] = {}
    for falha in falhas:
        nome = str(falha.get("automacao") or "Desconhecido")
        reincidencia[nome] = reincidencia.get(nome, 0) + 1
    return dict(sorted(reincidencia.items(), key=lambda par: par[1], reverse=True))


def cmd_coletar(horas: int, linhas: int, incluir_bruto: bool) -> int:
    """Monta o relatorio de triagem em JSON no stdout."""
    # `date().isoformat()` e nao `%d/%m/%Y`: este valor nao e exibicao, e o
    # parametro `date_from` de GET /api/executions, que o backend parseia em
    # ISO. A regra de datas do repositorio governa data para humano; aqui a
    # data e contrato de API.
    desde = (datetime.now() - timedelta(hours=horas)).date().isoformat()
    try:
        saude = _requisicao("/api/system/health/full")
        falhas = _coletar_falhas(desde, linhas, incluir_bruto)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        erro = {"erro": "API nao respondeu em " + BASE + ": " + str(exc)}
        print(json.dumps(erro, ensure_ascii=False))
        return 1

    relatorio = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "janela_horas": horas,
        "saude": {
            "database": saude.get("database"),
            "scheduler": saude.get("scheduler"),
            "worker": saude.get("worker"),
            "pending_tasks": saude.get("pending_tasks"),
        },
        "total_falhas": len(falhas),
        "reincidencia_por_automacao": _contar_reincidencia(falhas),
        "falhas": falhas,
    }
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return 0


def cmd_logs(exec_id: str, linhas: int) -> int:
    """Imprime as ultimas linhas do log de uma execucao."""
    log = _buscar_logs(exec_id, linhas)
    if not log:
        print("[FALHA] sem logs para " + exec_id + " (inexistente ou log vazio)")
        return 1
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


def _construir_parser() -> argparse.ArgumentParser:
    """CLI com os tres subcomandos (coletar, logs, requeue)."""
    parser = argparse.ArgumentParser(description="Triagem de falhas do Orchestrator.")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_col = sub.add_parser("coletar", help="Relatorio JSON das falhas da janela.")
    p_col.add_argument("--horas", type=int, default=24)
    p_col.add_argument("--linhas", type=int, default=60)
    p_col.add_argument(
        "--bruto",
        action="store_true",
        help="Inclui as linhas de log cruas, alem do envelope resumido.",
    )

    p_log = sub.add_parser("logs", help="Ultimas linhas do log de uma execucao.")
    p_log.add_argument("exec_id")
    p_log.add_argument("--linhas", type=int, default=120)

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

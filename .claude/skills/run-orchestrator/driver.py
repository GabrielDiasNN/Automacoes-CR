"""Driver de execucao do Orchestrator (API FastAPI + Dashboard SPA).

Uso (sempre a partir da raiz do repositorio, com o Python do .venv):

    .venv\\Scripts\\python .claude\\skills\\run-orchestrator\\driver.py <comando> [args]

Comandos:
    health                 GET /api/system/health (sem browser). Exit 0 se saudavel.
    api <rota> [...]       GET autenticado em uma ou mais rotas /api/*. Imprime resumo do JSON.
    login                  Fluxo real de usuario: digita a API Key no gate e entra. Screenshot.
    shot <rota> [...]      Injeta a chave em sessionStorage (pula o gate) e captura cada rota.
    smoke                  login + varredura de todas as rotas + relatorio de console. Exit 1 se houver erro.

Screenshots vao para Logs/driver/ (diretorio ignorado pelo git).
A API Key nunca e passada por argumento: e lida de ORCHESTRATOR_API_KEY no .env.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
SHOT_DIR = ROOT / "Logs" / "driver"

ROTAS = ["painel", "execucoes", "monitor", "beneficiamento", "automacoes", "sistema"]

# Ruido conhecido do console que nao caracteriza falha do app.
IGNORAR_CONSOLE = (
    "Download the React DevTools",
    "favicon.ico",
)


def ler_env() -> dict[str, str]:
    """Parser minimo de .env — mesma semantica de Lib-Config/Get-OrchestratorEnvValue."""
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
PORTA = ENV.get("HUB_API_PORT", "8000")
BASE = f"http://127.0.0.1:{PORTA}"
API_KEY = ENV.get("ORCHESTRATOR_API_KEY", "")


def _get_json(rota: str) -> object:
    rota = rota if rota.startswith("/") else "/" + rota
    req = urllib.request.Request(BASE + rota, headers={"X-API-Key": API_KEY})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - host fixo 127.0.0.1
        return json.loads(resp.read().decode("utf-8"))


def cmd_health() -> int:
    try:
        dados = _get_json("/api/system/health")
    except (urllib.error.URLError, OSError) as exc:
        print(f"[FALHA] API nao respondeu em {BASE}: {exc}")
        print("        Suba com: pwsh -File Infrastructure\\Start-Orchestrator.ps1")
        return 1
    assert isinstance(dados, dict)
    worker = dados.get("worker") or {}
    print(f"status     : {dados.get('status')}")
    print(f"database   : {dados.get('database')}")
    print(f"scheduler  : {dados.get('scheduler')}")
    print(f"worker     : alive={worker.get('is_alive')} pid={worker.get('pid')} tasks={worker.get('tasks_completed')}")
    print(f"pendentes  : {dados.get('pending_tasks')}")
    ok = dados.get("database") == "online" and dados.get("scheduler") == "executando"
    print("[OK] saudavel" if ok else "[FALHA] degradado")
    return 0 if ok else 1


def cmd_api(rotas: list[str]) -> int:
    if not rotas:
        print("uso: driver.py api /api/automations [...]")
        return 2
    falhou = False
    for rota in rotas:
        try:
            dados = _get_json(rota)
        except urllib.error.HTTPError as exc:
            print(f"[FALHA] {rota} -> HTTP {exc.code}")
            falhou = True
            continue
        except (urllib.error.URLError, OSError) as exc:
            print(f"[FALHA] {rota} -> {exc}")
            falhou = True
            continue
        if isinstance(dados, list):
            print(f"[OK] {rota} -> lista com {len(dados)} itens")
            if dados:
                print("     primeiro: " + json.dumps(dados[0], ensure_ascii=False)[:300])
        else:
            print(f"[OK] {rota} -> " + json.dumps(dados, ensure_ascii=False)[:400])
    return 1 if falhou else 0


def _nova_pagina(pw: Playwright, injetar_chave: bool) -> tuple[Browser, Page, list[str]]:
    navegador = pw.chromium.launch()
    contexto = navegador.new_context(viewport={"width": 1600, "height": 950})
    if injetar_chave:
        # sessionStorage precisa existir ANTES do bundle rodar: client.ts le a chave
        # no carregamento do modulo (nao em useEffect).
        contexto.add_init_script(
            f"sessionStorage.setItem('orchestrator_api_key', {json.dumps(API_KEY)});"
        )
    pagina = contexto.new_page()
    erros: list[str] = []
    pagina.on(
        "console",
        lambda m: erros.append(f"{m.type}: {m.text}")
        if m.type in ("error", "warning") and not any(r in m.text for r in IGNORAR_CONSOLE)
        else None,
    )
    pagina.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    return navegador, pagina, erros


def _capturar(pagina: Page, nome: str) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    destino = SHOT_DIR / f"{nome}.png"
    pagina.screenshot(path=str(destino), full_page=False)
    print(f"     screenshot: {destino.relative_to(ROOT)}")
    return destino


def cmd_login() -> int:
    if not API_KEY:
        print("[FALHA] ORCHESTRATOR_API_KEY ausente no .env")
        return 1
    with sync_playwright() as pw:
        navegador, pagina, erros = _nova_pagina(pw, injetar_chave=False)
        try:
            pagina.goto(f"{BASE}/dashboard/", wait_until="networkidle", timeout=30000)
            gate = pagina.get_by_label("API Key")
            gate.wait_for(state="visible", timeout=10000)
            _capturar(pagina, "login-gate")
            gate.fill(API_KEY)
            pagina.get_by_role("button", name=re.compile("Entrar")).click()
            # O shell so aparece depois que o gate cede; ancoramos na navegacao real.
            pagina.get_by_role("link", name=re.compile("Painel", re.I)).wait_for(timeout=15000)
            pagina.wait_for_timeout(2500)
            _capturar(pagina, "login-painel")
            print(f"[OK] login concluido — titulo: {pagina.title()!r}")
        finally:
            navegador.close()
    for erro in erros:
        print(f"     console: {erro}")
    return 0


def cmd_shot(rotas: list[str]) -> int:
    rotas = rotas or ROTAS
    problemas: list[str] = []
    with sync_playwright() as pw:
        navegador, pagina, erros = _nova_pagina(pw, injetar_chave=True)
        try:
            for rota in rotas:
                alvo = f"{BASE}/dashboard/{rota.strip('/')}"
                pagina.goto(alvo, wait_until="networkidle", timeout=30000)
                pagina.wait_for_timeout(2500)
                if pagina.get_by_label("API Key").count() > 0:
                    problemas.append(f"{rota}: gate de API Key apareceu (chave nao aceita)")
                print(f"[OK] {alvo}")
                _capturar(pagina, f"rota-{rota.strip('/') or 'raiz'}")
        finally:
            navegador.close()
    for erro in erros:
        print(f"     console: {erro}")
    problemas.extend(erros)
    return 1 if problemas else 0


def cmd_smoke() -> int:
    print("== 1/3 health ==")
    rc = cmd_health()
    if rc:
        return rc
    print("\n== 2/3 login (fluxo real) ==")
    rc = cmd_login()
    if rc:
        return rc
    print("\n== 3/3 rotas ==")
    return cmd_shot([])


COMANDOS: dict[str, Callable[[list[str]], int]] = {
    "health": lambda _: cmd_health(),
    "api": cmd_api,
    "login": lambda _: cmd_login(),
    "shot": cmd_shot,
    "smoke": lambda _: cmd_smoke(),
}


def main(argv: list[str]) -> int:
    handler = COMANDOS.get(argv[0]) if argv else None
    if handler is None:
        if argv:
            print(f"comando desconhecido: {argv[0]}")
        print(__doc__)
        return 2
    return handler(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

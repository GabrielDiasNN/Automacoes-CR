"""Driver de execucao do Orchestrator (API FastAPI + Dashboard SPA).

Uso (sempre a partir da raiz do repositorio, com o Python do .venv):

    .venv\\Scripts\\python .claude\\skills\\run-orchestrator\\driver.py <comando> [args]

Comandos:
    health                 GET /api/system/health (sem browser). Exit 0 se saudavel.
    api <rota> [...]       GET autenticado em uma ou mais rotas /api/*. Imprime resumo do JSON.
    login                  Fluxo real de usuario: digita a API Key no gate e entra. Screenshot.
    shot <rota> [...]      Injeta a chave em sessionStorage (pula o gate) e captura cada rota.
    smoke                  login + varredura de todas as rotas + relatorio de console.

Politica de exit code dos comandos com browser (`login`, `shot`, `smoke`): exit 1
apenas com `error` de console, `pageerror` ou gate de API Key inesperado.
`warning` de console e listado no relatorio mas NAO reprova — veja IGNORAR_CONSOLE.

Opcao comum: `--tag <rotulo>` sufixa os PNGs (`rota-painel--<rotulo>.png`), para
comparar antes/depois sem sobrescrever a evidencia anterior.

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

# Estado de processo preenchido por main(). Dicionario em vez de variavel solta
# para nao precisar de `global` (pylint W0603) em `_extrair_tag`.
CONFIG: dict[str, str] = {"sufixo_shot": ""}


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
    # Esquema e host sao fixos (http://127.0.0.1) e nao vem de entrada externa.
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def cmd_health() -> int:
    try:
        dados = _get_json("/api/system/health")
    except urllib.error.HTTPError as exc:
        # HTTPError e subclasse de URLError e precisa vir ANTES: a API respondeu
        # (429 do RateLimitMiddleware, 500 de health degradado). Sugerir restart
        # aqui derrubaria uma instancia viva de producao.
        print(f"[FALHA] /api/system/health -> HTTP {exc.code} ({exc.reason})")
        print("        A API respondeu; NAO reinicie o Orchestrator por causa disto.")
        return 1
    except (urllib.error.URLError, OSError) as exc:
        print(f"[FALHA] API nao respondeu em {BASE}: {exc}")
        print("        Suba com: pwsh -File Infrastructure\\Start-Orchestrator.ps1")
        return 1
    if not isinstance(dados, dict):
        print("[FALHA] payload inesperado de /api/system/health (esperado objeto JSON)")
        return 1
    worker = dados.get("worker") or {}
    print(f"status     : {dados.get('status')}")
    print(f"database   : {dados.get('database')}")
    print(f"scheduler  : {dados.get('scheduler')}")
    print(
        f"worker     : alive={worker.get('is_alive')} pid={worker.get('pid')} "
        f"tasks={worker.get('tasks_completed')}"
    )
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
                print(
                    "     primeiro: " + json.dumps(dados[0], ensure_ascii=False)[:300]
                )
        else:
            print(f"[OK] {rota} -> " + json.dumps(dados, ensure_ascii=False)[:400])
    return 1 if falhou else 0


class ColetorConsole:
    """Acumula console/pageerror carimbando a rota corrente e separando erro de aviso."""

    def __init__(self) -> None:
        self.rota = "-"
        self.erros: list[str] = []
        self.avisos: list[str] = []

    def registrar(self, tipo: str, texto: str) -> None:
        if any(ruido in texto for ruido in IGNORAR_CONSOLE):
            return
        destino = self.avisos if tipo == "warning" else self.erros
        destino.append(f"[{self.rota}] {tipo}: {texto}")

    def relatar(self) -> None:
        for aviso in self.avisos:
            print(f"     console (aviso): {aviso}")
        for erro in self.erros:
            print(f"     console: {erro}")


def _nova_pagina(
    pw: Playwright, injetar_chave: bool
) -> tuple[Browser, Page, ColetorConsole]:
    navegador = pw.chromium.launch()
    contexto = navegador.new_context(viewport={"width": 1600, "height": 950})
    if injetar_chave:
        # sessionStorage precisa existir ANTES do bundle rodar: client.ts le a chave
        # no carregamento do modulo (nao em useEffect).
        contexto.add_init_script(
            f"sessionStorage.setItem('orchestrator_api_key', {json.dumps(API_KEY)});"
        )
    pagina = contexto.new_page()
    coletor = ColetorConsole()
    pagina.on(
        "console",
        lambda m: (
            coletor.registrar(m.type, m.text)
            if m.type in ("error", "warning")
            else None
        ),
    )
    pagina.on("pageerror", lambda e: coletor.registrar("pageerror", str(e)))
    return navegador, pagina, coletor


def _capturar(pagina: Page, nome: str) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    destino = SHOT_DIR / f"{nome}{CONFIG['sufixo_shot']}.png"
    pagina.screenshot(path=str(destino), full_page=False)
    print(f"     screenshot: {destino.relative_to(ROOT)}")
    return destino


def cmd_login() -> int:
    with sync_playwright() as pw:
        navegador, pagina, coletor = _nova_pagina(pw, injetar_chave=False)
        coletor.rota = "login"
        try:
            pagina.goto(f"{BASE}/dashboard/", wait_until="networkidle", timeout=30000)
            gate = pagina.get_by_label("API Key")
            gate.wait_for(state="visible", timeout=10000)
            _capturar(pagina, "login-gate")
            gate.fill(API_KEY)
            pagina.get_by_role("button", name=re.compile("Entrar")).click()
            # O shell so aparece depois que o gate cede; ancoramos na navegacao real.
            pagina.get_by_role("link", name=re.compile("Painel", re.I)).wait_for(
                timeout=15000
            )
            pagina.wait_for_timeout(2500)
            _capturar(pagina, "login-painel")
            print(f"[OK] login concluido — titulo: {pagina.title()!r}")
        finally:
            navegador.close()
    coletor.relatar()
    return 1 if coletor.erros else 0


def cmd_shot(rotas: list[str]) -> int:
    rotas = rotas or ROTAS
    problemas: list[str] = []
    with sync_playwright() as pw:
        navegador, pagina, coletor = _nova_pagina(pw, injetar_chave=True)
        try:
            for rota in rotas:
                nome = rota.strip("/") or "raiz"
                coletor.rota = nome
                alvo = f"{BASE}/dashboard/{rota.strip('/')}"
                pagina.goto(alvo, wait_until="networkidle", timeout=30000)
                pagina.wait_for_timeout(2500)
                if pagina.get_by_label("API Key").count() > 0:
                    problemas.append(
                        f"{nome}: gate de API Key apareceu (chave nao aceita)"
                    )
                print(f"[OK] {alvo}")
                _capturar(pagina, f"rota-{nome}")
        finally:
            navegador.close()
    coletor.relatar()
    problemas.extend(coletor.erros)
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

# `health` bate numa rota publica (Orchestrator/app/routers/system.py, sem
# Depends(get_api_key)); os demais mandam X-API-Key e devolveriam 403 mudo.
COMANDOS_SEM_CHAVE = frozenset({"health"})


def _extrair_tag(argv: list[str]) -> tuple[list[str], str]:
    if "--tag" not in argv:
        return argv, ""
    indice = argv.index("--tag")
    valor = argv[indice + 1] if indice + 1 < len(argv) else ""
    if not valor:
        return argv[:indice], ""
    seguro = re.sub(r"[^A-Za-z0-9._-]", "-", valor)
    return argv[:indice] + argv[indice + 2 :], f"--{seguro}"


def main(argv: list[str]) -> int:
    argv, CONFIG["sufixo_shot"] = _extrair_tag(argv)
    handler = COMANDOS.get(argv[0]) if argv else None
    if handler is None:
        if argv:
            print(f"comando desconhecido: {argv[0]}")
        print(__doc__)
        return 2
    if argv[0] not in COMANDOS_SEM_CHAVE and not API_KEY:
        print(
            f"[FALHA] ORCHESTRATOR_API_KEY ausente ou vazia no .env ({ROOT / '.env'})"
        )
        print(
            "        Sem a chave a API responde 403. Nao passe a chave por argumento."
        )
        return 1
    return handler(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

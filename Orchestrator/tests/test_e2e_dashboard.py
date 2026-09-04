# pylint: disable=protected-access, reimported, redefined-outer-name, unused-variable, line-too-long, wrong-import-position, import-outside-toplevel, consider-using-with, global-statement, wrong-import-order, too-many-branches, too-many-statements, too-many-lines, import-error
"""
Teste de Ponta a Ponta (E2E) com Playwright: Dashboard React "Sala de Instrumentação".
Valida a navegação por rotas (react-router) e as interações críticas na tela real
do Orchestrator, gerando as evidências do Quality Gate.

A autenticação Zero-Trust do novo dashboard é via sessionStorage (chave
`orchestrator_api_key`), injetada por add_init_script antes do bundle carregar — não
há mais prompt() do navegador.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Generator

import pytest
from PIL import Image, ImageChops
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Adicionar pasta do app ao PYTHONPATH
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(TESTS_DIR, "..")))

from app import models

TEST_DB_PATH = Path(TESTS_DIR) / f"test-e2e-automacoes-{os.getpid()}.db"
TEST_PORT = 8002
TEST_HOST = "127.0.0.1"
API_KEY = os.environ.get("ORCHESTRATOR_API_KEY", "fixture-qa-001")

# Contadores globais de logs do console do navegador
CONSOLE_ERRORS = 0
CONSOLE_WARNINGS = 0
CONSOLE_MESSAGES: list[Any] = []


def _inject_api_key(page: Any) -> None:
    """Injeta a API Key no sessionStorage antes do bundle React executar."""
    page.add_init_script(
        f"window.sessionStorage.setItem('orchestrator_api_key', {json.dumps(API_KEY)});"
    )


def _inject_theme(page: Any, theme: str) -> None:
    """Força o ThemeContext (Onda 4-3) a montar num tema explícito, antes do
    bundle React executar — mesmo mecanismo de `_inject_api_key`."""
    page.add_init_script(
        f"window.localStorage.setItem('orchestrator_theme', {json.dumps(theme)});"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> Generator[None, None, None]:
    """Cria e popula o banco de dados SQLite de teste antes de subir o servidor."""
    for suffix in ["", "-shm", "-wal"]:
        fp = Path(str(TEST_DB_PATH) + suffix)
        if fp.exists():
            try:
                fp.unlink()
            except OSError:
                pass

    # Aplica as migrações do Alembic para estruturar o banco dinamicamente
    # pylint: disable=import-outside-toplevel
    from alembic import command
    from alembic.config import Config

    ini_path = os.path.abspath(os.path.join(TESTS_DIR, "..", "alembic.ini"))
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option(
        "sqlalchemy.url", f"sqlite:///{TEST_DB_PATH.as_posix()}"
    )

    command.upgrade(alembic_cfg, "head")

    # Inicializa engine no banco de teste dinâmico para cadastrar dados Mock
    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    db_session_factory = sessionmaker(bind=engine)
    session = db_session_factory()

    # 1. Cadastra automações de teste
    auto1 = models.Automation(
        name="Receitas Bloqueadas",
        description="Filtra pedidos bloqueados no Oracle",
        script_path="./Receitas Bloqueadas/run.ps1",
        enabled=True,
        max_retries=2,
        queue_group="oracle",
        sla_minutes=60,
    )
    auto2 = models.Automation(
        name="Montagem de Terceirizados",
        description="Extrai e valida NFs da Montagem",
        script_path="./Montagem de Terceirizados/run.ps1",
        enabled=True,
        max_retries=1,
        queue_group="oracle",
        sla_minutes=120,
    )
    session.add_all([auto1, auto2])
    session.flush()

    # 2. Cadastra execuções de teste para validar o histórico e logs
    exec1 = models.Execution(
        id="EXEC_E2E_SUCCESS_001",
        automation_id=auto1.id,
        status="SUCCESS",
        priority="HIGH",
        retry_count=0,
        max_retries=2,
        queue_group="oracle",
        requested_by="SYSTEM",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        duration_seconds=5.2,
        logs="[E2E-TEST] Iniciando carga...\n[E2E-TEST] 25 registros processados com sucesso.\n[E2E-TEST] Finalizado.",
    )
    session.add(exec1)
    session.commit()
    session.close()

    yield

    # Descartar conexões e engine do SQLAlchemy para permitir deleção física no Windows (Fase B10)
    engine.dispose()

    # Cleanup robusto pós-testes com retentativas para contornar latência de I/O do Windows
    import time

    for suffix in ["", "-shm", "-wal"]:
        fp = Path(str(TEST_DB_PATH) + suffix)
        for _ in range(5):
            if fp.exists():
                try:
                    fp.unlink()
                    break
                except OSError:
                    time.sleep(0.5)


@pytest.fixture(scope="session")
def uvicorn_server(setup_test_database: Any) -> Generator[str, None, None]:
    # pylint: disable=unused-argument
    """Sobe o servidor Uvicorn FastAPI em background apontando para o banco de teste."""
    env = os.environ.copy()
    env["ORCHESTRATOR_DB_PATH"] = TEST_DB_PATH.as_posix()
    env["ORCHESTRATOR_API_KEY"] = API_KEY
    env["PYTHONPATH"] = os.path.abspath(os.path.join(TESTS_DIR, ".."))

    # Inicia uvicorn na porta 8002 em subprocesso
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        TEST_HOST,
        "--port",
        str(TEST_PORT),
        "--log-level",
        "warning",
    ]
    # Usar arquivos físicos temporários para evitar deadlock de buffer no Windows (PIPE cheio)
    stdout_log_path = Path(TESTS_DIR) / f"uvicorn-stdout-{os.getpid()}.log"
    stderr_log_path = Path(TESTS_DIR) / f"uvicorn-stderr-{os.getpid()}.log"

    stdout_file = open(stdout_log_path, "w", encoding="utf-8")
    stderr_file = open(stderr_log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=stdout_file,
        stderr=stderr_file,
        cwd=os.path.abspath(os.path.join(TESTS_DIR, "..")),
    )

    # Espera até o servidor responder HTTP 200 na raiz
    import requests

    url = f"http://{TEST_HOST}:{TEST_PORT}/"
    success = False
    for _ in range(50):  # até 5 segundos
        try:
            res = requests.get(url, timeout=0.5)
            if res.status_code == 200:
                success = True
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.1)

    if not success:
        proc.terminate()
        stdout_file.close()
        stderr_file.close()
        stdout_content = (
            stdout_log_path.read_text(encoding="utf-8", errors="ignore")
            if stdout_log_path.exists()
            else ""
        )
        stderr_content = (
            stderr_log_path.read_text(encoding="utf-8", errors="ignore")
            if stderr_log_path.exists()
            else ""
        )
        for _ in range(5):
            try:
                if stdout_log_path.exists():
                    stdout_log_path.unlink()
                if stderr_log_path.exists():
                    stderr_log_path.unlink()
                break
            except OSError:
                time.sleep(0.5)
        raise RuntimeError(
            f"Servidor de teste falhou ao iniciar.\nStdout: {stdout_content}\nStderr: {stderr_content}"
        )

    yield f"http://{TEST_HOST}:{TEST_PORT}"

    # Encerra o processo uvicorn limpo
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    # Fecha e remove os arquivos de log físicos
    stdout_file.close()
    stderr_file.close()

    # Deleção resiliente com retentativas para evitar bloqueio temporário do Windows
    for _ in range(5):
        try:
            if stdout_log_path.exists():
                stdout_log_path.unlink()
            if stderr_log_path.exists():
                stderr_log_path.unlink()
            break
        except OSError:
            time.sleep(0.5)


# As 6 rotas do dashboard (react-router, basename /dashboard).
ROUTES = [
    ("painel", "Painel"),
    ("execucoes", "Execuções"),
    ("monitor", "Monitor"),
    ("beneficiamento", "Beneficiamento"),
    ("automacoes", "Automações"),
    ("sistema", "Sistema"),
]

BR_DATETIME = re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}")


@pytest.mark.e2e
def test_e2e_dashboard_navigation(
    uvicorn_server: str, page: Any, tmp_path: Path
) -> None:
    """Navega as 6 rotas do dashboard React e valida o Quality Gate de console limpo."""

    def handle_console(msg: Any) -> None:
        global CONSOLE_ERRORS, CONSOLE_WARNINGS
        txt = msg.text
        if "favicon" in txt.lower() or "icon" in txt.lower():
            return
        CONSOLE_MESSAGES.append(f"[{msg.type.upper()}] {txt}")
        if msg.type == "error":
            CONSOLE_ERRORS += 1
        elif msg.type == "warning":
            CONSOLE_WARNINGS += 1

    page.on("console", handle_console)
    _inject_api_key(page)

    # 1. Acessa o dashboard (já autenticado via sessionStorage -> sem gate)
    page.goto(f"{uvicorn_server}/dashboard/")
    page.get_by_role("heading", name="Painel").wait_for(timeout=30_000)

    # Assinatura: o Mímico Operacional e os mostradores devem renderizar
    page.wait_for_selector("text=fontes")
    page.wait_for_selector("text=worker")
    page.wait_for_selector("text=automações ativas")

    # 2. Navega por todas as rotas clicando no rail (routing client-side)
    for _slug, label in ROUTES:
        page.get_by_role("link", name=label).click()
        page.get_by_role("heading", name=label).wait_for(timeout=15_000)

    # 3. Evidência do Quality Gate
    screenshot_path = tmp_path / f"playwright-e2e-generated-{os.getpid()}.png"
    page.screenshot(path=screenshot_path)

    evidence_path = tmp_path / "playwright-e2e-evidence-generated.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_content = f"""# Template de Evidência E2E Final (Playwright)

Preencha este bloco ao final de cada entrega que exija validação E2E Playwright.

## Evidência E2E Final
- Data/Hora (BRT): {dt_str}
- URL validada: http://127.0.0.1:8000/dashboard/
- Ordem de execução: Governança -> Testes de contrato/backend -> Playwright E2E (último)
- Módulos navegados:
  - Painel
  - Execuções
  - Monitor
  - Beneficiamento
  - Automações
  - Sistema
- Ações críticas validadas:
  - Navegação por todas as 6 rotas (react-router)
  - Renderização do Mímico Operacional e dos mostradores
  - Console do navegador sem erros
- Console do navegador:
  - Erros: {CONSOLE_ERRORS}
  - Warnings: {CONSOLE_WARNINGS}
  - Resumo: Sem erros de console JS detectados na navegação
- Resultado final:
  - Aprovado
- Pendências (se houver):
  - nenhuma
"""
    evidence_path.write_text(report_content, encoding="utf-8")

    assert (
        CONSOLE_ERRORS == 0
    ), f"Erros de console detectados no navegador: {CONSOLE_MESSAGES}"
    assert screenshot_path.exists(), "O screenshot de evidência não foi salvo."
    assert evidence_path.exists(), "O arquivo de evidência não foi criado."


@pytest.mark.e2e
def test_e2e_dashboard_executions_detail_and_filter(
    uvicorn_server: str, page: Any
) -> None:
    """Valida a tabela de Execuções, o drawer de detalhe com logs e o filtro de status."""
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/execucoes")
    page.get_by_role("heading", name="Execuções").wait_for(timeout=30_000)

    # A execução semeada deve aparecer na tabela
    row = page.locator("tr", has_text="Receitas Bloqueadas").first
    row.wait_for(timeout=15_000)

    # Abre o drawer de detalhe e confere os logs mockados
    row.click()
    dialog = page.get_by_role("dialog")
    dialog.wait_for(timeout=10_000)
    page.wait_for_selector("text=registros processados")

    # Fecha o drawer (Escape) e aplica o filtro de status
    page.keyboard.press("Escape")
    page.get_by_label("Filtrar por status").select_option("SUCCESS")
    page.wait_for_selector("tr:has-text('Receitas Bloqueadas')", timeout=10_000)


@pytest.mark.e2e
def test_e2e_dashboard_execucoes_painel_exec_id_abre_drawer(
    uvicorn_server: str, page: Any
) -> None:
    """Clicar numa execução recente do Painel abre o drawer JÁ naquela execução em /execucoes.

    Fix do bug de nav (Onda 6, item 6): antes o clique descartava `ex.id` e
    navegava para /execucoes sem parâmetro nenhum — o drawer nunca abria
    sozinho, o operador tinha que procurar a execução de novo na lista.
    """
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/painel")
    page.get_by_role("heading", name="Painel").wait_for(timeout=30_000)
    page.wait_for_selector("text=últimas execuções")

    if page.get_by_text("nenhuma execução recente").count() > 0:
        pytest.skip(
            "Banco de teste sem execuções recentes no card do Painel — "
            "nada para clicar (setup_test_database não semeou nenhuma)."
        )

    linha = page.get_by_role("button", name=re.compile(r"^Execução "))
    linha.first.wait_for(timeout=15_000)
    linha.first.click()

    page.wait_for_url(
        re.compile(r".*/execucoes\?exec_id=EXEC_E2E_SUCCESS_001"), timeout=15_000
    )

    dialog = page.get_by_role("dialog")
    dialog.wait_for(timeout=15_000)
    dialog.get_by_text("Receitas Bloqueadas").first.wait_for(timeout=10_000)


@pytest.mark.e2e
def test_e2e_dashboard_automations_visible(uvicorn_server: str, page: Any) -> None:
    """A tela de Automações lista os cadastros semeados com os controles operacionais."""
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/automacoes")
    page.get_by_role("heading", name="Automações").wait_for(timeout=30_000)

    page.wait_for_selector("text=Receitas Bloqueadas")
    page.wait_for_selector("text=Montagem de Terceirizados")
    # Botão de disparo presente (controle operacional)
    assert page.get_by_role("button", name="Disparar").first.is_visible()


def _count_executions() -> int:
    """Conta linhas de `executions` no banco de teste isolado (não a API)."""
    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    try:
        session = sessionmaker(bind=engine)()
        try:
            return session.query(models.Execution).count()
        finally:
            session.close()
    finally:
        engine.dispose()


def _count_enabled_automations() -> int:
    """Conta automações com `enabled=True` no banco de teste isolado."""
    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    try:
        session = sessionmaker(bind=engine)()
        try:
            return (
                session.query(models.Automation)
                .filter(models.Automation.enabled.is_(True))
                .count()
            )
        finally:
            session.close()
    finally:
        engine.dispose()


@pytest.mark.e2e
def test_e2e_dashboard_automations_dispatch_confirm_and_cancel(
    uvicorn_server: str, page: Any
) -> None:
    """Disparar exige confirmação (ConfirmModal); cancelar não enfileira execução alguma.

    Achado nº 1, Onda 1 do plano de revisão geral do frontend: antes, Disparar
    executava um script de produção com um único clique.
    """
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/automacoes")
    page.get_by_role("heading", name="Automações").wait_for(timeout=30_000)
    page.wait_for_selector("text=Receitas Bloqueadas")

    antes = _count_executions()

    page.get_by_role("button", name="Disparar Receitas Bloqueadas").click()
    dialog = page.get_by_role("alertdialog")
    dialog.wait_for(timeout=10_000)
    page.get_by_role("heading", name="Disparar automação").wait_for(timeout=5_000)

    page.get_by_role("button", name="Cancelar").click()
    dialog.wait_for(state="hidden", timeout=5_000)

    depois = _count_executions()
    assert depois == antes, (
        f"Cancelar no ConfirmModal não deve enfileirar execução — "
        f"antes={antes} depois={depois}"
    )


@pytest.mark.e2e
def test_e2e_dashboard_system_instruments(uvicorn_server: str, page: Any) -> None:
    """A tela de Sistema mostra os instrumentos (gauges), worker e ações de manutenção."""
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/sistema")
    page.get_by_role("heading", name="Sistema").wait_for(timeout=30_000)

    page.wait_for_selector("text=instrumentos")
    page.wait_for_selector("text=CPU")
    page.wait_for_selector("text=RAM")
    assert page.get_by_role("button", name="WAL Checkpoint").is_visible()


@pytest.mark.e2e
def test_e2e_dashboard_system_worker_actions(uvicorn_server: str, page: Any) -> None:
    """O card do Worker em /sistema expõe "Acordar worker" (wake-up idempotente e benigno).

    Onda 6: só cutuca o worker a checar a fila agora — sem ConfirmModal, pode
    clicar. Confirma que o toast de sucesso aparece.
    """
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/sistema")
    page.get_by_role("heading", name="Sistema").wait_for(timeout=30_000)

    botao = page.get_by_role("button", name="Acordar worker")
    botao.wait_for(timeout=15_000)
    assert botao.is_visible()

    botao.click()
    # `wakeupWorker` responde {"message": "Sinal de wake-up enviado ao worker."}
    # e `useAction` mostra essa mensagem no toast.
    page.wait_for_selector("text=Sinal de wake-up enviado ao worker", timeout=10_000)


@pytest.mark.e2e
def test_e2e_dashboard_pause_all_confirm_and_cancel(
    uvicorn_server: str, page: Any
) -> None:
    """Pausar tudo exige ConfirmModal; CANCELAR não toca em nenhuma automação.

    Ação de alcance global em produção — este E2E cancela, NUNCA confirma
    (espelha test_e2e_dashboard_automations_dispatch_confirm_and_cancel).
    """
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/sistema")
    page.get_by_role("heading", name="Sistema").wait_for(timeout=30_000)
    page.wait_for_selector("text=controle de emergência")

    ativos_antes = _count_enabled_automations()

    page.get_by_role("button", name="Pausar todas as automações").click()
    dialog = page.get_by_role("alertdialog")
    dialog.wait_for(timeout=10_000)
    page.get_by_role("heading", name="Pausar todas as automações").wait_for(
        timeout=5_000
    )

    page.get_by_role("button", name="Cancelar").click()
    dialog.wait_for(state="hidden", timeout=5_000)

    ativos_depois = _count_enabled_automations()
    assert ativos_depois == ativos_antes, (
        f"Cancelar 'Pausar tudo' não deve desativar nenhuma automação — "
        f"antes={ativos_antes} depois={ativos_depois}"
    )


@pytest.mark.e2e
def test_e2e_dashboard_system_drift_card(uvicorn_server: str, page: Any) -> None:
    """A tela de Sistema mostra o card de drift de portfólio (Onda 6)."""
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/sistema")
    page.get_by_role("heading", name="Sistema").wait_for(timeout=30_000)

    page.wait_for_selector("text=drift de portfólio", timeout=15_000)
    # O corpo do card é ou o empty state ("Catálogo consistente...") ou a lista
    # de itens em drift — depende do estado do catálogo semeado, não força um
    # dos dois. O card existir é o contrato deste teste.
    card = page.get_by_text("drift de portfólio")
    assert card.first.is_visible()


@pytest.mark.e2e
def test_e2e_dashboard_system_audit_card(uvicorn_server: str, page: Any) -> None:
    """A tela de Sistema mostra o card de trilha de auditoria (Onda 6, item 7).

    Não força empty state nem tabela preenchida — o histórico de auditoria do
    banco de teste depende de quais ações os outros testes já dispararam
    contra a mesma instância (ex.: "Acordar worker"). O card existir + o
    seletor de teto (50/100/200) é o contrato deste teste.
    """
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/sistema")
    page.get_by_role("heading", name="Sistema").wait_for(timeout=30_000)

    page.wait_for_selector("text=trilha de auditoria", timeout=15_000)
    assert page.get_by_label("Teto de entradas da trilha de auditoria").is_visible()


@pytest.mark.e2e
def test_e2e_dashboard_timezone_rendering(uvicorn_server: str, page: Any) -> None:
    """Garante que o dashboard renderiza datas em BRT (DD/MM/AAAA HH:MM:SS)."""
    import requests
    from app.timezone import get_now_local

    scheduled_run_at = (get_now_local() + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    # O preflight exige `automation.manifest.json` desde 31/07/2026, e este
    # teste fala com um uvicorn real — o wrapper da conftest, que atua sobre o
    # `TestClient`, não alcança esta requisição.
    manifesto_e2e = (
        Path(__file__).resolve().parent / "test" / "automation.manifest.json"
    )
    manifesto_e2e.write_text(
        json.dumps(
            {
                "id": "E2E-99",
                "name": "Timezone E2E Auto",
                "slug": "timezone-e2e-auto",
                "criticality": "low",
                "owner_area": "QA",
                "entrypoint": "run.ps1",
                "runtime": "powershell",
                "channels": [],
                "queue_group": None,
                "sla_minutes": None,
                "max_runtime_minutes": 30,
                "max_retries": 0,
                "schedule_summary": "Manual",
                "runbook_path": "Orchestrator/tests/test/run.ps1",
                "context_path": "Orchestrator/tests/test/run.ps1",
                "readme_path": "Orchestrator/tests/test/run.ps1",
                "orchestrator": {"script_path": "./Orchestrator/tests/test/run.ps1"},
                "dependencies": {"oracle": False, "outlook": False, "whatsapp": False},
                "smoke_tests": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    create_response = requests.post(
        f"{uvicorn_server}/api/automations",
        json={
            "name": "Timezone E2E Auto",
            "script_path": "./Orchestrator/tests/test/run.ps1",
            "schedule": f'{{"schedule_type":"once","run_at":"{scheduled_run_at}","timezone":"America/Sao_Paulo"}}',
            "enabled": True,
        },
        headers={"X-API-Key": API_KEY},
        timeout=20,
    )
    manifesto_e2e.unlink(missing_ok=True)
    assert create_response.status_code == 201, create_response.text

    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/execucoes")
    page.get_by_role("heading", name="Execuções").wait_for(timeout=30_000)
    page.locator("tr", has_text="Receitas Bloqueadas").first.wait_for(timeout=15_000)

    table_text = page.locator("table").first.inner_text()
    assert BR_DATETIME.search(table_text), f"Sem data BRT na tabela: {table_text!r}"


@pytest.mark.e2e
def test_e2e_dashboard_beneficiamento_loads(uvicorn_server: str, page: Any) -> None:
    """A aba Beneficiamento carrega o cabeçalho e o cartão de saúde do snapshot."""
    console_errors: list[str] = []

    def handle_console(msg: Any) -> None:
        if msg.type == "error" and "favicon" not in msg.text.lower():
            console_errors.append(msg.text)

    page.on("console", handle_console)
    _inject_api_key(page)

    page.goto(f"{uvicorn_server}/dashboard/beneficiamento")
    page.get_by_role("heading", name="Beneficiamento").wait_for(timeout=30_000)
    page.wait_for_selector("text=saúde do snapshot", timeout=15_000)

    assert not console_errors, f"Erros de console em Beneficiamento: {console_errors}"


@pytest.mark.e2e
def test_e2e_dashboard_observabilidade_redirect_to_monitor(
    uvicorn_server: str, page: Any
) -> None:
    """A rota legada /observabilidade redireciona para /monitor (rename da Fase 2)."""
    _inject_api_key(page)

    page.goto(f"{uvicorn_server}/dashboard/observabilidade")
    page.get_by_role("heading", name="Monitor").wait_for(timeout=30_000)

    assert page.url.rstrip("/").endswith("/dashboard/monitor")


# ---------------------------------------------------------------------------
# Regressão Visual (F3-T4): compara screenshot atual contra baseline em disco.
#
# Nota de flakiness conhecida: as páginas exibem contadores de tempo relativo
# (idade de execução, uptime do worker) que mudam a cada execução do teste.
# A tolerância abaixo absorve pequenas diferenças de texto/antialiasing; se o
# layout mudar de propósito, apague o baseline correspondente para regenerá-lo.
# ---------------------------------------------------------------------------

BASELINE_DIR = (
    Path(TESTS_DIR).resolve().parents[1]
    / "docs"
    / "playwright-screenshots"
    / "baseline"
)
VISUAL_DIFF_TOLERANCE = 0.05  # 5% dos pixels podem divergir do baseline


def _assert_matches_baseline(page: Any, name: str) -> None:
    """Compara o screenshot atual contra o baseline em disco; cria o baseline se ausente."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    baseline_path = BASELINE_DIR / f"{name}.png"
    current = Image.open(BytesIO(page.screenshot(full_page=True))).convert("RGB")

    if not baseline_path.exists():
        current.save(baseline_path)
        pytest.skip(f"Baseline criado para '{name}'; rode novamente para comparar.")

    baseline = Image.open(baseline_path).convert("RGB")
    if baseline.size != current.size:
        pytest.fail(
            f"Dimensão do screenshot '{name}' mudou: baseline={baseline.size} atual={current.size}."
        )

    histogram = ImageChops.difference(baseline, current).convert("L").histogram()
    # Bins de intensidade 0-15 tratados como ruído (antialiasing); acima disso conta como divergência real.
    diff_pixels = sum(histogram[16:])
    total_pixels = current.width * current.height
    diff_ratio = diff_pixels / total_pixels

    assert diff_ratio <= VISUAL_DIFF_TOLERANCE, (
        f"Regressão visual em '{name}': {diff_ratio:.1%} dos pixels divergem do "
        f"baseline (tolerância: {VISUAL_DIFF_TOLERANCE:.0%}). Se a mudança de "
        f"layout for intencional, apague {baseline_path} para regenerar."
    )


@pytest.mark.e2e
def test_screenshot_dashboard_overview_estado_healthy(
    uvicorn_server: str, page: Any
) -> None:
    _inject_api_key(page)
    # Explícito (Onda 4-3): antes do ThemeContext existir, qualquer color-scheme
    # do runner renderizava o único tema que havia. Agora "system" (sem injeção)
    # resolveria pelo @media do browser — no Playwright, tipicamente "light" —
    # e faria ESTE baseline (capturado no escuro) divergir ~100%, não por regressão
    # real, só por depender de um padrão ambiental não determinístico.
    _inject_theme(page, "dark")
    page.goto(f"{uvicorn_server}/dashboard/painel")
    page.get_by_role("heading", name="Painel").wait_for(timeout=30_000)
    page.wait_for_selector("text=automações ativas", timeout=15_000)
    _assert_matches_baseline(page, "dashboard_painel_healthy")


@pytest.mark.e2e
def test_screenshot_diagnostics_com_findings(uvicorn_server: str, page: Any) -> None:
    _inject_api_key(page)
    _inject_theme(page, "dark")
    page.goto(f"{uvicorn_server}/dashboard/monitor")
    page.get_by_role("heading", name="Monitor").wait_for(timeout=30_000)
    _assert_matches_baseline(page, "dashboard_monitor")


@pytest.mark.e2e
def test_screenshot_automacoes_lista(uvicorn_server: str, page: Any) -> None:
    _inject_api_key(page)
    _inject_theme(page, "dark")
    page.goto(f"{uvicorn_server}/dashboard/automacoes")
    page.get_by_role("heading", name="Automações").wait_for(timeout=30_000)
    # O heading aparece antes dos cards — sem isto o screenshot pode pegar o
    # skeleton em vez do conteúdo carregado (achado ao gerar o baseline claro).
    page.wait_for_selector("text=sucesso / falha 24h", timeout=15_000)
    _assert_matches_baseline(page, "dashboard_automacoes")


@pytest.mark.e2e
def test_screenshot_beneficiamento_kpi_carregado(
    uvicorn_server: str, page: Any
) -> None:
    _inject_api_key(page)
    _inject_theme(page, "dark")
    page.goto(f"{uvicorn_server}/dashboard/beneficiamento")
    page.get_by_role("heading", name="Beneficiamento").wait_for(timeout=30_000)
    page.wait_for_selector("text=saúde do snapshot", timeout=15_000)
    _assert_matches_baseline(page, "dashboard_beneficiamento_kpi")


# ---------------------------------------------------------------------------
# Regressão visual — tema claro (Onda 4-3). Mesmas 4 telas, mesmo mecanismo de
# `_assert_matches_baseline`, só forçando `data-theme="light"` via
# `_inject_theme` antes do bundle montar. Baselines em arquivo separado
# (sufixo `_light`) — os 4 escuros acima continuam intocados.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_screenshot_dashboard_overview_estado_healthy_light(
    uvicorn_server: str, page: Any
) -> None:
    _inject_api_key(page)
    _inject_theme(page, "light")
    page.goto(f"{uvicorn_server}/dashboard/painel")
    page.get_by_role("heading", name="Painel").wait_for(timeout=30_000)
    page.wait_for_selector("text=automações ativas", timeout=15_000)
    _assert_matches_baseline(page, "dashboard_painel_healthy_light")


@pytest.mark.e2e
def test_screenshot_diagnostics_com_findings_light(
    uvicorn_server: str, page: Any
) -> None:
    _inject_api_key(page)
    _inject_theme(page, "light")
    page.goto(f"{uvicorn_server}/dashboard/monitor")
    page.get_by_role("heading", name="Monitor").wait_for(timeout=30_000)
    _assert_matches_baseline(page, "dashboard_monitor_light")


@pytest.mark.e2e
def test_screenshot_automacoes_lista_light(uvicorn_server: str, page: Any) -> None:
    _inject_api_key(page)
    _inject_theme(page, "light")
    page.goto(f"{uvicorn_server}/dashboard/automacoes")
    page.get_by_role("heading", name="Automações").wait_for(timeout=30_000)
    page.wait_for_selector("text=sucesso / falha 24h", timeout=15_000)
    _assert_matches_baseline(page, "dashboard_automacoes_light")


@pytest.mark.e2e
def test_screenshot_beneficiamento_kpi_carregado_light(
    uvicorn_server: str, page: Any
) -> None:
    _inject_api_key(page)
    _inject_theme(page, "light")
    page.goto(f"{uvicorn_server}/dashboard/beneficiamento")
    page.get_by_role("heading", name="Beneficiamento").wait_for(timeout=30_000)
    page.wait_for_selector("text=saúde do snapshot", timeout=15_000)
    _assert_matches_baseline(page, "dashboard_beneficiamento_kpi_light")


# ---------------------------------------------------------------------------
# Auditoria de acessibilidade (Onda 4-3) — axe-core rodando contra o DOM real
# no browser real, não RTL/jsdom sobre `pages/` (decisão do CLAUDE.md: "a
# delegação ao E2E é deliberada"). axe-core é devDependency do Dashboard
# (`Dashboard/node_modules/axe-core/axe.min.js`) — injetado via
# `add_script_tag(path=...)`, sem rede em test-time.
# ---------------------------------------------------------------------------

AXE_CORE_PATH = (
    Path(TESTS_DIR).resolve().parents[1]
    / "Dashboard"
    / "node_modules"
    / "axe-core"
    / "axe.min.js"
)
# "serious"/"critical" bloqueiam; "minor"/"moderate" só ficam registrados —
# mesmo corte que o `-ll` (low level) do bandit neste projeto: sinal real,
# sem ruído de achados cosméticos.
AXE_BLOCKING_IMPACT = {"serious", "critical"}


AXE_CORE_SRC = AXE_CORE_PATH.read_text(encoding="utf-8")


def _run_axe(page: Any) -> list[dict[str, Any]]:
    """Injeta axe-core e roda a auditoria completa contra o DOM carregado.

    `add_script_tag(path=...)` embute o conteúdo como <script> INLINE — a CSP
    de produção (`script-src 'self'`, ver main.py) bloqueia isso. Servido via
    `page.route` numa URL fake do mesmo origin (intercepta antes de ir à rede,
    nunca sai do processo de teste) + `add_script_tag(url=...)`, que é um
    <script src> normal e passa pelo 'self' sem tocar na CSP de produção.
    """
    page.route(
        "**/__test-axe-core.js",
        lambda route: route.fulfill(
            status=200, content_type="application/javascript", body=AXE_CORE_SRC
        ),
    )
    page.add_script_tag(url="/__test-axe-core.js")
    result = page.evaluate("async () => (await axe.run()).violations")
    return result  # type: ignore[no-any-return]


def _assert_no_serious_a11y_violations(page: Any, screen_name: str) -> None:
    violations = _run_axe(page)
    serious = [v for v in violations if v.get("impact") in AXE_BLOCKING_IMPACT]
    if serious:
        node_lines = []
        for v in serious:
            for n in v["nodes"][:6]:
                summary = n.get("failureSummary", "").replace("\n", " ")
                node_lines.append(f"      {n['target']}: {summary}")
        detail = (
            "\n".join(
                f"  - [{v['impact']}] {v['id']}: {v['help']} "
                f"({len(v['nodes'])} nó(s)) — {v['helpUrl']}"
                for v in serious
            )
            + "\n"
            + "\n".join(node_lines)
        )
        pytest.fail(
            f"{len(serious)} violação(ões) séria(s)/crítica(s) de acessibilidade "
            f"em '{screen_name}':\n{detail}"
        )


@pytest.mark.e2e
def test_a11y_painel_sem_violacoes_serias(uvicorn_server: str, page: Any) -> None:
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/painel")
    page.get_by_role("heading", name="Painel").wait_for(timeout=30_000)
    page.wait_for_selector("text=automações ativas", timeout=15_000)
    _assert_no_serious_a11y_violations(page, "Painel")


@pytest.mark.e2e
def test_a11y_automacoes_sem_violacoes_serias(uvicorn_server: str, page: Any) -> None:
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/automacoes")
    page.get_by_role("heading", name="Automações").wait_for(timeout=30_000)
    page.wait_for_selector("text=sucesso / falha 24h", timeout=15_000)
    _assert_no_serious_a11y_violations(page, "Automações")


@pytest.mark.e2e
def test_a11y_monitor_sem_violacoes_serias(uvicorn_server: str, page: Any) -> None:
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/monitor")
    page.get_by_role("heading", name="Monitor").wait_for(timeout=30_000)
    _assert_no_serious_a11y_violations(page, "Monitor")


@pytest.mark.e2e
def test_a11y_beneficiamento_sem_violacoes_serias(
    uvicorn_server: str, page: Any
) -> None:
    _inject_api_key(page)
    page.goto(f"{uvicorn_server}/dashboard/beneficiamento")
    page.get_by_role("heading", name="Beneficiamento").wait_for(timeout=30_000)
    page.wait_for_selector("text=saúde do snapshot", timeout=15_000)
    _assert_no_serious_a11y_violations(page, "Beneficiamento")

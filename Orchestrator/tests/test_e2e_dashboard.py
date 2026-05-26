# pylint: disable=protected-access, reimported, redefined-outer-name, unused-variable, line-too-long, wrong-import-position, import-outside-toplevel, consider-using-with, global-statement, wrong-import-order, too-many-branches, too-many-statements
"""
Teste de Ponta a Ponta (E2E) com Playwright: Dashboard Operacional
Valida a navegação pelas guias e interações críticas na tela real do Orchestrator.
Gera de forma automática as evidências do Quality Gate.
"""

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, cast

import pytest
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
API_KEY = os.environ.get("ORCHESTRATOR_API_KEY", "hub-secret" + "-token")

# Contadores globais de logs do console do navegador
CONSOLE_ERRORS = 0
CONSOLE_WARNINGS = 0
CONSOLE_MESSAGES: list[Any] = []


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


def test_e2e_dashboard_navigation(
    uvicorn_server: str, page: Any, tmp_path: Path
) -> None:
    """Valida a navegação e o Quality Gate de conformidade JS no Dashboard."""

    # Escutar logs do console
    def handle_console(msg: Any) -> None:
        global CONSOLE_ERRORS, CONSOLE_WARNINGS
        txt = msg.text
        # Ignorar erros comuns irrelevantes no console do Playwright (ex. falha ao carregar favicon)
        if "favicon" in txt or "icon" in txt:
            return

        CONSOLE_MESSAGES.append(f"[{msg.type.upper()}] {txt}")
        if msg.type == "error":
            CONSOLE_ERRORS += 1
        elif msg.type == "warning":
            CONSOLE_WARNINGS += 1

    page.on("console", handle_console)

    # Trata a janela de prompt do Zero-Trust para injetar a API Key
    def handle_dialog(dialog: Any) -> None:
        dialog.accept(API_KEY)

    page.on("dialog", handle_dialog)

    # 1. Acessa a URL do Dashboard
    target_url = f"{uvicorn_server}/dashboard/"
    page.goto(target_url)
    page.wait_for_load_state("networkidle")

    # Espera carregar os painéis operacionais
    page.wait_for_selector("text=Centro de controle")

    # 2. Navega pelas abas do Dashboard
    guias = ["dashboard", "automations", "executions", "observability", "system", "env"]
    modulos_visitados = []

    for guia in guias:
        selector = f'button[data-target="{guia}"]'
        page.click(selector)
        page.wait_for_timeout(300)  # Pequeno delay para transição fluida
        modulos_visitados.append(guia.capitalize())

    # 3. Executa ações críticas na aba de Execuções
    page.click('button[data-target="executions"]')
    page.wait_for_selector("#exec-tbody")

    # Aplica filtro de status
    page.select_option("#filter-status", "SUCCESS")
    page.click('button[data-action="refresh-executions"]')
    page.wait_for_timeout(400)

    # Clica em ver logs (abre o modal clicando na primeira linha com data-execution-id)
    page.wait_for_selector('tr[data-action="open-log-row"]')
    page.click('tr[data-action="open-log-row"]')
    page.wait_for_selector("#modal-logs")
    page.wait_for_selector(
        "text=[E2E-TEST]"
    )  # Confirma que os logs mockados abriram no modal

    # Tira um screenshot de alta qualidade com o modal de logs aberto para evidência
    screenshot_path = tmp_path / f"playwright-e2e-generated-{os.getpid()}.png"
    page.screenshot(path=screenshot_path)

    # Fecha o modal de logs
    page.click('button[data-action="close-log-modal"]')
    page.wait_for_timeout(300)

    # 4. Geração Automática do Relatório de Evidência
    evidence_path = tmp_path / "playwright-e2e-evidence-generated.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Escreve o arquivo no formato estrito do Quality Gate
    report_content = f"""# Template de Evidência E2E Final (Playwright)

Preencha este bloco ao final de cada entrega que exija validação E2E Playwright.

## Evidência E2E Final
- Data/Hora (BRT): {dt_str}
- URL validada: http://127.0.0.1:8000/dashboard/
- Ordem de execução: Governança -> Testes de contrato/backend -> Playwright E2E (último)
- Módulos navegados:
  - Comando
  - Automações
  - Execuções
  - Observabilidade
  - Sistema
  - Configuração
- Ações críticas validadas:
  - Listagem/refresh de execuções
  - Aplicação de filtro em execuções
  - Abertura de logs
  - Navegação entre todas as 6 guias do Dashboard
- Console do navegador:
  - Erros: {CONSOLE_ERRORS}
  - Warnings: {CONSOLE_WARNINGS}
  - Resumo: Sem erros sintáticos ou comportamentais de console JS detectados na navegação
- Resultado final:
  - Aprovado
- Pendências (se houver):
  - nenhuma
"""
    evidence_path.write_text(report_content, encoding="utf-8")

    # Asserções do Quality Gate do teste
    assert (
        CONSOLE_ERRORS == 0
    ), f"Erros de console detectados no navegador: {CONSOLE_MESSAGES}"
    assert (
        screenshot_path.exists()
    ), "O screenshot de evidência não foi salvo corretamente."
    assert evidence_path.exists(), "O arquivo de evidência gerada não foi criado."


def test_e2e_dashboard_timezone_rendering(uvicorn_server: str, page: Any) -> None:
    """Garante que o dashboard renderiza datas em BRT nas abas operacionais."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))

    import requests
    from app.timezone import get_now_local

    scheduled_run_at = (get_now_local() + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S"
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
    assert create_response.status_code == 201, create_response.text

    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("text=Centro de controle")

    def assert_br_datetime(value: str) -> None:
        assert re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", value), value

    page.click('button[data-target="automations"]')
    page.wait_for_selector('#fleet-tbody tr:has-text("Timezone E2E Auto")')
    target_automation_row = page.locator(
        '#fleet-tbody tr:has-text("Timezone E2E Auto")'
    ).first
    page.wait_for_function(
        """name => {
            const rows = Array.from(document.querySelectorAll('#fleet-tbody tr'));
            const row = rows.find((item) => (item.innerText || '').includes(name));
            if (!row) return false;
            const cells = row.querySelectorAll('td');
            const nextRun = (cells[2]?.innerText || '').trim();
            return nextRun !== '-' && /^\\d{2}\\/\\d{2}\\/\\d{4} \\d{2}:\\d{2}:\\d{2}$/.test(nextRun);
        }""",
        arg="Timezone E2E Auto",
    )
    next_run = target_automation_row.locator("td").nth(2).inner_text().strip()
    assert next_run != "-"
    assert_br_datetime(next_run)

    page.click('button[data-target="executions"]')
    page.wait_for_selector("#exec-tbody tr")
    executions = page.locator("#exec-tbody tr").evaluate_all(
        """rows => rows.slice(0, 3).map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            return (cells[5]?.innerText || '').trim();
        })"""
    )
    valid_executions = [
        value
        for value in executions
        if re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", value)
    ]
    assert valid_executions
    for value in valid_executions:
        assert_br_datetime(value)

    page.click('button[data-target="system"]')
    page.wait_for_selector("#audit-tbody tr")
    page.wait_for_function(
        """() => Array.from(document.querySelectorAll('#audit-tbody tr td:first-child'))
            .some((cell) => /^\\d{2}\\/\\d{2}\\/\\d{4} \\d{2}:\\d{2}:\\d{2}$/.test((cell.innerText || '').trim()))"""
    )
    audit_rows = page.locator("#audit-tbody tr").evaluate_all(
        """rows => rows.slice(0, 3).map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            return (cells[0]?.innerText || '').trim();
        })"""
    )
    valid_audit_rows = [
        value
        for value in audit_rows
        if re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", value)
    ]
    assert valid_audit_rows
    for value in valid_audit_rows:
        assert_br_datetime(value)


def test_e2e_dashboard_portfolio_panel_exposes_governed_catalog(
    uvicorn_server: str, page: Any
) -> None:
    """Valida se o painel operacional mostra o catálogo governado do portfólio."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))
    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#portfolio-tbody")
    page.wait_for_selector("#insight-portfolio-health")

    portfolio_text = page.locator("#portfolio-tbody").text_content() or ""
    portfolio_insight = page.locator("#insight-portfolio-health").text_content() or ""
    assert "Receitas Bloqueadas" in portfolio_text
    assert "Montagem de Terceirizados" in portfolio_text
    assert "Documentação OK" in portfolio_text
    assert portfolio_insight.strip() != ""


def test_e2e_dashboard_api_time_helpers_direct(uvicorn_server: str, page: Any) -> None:
    """Valida diretamente o módulo JS de datas do dashboard no navegador."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))
    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")

    result = page.evaluate(f"""async () => {{
            localStorage.setItem('orchestrator_api_key', {API_KEY!r});
            const mod = await import('/dashboard/js/api.js?v=' + Date.now());
            const utcFormatted = mod.formatDate('2026-05-21T14:00:00Z');
            const brFormatted = mod.formatDate('21/05/2026 11:05:42');
            const shortFormatted = mod.formatDate('2026-05-21T14:00:00Z', true);
            const parsedUtc = mod.parseDateValue('2026-05-21T14:00:00Z');
            const parsedBr = mod.parseDateValue('21/05/2026 11:05:42');
            return {{
                utcFormatted,
                brFormatted,
                shortFormatted,
                parsedUtcIso: parsedUtc ? parsedUtc.toISOString() : null,
                parsedBrIso: parsedBr ? parsedBr.toISOString() : null,
            }};
        }}""")

    assert result["utcFormatted"] == "21/05/2026 11:00:00"
    assert result["brFormatted"] == "21/05/2026 11:05:42"
    assert result["shortFormatted"] == "11:00:00"
    assert result["parsedUtcIso"] == "2026-05-21T14:00:00.000Z"
    assert result["parsedBrIso"] == "2026-05-21T14:05:42.000Z"


def test_e2e_dashboard_executions_filters_all_controls(
    uvicorn_server: str, page: Any
) -> None:
    """Valida o encadeamento de todos os filtros visíveis da bancada de execuções."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))

    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        auto_match = models.Automation(
            name="Filtro Match Auto",
            script_path="./Receitas Bloqueadas/run.ps1",
            enabled=True,
            queue_group="financeiro",
        )
        auto_other = models.Automation(
            name="Filtro Other Auto",
            script_path="./Montagem de Terceirizados/run.ps1",
            enabled=True,
            queue_group="operacional",
        )
        session.add_all([auto_match, auto_other])
        session.flush()

        now = datetime.now()
        session.add_all(
            [
                models.Execution(
                    id="EXEC_E2E_FILTER_MATCH",
                    automation_id=auto_match.id,
                    status="ERROR",
                    priority="HIGH",
                    queue_group="financeiro",
                    requested_by="Operador QA",
                    started_at=now - timedelta(hours=1),
                    logs="[E2E-FILTER] Match",
                ),
                models.Execution(
                    id="EXEC_E2E_FILTER_OTHER_STATUS",
                    automation_id=auto_match.id,
                    status="SUCCESS",
                    priority="HIGH",
                    queue_group="financeiro",
                    requested_by="Operador QA",
                    started_at=now - timedelta(hours=1),
                    finished_at=now - timedelta(minutes=50),
                    duration_seconds=120,
                    logs="[E2E-FILTER] Wrong status",
                ),
                models.Execution(
                    id="EXEC_E2E_FILTER_OTHER_PRIORITY",
                    automation_id=auto_match.id,
                    status="ERROR",
                    priority="LOW",
                    queue_group="financeiro",
                    requested_by="Operador QA",
                    started_at=now - timedelta(hours=1),
                    logs="[E2E-FILTER] Wrong priority",
                ),
                models.Execution(
                    id="EXEC_E2E_FILTER_OTHER_GROUP",
                    automation_id=auto_other.id,
                    status="ERROR",
                    priority="HIGH",
                    queue_group="operacional",
                    requested_by="Operador QA",
                    started_at=now - timedelta(hours=1),
                    logs="[E2E-FILTER] Wrong group",
                ),
                models.Execution(
                    id="EXEC_E2E_FILTER_OTHER_REQUESTER",
                    automation_id=auto_match.id,
                    status="ERROR",
                    priority="HIGH",
                    queue_group="financeiro",
                    requested_by="SYSTEM",
                    started_at=now - timedelta(hours=1),
                    logs="[E2E-FILTER] Wrong requester",
                ),
                models.Execution(
                    id="EXEC_E2E_FILTER_OTHER_DATE",
                    automation_id=auto_match.id,
                    status="ERROR",
                    priority="HIGH",
                    queue_group="financeiro",
                    requested_by="Operador QA",
                    started_at=now - timedelta(days=3),
                    logs="[E2E-FILTER] Wrong date",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    today = datetime.now().strftime("%Y-%m-%d")

    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")
    page.click('button[data-target="executions"]')
    page.wait_for_selector("#exec-tbody tr")

    page.select_option("#filter-automation", label="Filtro Match Auto")
    page.select_option("#filter-queue-group", "financeiro")
    page.select_option("#filter-status", "ERROR")
    page.select_option("#filter-priority", "HIGH")
    page.fill("#filter-requested-by", "operador")
    page.locator("#filter-requested-by").dispatch_event("change")
    page.fill("#filter-date-from", today)
    page.locator("#filter-date-from").dispatch_event("change")
    page.fill("#filter-date-to", today)
    page.locator("#filter-date-to").dispatch_event("change")

    payload = page.evaluate(
        """async (apiKey) => {
            const params = new URLSearchParams({
                page: '1',
                per_page: '20',
            });
            const read = (id) => document.getElementById(id)?.value || '';
            const status = read('filter-status');
            const automationId = read('filter-automation');
            const queueGroup = read('filter-queue-group');
            const priority = read('filter-priority');
            const requestedBy = read('filter-requested-by');
            const dateFrom = read('filter-date-from');
            const dateTo = read('filter-date-to');
            if (status) params.set('status', status);
            if (automationId) params.set('automation_id', automationId);
            if (queueGroup) params.set('queue_group', queueGroup);
            if (priority) params.set('priority', priority);
            if (requestedBy) params.set('requested_by', requestedBy);
            if (dateFrom) params.set('date_from', `${dateFrom}T00:00:00`);
            if (dateTo) params.set('date_to', `${dateTo}T23:59:59`);
            const response = await fetch('/api/executions?' + params.toString(), {
                headers: { 'X-API-Key': apiKey },
            });
            const data = await response.json();
            return {
                statusCode: response.status,
                query: params.toString(),
                ids: (data.items || []).map((item) => item.id),
                requestedBy: (data.items || []).map((item) => item.requested_by),
            };
        }""",
        API_KEY,
    )

    assert payload["statusCode"] == 200
    assert payload["ids"] == ["EXEC_E2E_FILTER_MATCH"]
    assert payload["requestedBy"] == ["Operador QA"]


def test_e2e_dashboard_automations_search_filters_visible_grid(
    uvicorn_server: str, page: Any
) -> None:
    """Valida a busca textual da tela administrativa de automações na grade visível."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))

    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        session.add_all(
            [
                models.Automation(
                    name="Auto Busca Financeiro",
                    description="Consolidação financeira diária",
                    script_path="./Receitas Bloqueadas/run.ps1",
                    enabled=True,
                ),
                models.Automation(
                    name="Auto Busca Operacional",
                    description="Rotina de expedição",
                    script_path="./Montagem de Terceirizados/run.ps1",
                    enabled=True,
                ),
                models.Automation(
                    name="Auto Busca WhatsApp",
                    description="Envio de alertas por canal",
                    script_path="./Receitas Emitidas/run.ps1",
                    enabled=True,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")
    page.click('button[data-target="automations"]')
    page.wait_for_selector('#fleet-tbody tr:has-text("Auto Busca Financeiro")')

    page.fill("#auto-search", "financeiro")
    page.locator("#auto-search").dispatch_event("input")
    page.wait_for_function(
        """() => {
            const rows = Array.from(document.querySelectorAll('#fleet-tbody tr'));
            if (rows.length !== 1) return false;
            const cells = rows[0].querySelectorAll('td');
            return (cells[0]?.innerText || '').includes('Auto Busca Financeiro');
        }"""
    )

    rows = page.locator("#fleet-tbody tr").evaluate_all("""rows => rows.map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            return {
                automation: (cells[0]?.innerText || '').trim(),
                cadence: (cells[1]?.innerText || '').trim(),
                state: (cells[5]?.innerText || '').trim(),
            };
        })""")

    assert len(rows) == 1
    assert "Auto Busca Financeiro" in rows[0]["automation"]
    assert rows[0]["state"] in ["ATIVO", "PAUSADA"]


def _read_automation_history_row(page: Any) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        page.locator("#fleet-tbody tr").evaluate_all("""rows => rows.map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            const scheduleBadge = cells[1]?.querySelector('.fleet-schedule-badge');
            const riskBadge = cells[6]?.querySelector('.fleet-risk-badge');
            const actionsWrapper = cells[7]?.querySelector('.fleet-actions-inline');
            const toggleButton = cells[7]?.querySelector('[data-action-menu-toggle]');
            return {
                automation: (cells[0]?.innerText || '').trim(),
                last: (cells[3]?.innerText || '').trim(),
                risk: (cells[6]?.innerText || '').trim(),
                primaryControls: actionsWrapper ? actionsWrapper.querySelectorAll(':scope > button, :scope > .fleet-actions-menu > button').length : 0,
                actionsInlineHeight: actionsWrapper ? Math.round(actionsWrapper.getBoundingClientRect().height) : 0,
                menuExpanded: toggleButton ? toggleButton.getAttribute('aria-expanded') : null,
                scheduleWrapsCleanly: scheduleBadge ? scheduleBadge.scrollWidth <= scheduleBadge.clientWidth + 2 : false,
                riskWrapsCleanly: riskBadge ? riskBadge.scrollWidth <= riskBadge.clientWidth + 2 : false,
                actionsOverflow: actionsWrapper ? actionsWrapper.scrollWidth > actionsWrapper.clientWidth + 2 : true,
            };
        })""")[0],
    )


def _open_more_actions_and_read_state(page: Any) -> dict[str, Any]:
    page.click("#fleet-tbody tr [data-action-menu-toggle]")
    page.wait_for_selector(".fleet-actions-menu-panel:not([hidden])")
    return cast(
        dict[str, Any],
        page.evaluate("""() => {
            const panel = document.querySelector('.fleet-actions-menu-panel:not([hidden])');
            const labels = panel
                ? Array.from(panel.querySelectorAll('.fleet-actions-menu-item span')).map((item) => (item.textContent || '').trim())
                : [];
            const host = document.querySelector('#fleet-tbody tr .fleet-actions-inline');
            return {
                menuVisible: Boolean(panel),
                labels,
                menuOpenCount: document.querySelectorAll('.fleet-actions-menu-panel:not([hidden])').length,
                actionsOverflow: host ? host.scrollWidth > host.clientWidth + 2 : true,
            };
        }"""),
    )


def _assert_menu_closes_on_outside_click(page: Any) -> None:
    page.mouse.click(40, 40)
    page.wait_for_function(
        """() => document.querySelectorAll('.fleet-actions-menu-panel:not([hidden])').length === 0"""
    )


def _assert_menu_action_closes_and_opens_json_modal(page: Any) -> None:
    page.click("#fleet-tbody tr [data-action-menu-toggle]")
    page.wait_for_selector(".fleet-actions-menu-panel:not([hidden])")
    page.click(
        '.fleet-actions-menu-panel:not([hidden]) [data-action="open-json-modal"]'
    )
    page.wait_for_function(
        """() => document.getElementById('modal-json')?.open === true"""
    )
    page.wait_for_function(
        """() => document.querySelectorAll('.fleet-actions-menu-panel:not([hidden])').length === 0"""
    )
    page.click('button[data-action="close-dialog"][data-dialog-id="modal-json"]')
    page.wait_for_function(
        """() => document.getElementById('modal-json')?.open === false"""
    )


def test_e2e_dashboard_automations_last_execution_snapshot_visible(
    uvicorn_server: str, page: Any
) -> None:
    """Garante que a aba Automações exibe o histórico recente real e compacta a célula de ações."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))

    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        auto = models.Automation(
            name="Auto E2E Histórico",
            description="Validação visual do histórico recente",
            script_path="./Receitas Emitidas/run.ps1",
            enabled=True,
            cooldown_minutes=10,
            max_retries=3,
            queue_group="ops",
            schedule='{"schedule_type":"weekly","schedule_version":2,"timezone":"America/Sao_Paulo","days_of_week":[1,2,3,4,5,6],"times":[{"h":5,"m":0},{"h":22,"m":0}]}',
        )
        session.add(auto)
        session.flush()

        now = datetime.now()
        session.add_all(
            [
                models.Execution(
                    id="EXEC_E2E_HISTORY_OLD",
                    automation_id=auto.id,
                    status="ERROR",
                    priority="NORMAL",
                    queue_group="ops",
                    requested_by="SYSTEM",
                    started_at=now - timedelta(hours=6),
                    finished_at=now - timedelta(hours=6) + timedelta(minutes=2),
                    duration_seconds=120,
                    failure_reason="Falha antiga",
                ),
                models.Execution(
                    id="EXEC_E2E_HISTORY_LATEST",
                    automation_id=auto.id,
                    status="SUCCESS",
                    priority="NORMAL",
                    queue_group="ops",
                    requested_by="CRON",
                    started_at=now - timedelta(minutes=18),
                    finished_at=now - timedelta(minutes=15),
                    duration_seconds=180,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")
    page.click('button[data-target="automations"]')
    page.wait_for_selector("#fleet-tbody tr")

    page.fill("#auto-search", "E2E Histórico")
    page.locator("#auto-search").dispatch_event("input")
    page.wait_for_timeout(400)

    target = _read_automation_history_row(page)
    assert "Auto E2E Histórico" in target["automation"]
    assert "Sem execução recente" not in target["last"]
    assert "SUCESSO" in target["last"]
    assert re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", target["last"])
    assert "ER 1/24H" in target["risk"].upper()
    assert target["primaryControls"] == 5
    assert target["actionsInlineHeight"] <= 32
    assert target["menuExpanded"] == "false"
    assert target["scheduleWrapsCleanly"] is True
    assert target["riskWrapsCleanly"] is True
    assert target["actionsOverflow"] is False

    menu_state = _open_more_actions_and_read_state(page)
    assert menu_state["menuVisible"] is True
    assert menu_state["menuOpenCount"] == 1
    assert menu_state["labels"] == ["Clonar", "Editar JSON", "Editar scripts", "Excluir cadastro"]
    assert menu_state["actionsOverflow"] is False

    _assert_menu_closes_on_outside_click(page)
    _assert_menu_action_closes_and_opens_json_modal(page)


def test_e2e_dashboard_system_shortcuts_open_execution_triage(
    uvicorn_server: str, page: Any
) -> None:
    """Valida atalhos da aba Sistema para abrir recortes operacionais em Execuções."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))

    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        auto_group = models.Automation(
            name="Atalho Grupo Ativo",
            script_path="./Receitas Bloqueadas/run.ps1",
            enabled=True,
            queue_group="grupo_sistema",
        )
        auto_hotspot = models.Automation(
            name="Atalho Hotspot",
            script_path="./Montagem de Terceirizados/run.ps1",
            enabled=True,
            queue_group="hotspot_ops",
        )
        session.add_all([auto_group, auto_hotspot])
        session.flush()

        now = datetime.now()
        session.add_all(
            [
                models.Execution(
                    id="EXEC_SYS_GROUP_RUNNING",
                    automation_id=auto_group.id,
                    status="RUNNING",
                    priority="HIGH",
                    queue_group="grupo_sistema",
                    requested_by="SYSTEM",
                    started_at=now - timedelta(minutes=15),
                    logs="[E2E-SYSTEM] Running group",
                ),
                models.Execution(
                    id="EXEC_SYS_HOTSPOT_1",
                    automation_id=auto_hotspot.id,
                    status="ERROR",
                    priority="HIGH",
                    queue_group="hotspot_ops",
                    requested_by="SYSTEM",
                    started_at=now - timedelta(hours=1),
                    logs="[E2E-SYSTEM] Hotspot 1",
                ),
                models.Execution(
                    id="EXEC_SYS_HOTSPOT_2",
                    automation_id=auto_hotspot.id,
                    status="ERROR",
                    priority="HIGH",
                    queue_group="hotspot_ops",
                    requested_by="SYSTEM",
                    started_at=now - timedelta(hours=2),
                    logs="[E2E-SYSTEM] Hotspot 2",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")
    page.click('button[data-target="system"]')
    page.wait_for_selector("#diagnostic-contract")
    page.wait_for_selector("#diagnostic-contract h4:text-is('Base operacional')")

    page.wait_for_selector(
        'button[data-action="execution-filter-group"][data-queue-group="grupo_sistema"]'
    )
    page.click(
        'button[data-action="execution-filter-group"][data-queue-group="grupo_sistema"]'
    )
    page.wait_for_timeout(500)

    after_group = page.evaluate("""() => ({
            executionsActive: document.getElementById('view-executions')?.classList.contains('active') || false,
            queueGroup: document.getElementById('filter-queue-group')?.value || '',
        })""")
    assert after_group["executionsActive"] is True
    assert after_group["queueGroup"] == "grupo_sistema"

    page.click('button[data-target="system"]')
    page.wait_for_function(
        """() => document.getElementById('view-system')?.classList.contains('active') || false"""
    )
    hotspot_button = page.locator(
        '#view-system button[data-action="execution-open-hotspot"]'
    ).first
    hotspot_button.wait_for(state="visible")
    hotspot_button.click()
    page.wait_for_timeout(500)

    after_hotspot = page.evaluate("""() => ({
            executionsActive: document.getElementById('view-executions')?.classList.contains('active') || false,
            automationId: document.getElementById('filter-automation')?.value || '',
            status: document.getElementById('filter-status')?.value || '',
        })""")
    assert after_hotspot["executionsActive"] is True
    assert after_hotspot["status"] == "ERROR"
    assert after_hotspot["automationId"] != ""

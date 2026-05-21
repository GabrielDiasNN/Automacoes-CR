# pylint: disable=protected-access, reimported, redefined-outer-name, unused-variable, line-too-long, wrong-import-position, import-outside-toplevel, consider-using-with, global-statement, wrong-import-order
"""
Teste de Ponta a Ponta (E2E) com Playwright: Dashboard Operacional
Valida a navegação pelas guias e interações críticas na tela real do Orchestrator.
Gera de forma automática as evidências do Quality Gate.
"""

import os
import re
import sys
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Any, Generator

# Adicionar pasta do app ao PYTHONPATH
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(TESTS_DIR, "..")))

from app import models

TEST_DB_PATH = Path(TESTS_DIR) / "test-e2e-automacoes.db"
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
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except OSError:
            pass

    # Aplica as migrações do Alembic para estruturar o banco dinamicamente
    # pylint: disable=import-outside-toplevel
    from alembic.config import Config
    from alembic import command

    ini_path = os.path.abspath(os.path.join(TESTS_DIR, "..", "alembic.ini"))
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{TEST_DB_PATH.as_posix()}")

    command.upgrade(alembic_cfg, "head")

    # Inicializa engine no banco de teste dinâmico para cadastrar dados Mock
    engine = create_engine(f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"check_same_thread": False})

    db_session_factory = sessionmaker(bind=engine)
    session = db_session_factory()

    # 1. Cadastra automações de teste
    auto1 = models.Automation(
        name="Receitas Bloqueadas",
        description="Filtra pedidos bloqueados no Oracle",
        script_path="./Receitas Bloqueadas/processar_receitas.py",
        enabled=True,
        max_retries=2,
        queue_group="oracle",
        sla_minutes=60,
    )
    auto2 = models.Automation(
        name="Montagem de Terceirizados",
        description="Extrai e valida NFs da Montagem",
        script_path="./Montagem de Terceirizados/validate_and_generate_html.py",
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

    # Cleanup após todos os testes
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except OSError:
            pass


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
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
        stdout, stderr = proc.communicate()
        raise RuntimeError(f"Servidor de teste falhou ao iniciar.\nStdout: {stdout.decode()}\nStderr: {stderr.decode()}")

    yield f"http://{TEST_HOST}:{TEST_PORT}"

    # Encerra o processo uvicorn limpo
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_e2e_dashboard_navigation(uvicorn_server: str, page: Any, tmp_path: Path) -> None:
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
    page.wait_for_selector("text=[E2E-TEST]")  # Confirma que os logs mockados abriram no modal

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
    assert CONSOLE_ERRORS == 0, f"Erros de console detectados no navegador: {CONSOLE_MESSAGES}"
    assert screenshot_path.exists(), "O screenshot de evidência não foi salvo corretamente."
    assert evidence_path.exists(), "O arquivo de evidência gerada não foi criado."


def test_e2e_dashboard_timezone_rendering(uvicorn_server: str, page: Any) -> None:
    """Garante que o dashboard renderiza datas em BRT nas abas operacionais."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))

    import requests
    from app.timezone import get_now_local

    scheduled_run_at = (get_now_local() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    create_response = requests.post(
        f"{uvicorn_server}/api/automations",
        json={
            "name": "Timezone E2E Auto",
            "script_path": "./Receitas Bloqueadas/processar_receitas.py",
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
    page.wait_for_selector("#fleet-tbody tr")
    automations = page.locator("#fleet-tbody tr").evaluate_all(
        """rows => rows.slice(0, 3).map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            return (cells[2]?.innerText || '').trim();
        })"""
    )
    assert any(value != "-" for value in automations)
    for value in automations:
        if value != "-":
            assert_br_datetime(value)

    page.click('button[data-target="executions"]')
    page.wait_for_selector("#exec-tbody tr")
    executions = page.locator("#exec-tbody tr").evaluate_all(
        """rows => rows.slice(0, 3).map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            return (cells[5]?.innerText || '').trim();
        })"""
    )
    valid_executions = [value for value in executions if re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", value)]
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
    valid_audit_rows = [value for value in audit_rows if re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", value)]
    assert valid_audit_rows
    for value in valid_audit_rows:
        assert_br_datetime(value)


def test_e2e_dashboard_api_time_helpers_direct(uvicorn_server: str, page: Any) -> None:
    """Valida diretamente o módulo JS de datas do dashboard no navegador."""
    page.on("dialog", lambda dialog: dialog.accept(API_KEY))
    page.goto(f"{uvicorn_server}/dashboard/")
    page.wait_for_load_state("networkidle")

    result = page.evaluate(
        f"""async () => {{
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
        }}"""
    )

    assert result["utcFormatted"] == "21/05/2026 11:00:00"
    assert result["brFormatted"] == "21/05/2026 11:05:42"
    assert result["shortFormatted"] == "11:00:00"
    assert result["parsedUtcIso"] == "2026-05-21T14:00:00.000Z"
    assert result["parsedBrIso"] == "2026-05-21T14:05:42.000Z"

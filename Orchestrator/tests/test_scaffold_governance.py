"""Validação do scaffold governado de novas automações."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("pwsh") is None,
    reason=(
        "Exercita Tools/New-Automation.ps1 via PowerShell real (subprocess "
        "'pwsh'); em ambiente sem o binário pwsh no PATH o teste não tem como "
        "rodar — não é uma falha do scaffold, é ausência da ferramenta."
    ),
)


def _copiar_fontes_scaffold(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for relative in ["_Template", "docs/templates", "Tools/New-Automation.ps1"]:
        source = repo_root / relative
        target = tmp_path / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _executar_scaffold(
    tmp_path: Path, args: list[str], *, ps_bin: str = "pwsh"
) -> subprocess.CompletedProcess[str]:
    _copiar_fontes_scaffold(tmp_path)
    return subprocess.run(
        [
            ps_bin,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "Tools" / "New-Automation.ps1"),
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_new_automation_scaffold_generates_governed_manifest_and_smoke(
    tmp_path: Path,
) -> None:
    result = _executar_scaffold(
        tmp_path,
        [
            "-Name",
            "Auto Scaffold Governado",
            "-BasePath",
            str(tmp_path),
            "-OwnerArea",
            "Operação Fiscal",
            "-Criticality",
            "high",
            "-QueueGroup",
            "oracle",
            "-SlaMinutes",
            "180",
            "-WithOracle",
        ],
    )

    assert "Scaffold concluido" in result.stdout

    automation_dir = tmp_path / "Auto Scaffold Governado"
    manifest = json.loads(
        (automation_dir / "automation.manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["owner_area"] == "Operação Fiscal"
    assert manifest["criticality"] == "high"
    assert manifest["queue_group"] == "oracle"
    assert manifest["sla_minutes"] == 180
    assert manifest["runtime"] == "python"
    assert manifest["dependencies"]["oracle"] is True
    assert manifest["smoke_tests"] == [
        "Orchestrator/tests/test_auto-scaffold-governado.py"
    ]

    smoke_test = tmp_path / "Orchestrator" / "tests" / "test_auto-scaffold-governado.py"
    assert smoke_test.exists()
    smoke_content = smoke_test.read_text(encoding="utf-8")
    assert (
        "def test_auto_scaffold_governado_scaffold_contract_files_exist()"
        in smoke_content
    )
    assert 'automation_dir = root / "Auto Scaffold Governado"' in smoke_content
    assert "TEMPLATE_RUNNER" not in smoke_content
    assert (
        'assert (automation_dir / "run_auto_scaffold_governado.py").exists()'
        in smoke_content
    )

    _assert_runner_e_shim_gerados(automation_dir)


def _assert_runner_e_shim_gerados(automation_dir: Path) -> None:
    """Automacao nova nasce no runner Python: o shim aponta para ele e nenhum
    arquivo gerado carrega placeholder do template."""
    runner = automation_dir / "run_auto_scaffold_governado.py"
    assert runner.exists(), "scaffold deve gerar o runner Python"
    runner_content = runner.read_text(encoding="utf-8")
    assert "TEMPLATE_SLUG" not in runner_content
    assert "TEMPLATE_RUNNER" not in runner_content
    assert 'AUTOMACAO: Final[str] = "Auto Scaffold Governado"' in runner_content
    assert 'SLUG_LOG: Final[str] = "auto-scaffold-governado"' in runner_content
    assert "RETENCAO_LOG_DIAS: Final[int] = 15" in runner_content
    assert "hr.rotate_log(ctx.log_path" in runner_content
    compile(runner_content, str(runner), "exec")

    readme_content = (automation_dir / "README.md").read_text(encoding="utf-8")
    context_content = (automation_dir / "CONTEXT.md").read_text(encoding="utf-8")
    assert "TEMPLATE_RUNNER" not in readme_content
    assert "run_<id>.py" not in readme_content
    assert "run_auto_scaffold_governado.py" in readme_content
    assert "TEMPLATE_RUNNER" not in context_content
    assert "run_<id>.py" not in context_content
    assert "run_auto_scaffold_governado.py" in context_content

    run_ps1_bytes = (automation_dir / "run.ps1").read_bytes()
    assert run_ps1_bytes.startswith(
        b"\xef\xbb\xbf"
    ), "run.ps1 gerado deve ter UTF-8 BOM"
    shim = run_ps1_bytes.decode("utf-8-sig")
    assert '"run_auto_scaffold_governado.py"' in shim
    assert "TEMPLATE_RUNNER" not in shim
    assert "Invoke-HubPythonRunner" in shim
    assert "exit $exitCode" in shim
    assert "Enter-AutomationLock" not in shim


def test_new_automation_with_whatsapp_gera_run_bat_com_config_path(
    tmp_path: Path,
) -> None:
    _executar_scaffold(
        tmp_path,
        [
            "-Name",
            "Auto WhatsApp Scaffold",
            "-BasePath",
            str(tmp_path),
            "-OwnerArea",
            "PCP",
            "-WithWhatsApp",
        ],
    )

    run_bat = (tmp_path / "Auto WhatsApp Scaffold" / "RunWhatsApp.bat").read_text(
        encoding="utf-8"
    )
    assert '-ConfigPath "%~dp0whatsapp-config.json"' in run_bat
    assert "-BaseDir" not in run_bat


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="Exercita compatibilidade de encoding no Windows PowerShell 5.1.",
)
def test_new_automation_ps51_substitui_placeholders_acentuados_sem_mojibake(
    tmp_path: Path,
) -> None:
    _executar_scaffold(
        tmp_path,
        [
            "-Name",
            "Auto PS51 Teste",
            "-BasePath",
            str(tmp_path),
            "-OwnerArea",
            "PCP",
        ],
        ps_bin="powershell.exe",
    )

    automation_dir = tmp_path / "Auto PS51 Teste"
    readme = (automation_dir / "README.md").read_text(encoding="utf-8")
    runbook = (tmp_path / "docs" / "runbooks" / "auto-ps51-teste-runbook.md").read_text(
        encoding="utf-8"
    )
    assert "[Nome da Automação]" not in readme
    assert "[Nome da Automação]" not in runbook
    assert "Auto PS51 Teste" in readme
    assert "Auto PS51 Teste" in runbook
    assert "Esta automação usa o fluxo atual do Hub" in readme
    assert "Ã" not in readme and "Ã" not in runbook

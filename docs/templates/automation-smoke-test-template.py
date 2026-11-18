# Residual: TEMPLATE_TEST_ID e o nome do arquivo são contrato com Tools/New-Automation.ps1 (fora desta partição).
# pylint: disable=invalid-name
"""Smoke mínimo gerado pelo scaffold da automação."""

from pathlib import Path


def test_TEMPLATE_TEST_ID_scaffold_contract_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    automation_dir = root / "[Nome da Automação]"

    assert (automation_dir / "run.ps1").exists()
    assert (automation_dir / "TEMPLATE_RUNNER").exists()
    assert (automation_dir / "automation.manifest.json").exists()
    assert (automation_dir / "README.md").exists()
    assert (automation_dir / "CONTEXT.md").exists()
    assert (root / "docs" / "runbooks" / "TEMPLATE_SLUG-runbook.md").exists()

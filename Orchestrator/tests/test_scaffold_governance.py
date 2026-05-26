# pylint: disable=all
# mypy: ignore-errors
"""Validação do scaffold governado de novas automações."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_new_automation_scaffold_generates_governed_manifest_and_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]

    for relative in [
        "_Template",
        "docs/templates",
        "Tools/New-Automation.ps1",
    ]:
        source = repo_root / relative
        target = tmp_path / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "Tools" / "New-Automation.ps1"),
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
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Scaffold concluido" in result.stdout

    automation_dir = tmp_path / "Auto Scaffold Governado"
    manifest = json.loads((automation_dir / "automation.manifest.json").read_text(encoding="utf-8"))

    assert manifest["owner_area"] == "Operação Fiscal"
    assert manifest["criticality"] == "high"
    assert manifest["queue_group"] == "oracle"
    assert manifest["sla_minutes"] == 180
    assert manifest["dependencies"]["oracle"] is True
    assert manifest["smoke_tests"] == ["Orchestrator/tests/test_auto-scaffold-governado.py"]

    smoke_test = tmp_path / "Orchestrator" / "tests" / "test_auto-scaffold-governado.py"
    assert smoke_test.exists()
    smoke_content = smoke_test.read_text(encoding="utf-8")
    assert "def test_auto_scaffold_governado_scaffold_contract_files_exist()" in smoke_content
    assert 'automation_dir = root / "Auto Scaffold Governado"' in smoke_content

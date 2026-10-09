"""
Testes focados nas operações de Web IDE de Automações (Scripts e Configs).
"""

import json
from pathlib import Path
from typing import Any

import app.routers.automation_config as config_router
import app.routers.automation_ide as ide_router
import app.routers.automations as auto_router
import pytest
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient


def _patch_project_root(monkeypatch: pytest.MonkeyPatch, root: str) -> None:
    """Aponta o PROJECT_ROOT dos três routers de automação para o dir de teste.

    Desde a extração de services/managed_file_access.py, os routers de config e
    IDE resolvem o diretório da automação com o PROJECT_ROOT do próprio módulo;
    o de automations segue sendo usado na validação de script_path na criação.
    """
    for module in (auto_router, config_router, ide_router):
        monkeypatch.setattr(module, "PROJECT_ROOT", root)


def test_update_automation_config_creates_backup(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    script_path = bot_dir / "run.ps1"
    config_path = bot_dir / "config.json"
    script_path.write_text("Write-Host 'ok'", encoding="utf-8")
    config_path.write_text('{"old": true}', encoding="utf-8")

    _patch_project_root(monkeypatch, str(tmp_path))
    client.post(
        "/api/automations",
        json={"name": "Config Backup", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.put(
        "/api/automations/1/configs/config.json",
        json={"content": '{"new": true}'},
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    backup_relpath = res.json()["backup"]
    backup_path = bot_dir / backup_relpath
    assert backup_path.exists()
    assert json.loads(backup_path.read_text(encoding="utf-8")) == {"old": True}
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"new": True}


def test_update_automation_script_creates_backup_and_preserves_ps_bom(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    script_path = bot_dir / "run.ps1"
    script_path.write_text("Write-Host 'old'", encoding="utf-8-sig")

    _patch_project_root(monkeypatch, str(tmp_path))
    client.post(
        "/api/automations",
        json={"name": "Script Backup", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.put(
        "/api/automations/1/scripts/run.ps1",
        json={"content": "Write-Host 'new'"},
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    backup_path = bot_dir / res.json()["backup"]
    assert backup_path.exists()
    assert "old" in backup_path.read_text(encoding="utf-8-sig")
    assert script_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "new" in script_path.read_text(encoding="utf-8-sig")


def test_update_automation_script_rejects_path_escape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    (bot_dir / "run.ps1").write_text("Write-Host 'ok'", encoding="utf-8")

    _patch_project_root(monkeypatch, str(tmp_path))
    client.post(
        "/api/automations",
        json={"name": "Script Escape", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.put(
        "/api/automations/1/scripts/..%2Frun.ps1",
        json={"content": "bad"},
        headers=AUTH_HEADERS,
    )

    assert res.status_code in (400, 404)


def test_list_scripts_logs_and_skips_unreadable_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    (bot_dir / "run.ps1").write_text("Write-Host 'ok'", encoding="utf-8")
    (bot_dir / "trancado.py").write_text("print('x')", encoding="utf-8")

    abrir_original = open

    def abrir_com_falha(file: Any, *args: Any, **kwargs: Any) -> Any:
        if Path(str(file)).name == "trancado.py":
            raise OSError(f"Permission denied: {file}")
        return abrir_original(file, *args, **kwargs)

    _patch_project_root(monkeypatch, str(tmp_path))
    # `open` é resolvido como global do módulo antes do builtin: o patch atinge só o router.
    monkeypatch.setattr(ide_router, "open", abrir_com_falha, raising=False)
    client.post(
        "/api/automations",
        json={"name": "Scripts Ilegivel", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    with caplog.at_level("WARNING", logger="orchestrator"):
        res = client.get("/api/automations/1/scripts", headers=AUTH_HEADERS)

    assert res.status_code == 200
    assert [item["filename"] for item in res.json()] == ["run.ps1"]

    avisos = [
        r.getMessage()
        for r in caplog.records
        if r.name == "orchestrator" and r.levelname == "WARNING"
    ]
    assert any("trancado.py" in aviso and "OSError" in aviso for aviso in avisos)
    # Nenhum aviso pode carregar o caminho absoluto do diretório de teste.
    assert all(str(tmp_path) not in aviso for aviso in avisos)

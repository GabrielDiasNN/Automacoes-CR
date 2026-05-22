# pylint: disable=all
# mypy: ignore-errors
"""
Testes focados nas operações de Web IDE de Automações (Scripts e Configs).
"""

import json
import pytest
from conftest import AUTH_HEADERS


def test_update_automation_config_creates_backup(client, monkeypatch, tmp_path):
    import app.routers.automations as auto_router

    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    script_path = bot_dir / "run.ps1"
    config_path = bot_dir / "config.json"
    script_path.write_text("Write-Host 'ok'", encoding="utf-8")
    config_path.write_text('{"old": true}', encoding="utf-8")

    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))
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
    client,
    monkeypatch,
    tmp_path,
):
    import app.routers.automations as auto_router

    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    script_path = bot_dir / "run.ps1"
    script_path.write_text("Write-Host 'old'", encoding="utf-8-sig")

    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))
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


def test_update_automation_script_rejects_path_escape(client, monkeypatch, tmp_path):
    import app.routers.automations as auto_router

    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    (bot_dir / "run.ps1").write_text("Write-Host 'ok'", encoding="utf-8")

    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))
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

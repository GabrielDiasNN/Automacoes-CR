"""Smoke tests para OBs Paradas Fase (OBP-04)."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
AUTOMATION_DIR = ROOT / "OBs Paradas Fase"


def test_manifest_valido() -> None:
    manifest_path = AUTOMATION_DIR / "automation.manifest.json"
    assert manifest_path.exists(), "automation.manifest.json ausente"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == "OBP-04"
    assert manifest["runtime"] == "powershell"
    assert "whatsapp" in manifest["channels"]


def test_entrypoint_existe() -> None:
    assert (AUTOMATION_DIR / "run.ps1").exists()


def test_scripts_python_existem() -> None:
    assert (AUTOMATION_DIR / "extract_obs.py").exists()
    assert (AUTOMATION_DIR / "generate_phase_cards.py").exists()


def test_whatsapp_config_valido() -> None:
    cfg_path = AUTOMATION_DIR / "whatsapp-config.json"
    assert cfg_path.exists(), "whatsapp-config.json ausente"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["auth"]["clientId"] == "hub-global"
    assert cfg["target"]["type"] == "group"
    assert "@g.us" in cfg["target"]["contactId"]


def test_docs_existem() -> None:
    assert (AUTOMATION_DIR / "README.md").exists()
    assert (AUTOMATION_DIR / "CONTEXT.md").exists()

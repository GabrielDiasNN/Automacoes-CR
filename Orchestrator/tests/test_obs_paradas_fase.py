"""Smoke tests para OBs Paradas Fase (OBP-04)."""
import json
import re
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
    assert re.match(r"^\d+@g\.us$", cfg["target"]["contactId"]), (
        f"contactId inválido: {cfg['target']['contactId']!r} — esperado formato <digitos>@g.us"
    )


def test_docs_existem() -> None:
    assert (AUTOMATION_DIR / "README.md").exists()
    assert (AUTOMATION_DIR / "CONTEXT.md").exists()


def test_config_json_valido() -> None:
    cfg_path = AUTOMATION_DIR / "config.json"
    assert cfg_path.exists(), "config.json ausente"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "threshold_por_fase" in cfg, "config.json deve conter 'threshold_por_fase'"
    assert isinstance(cfg["threshold_por_fase"], dict), "'threshold_por_fase' deve ser um objeto"
    assert len(cfg["threshold_por_fase"]) > 0, "'threshold_por_fase' não pode ser vazio"
    sql_path = AUTOMATION_DIR / "SQL-ObsParadasFase.sql"
    assert sql_path.exists(), "SQL-ObsParadasFase.sql ausente"


def test_sql_nao_vazio() -> None:
    sql_path = AUTOMATION_DIR / "SQL-ObsParadasFase.sql"
    assert sql_path.exists(), "SQL-ObsParadasFase.sql ausente"
    content = sql_path.read_text(encoding="utf-8").strip()
    assert len(content) > 0, "SQL-ObsParadasFase.sql está vazio"
    assert "SELECT" in content.upper(), "SQL-ObsParadasFase.sql não contém SELECT"

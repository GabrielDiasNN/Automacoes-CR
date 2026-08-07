"""Consistência estrutural dos automation.manifest.json reais das 5 automações.

Regressão do achado #16 (revisão de design): OBs Fluxo Sem Tingimento tinha
uma chave `script_path` solta na raiz do manifesto, nunca lida pelo preflight
(que só lê `orchestrator.script_path`) e por isso livre para divergir do
caminho real sem nenhuma validação notando.
"""

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUTOMATION_DIRS = [
    "Receitas Bloqueadas",
    "Receitas Emitidas",
    "Montagem de Terceirizados",
    "OBs Paradas Fase",
    "OBs Fluxo Sem Tingimento",
]


@pytest.mark.parametrize("automation_dir", _AUTOMATION_DIRS)
def test_manifesto_nao_tem_script_path_solto_na_raiz(automation_dir: str) -> None:
    manifest_path = _REPO_ROOT / automation_dir / "automation.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "script_path" not in manifest, (
        f"{automation_dir}: script_path na raiz do manifesto nunca é lido pelo "
        "preflight (só orchestrator.script_path é validado) — pode divergir "
        "silenciosamente do caminho real."
    )
    assert "script_path" in manifest["orchestrator"]

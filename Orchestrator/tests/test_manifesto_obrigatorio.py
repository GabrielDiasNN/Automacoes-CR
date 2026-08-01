"""Manifesto ausente bloqueia o cadastro (decisão de 31/07/2026).

Antes, a ausência de `automation.manifest.json` devolvia `attention`, e
`is_valid = status != "incident"` deixava passar: a automação era persistida
sem manifesto, sem docs obrigatórias e sem verificação de `whatsapp-config.json`.
Como `_manifest_field_mismatches` só roda quando o manifesto EXISTE, a forma
mais fácil de escapar de toda a governança de manifesto era não ter um.

Estes testes falam com o preflight diretamente, sem o wrapper `com_manifesto`
da conftest — é aqui que o bloqueio precisa ser verificado de verdade.
"""

import os
from pathlib import Path

import app.routers.automations as auto_router
import pytest
from app.services.automation_preflight import build_automation_preflight
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient


def _pasta_sem_manifesto(tmp_path: Path) -> str:
    pasta = tmp_path / "Sem Manifesto"
    pasta.mkdir()
    (pasta / "run.ps1").write_text("Write-Host 'ok'", encoding="utf-8")
    return str(tmp_path)


@pytest.mark.unitario
def test_ausencia_de_manifesto_e_bloqueante(tmp_path: Path) -> None:
    raiz = _pasta_sem_manifesto(tmp_path)

    resultado = build_automation_preflight(
        {
            "name": "Sem Manifesto",
            "script_path": "./Sem Manifesto/run.ps1",
            "enabled": True,
        },
        raiz,
    )

    # Via `model_dump`: o pylint não infere os campos do modelo pydantic
    # através do atributo, e o dicionário é o mesmo contrato que a API devolve.
    dados = resultado.model_dump()
    governanca = dados["governance"]

    assert governanca["manifest_present"] is False
    assert governanca["status"] == "incident", (
        "Ausência de manifesto voltou a ser não bloqueante: `attention` passa "
        "por `is_valid = status != 'incident'` e reabre o buraco."
    )
    assert dados["valid"] is False
    assert any(
        item["code"] == "manifest_missing" for item in governanca["blocking_issues"]
    )


@pytest.mark.integracao
@pytest.mark.usefixtures("sem_governanca_automatica")
def test_create_recusa_automacao_sem_manifesto(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O caminho real da API, sem o wrapper da conftest."""
    monkeypatch.setattr(auto_router, "PROJECT_ROOT", _pasta_sem_manifesto(tmp_path))

    resposta = client.post(
        "/api/automations",
        json={
            "name": "Sem Manifesto",
            "script_path": "./Sem Manifesto/run.ps1",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )

    assert resposta.status_code == 422
    assert "manifest" in resposta.text.lower()


@pytest.mark.unitario
def test_scaffolding_gera_o_manifesto_que_o_preflight_exige() -> None:
    """O caminho canônico de criação nunca cai no bloqueio.

    `Tools/New-Automation.ps1` gera `automation.manifest.json` a partir de
    `_Template`. Se o template perder o manifesto, o scaffolding passaria a
    produzir automações que a própria API recusa — e é este teste que avisa.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert os.path.isfile(os.path.join(raiz, "_Template", "automation.manifest.json"))

    with open(
        os.path.join(raiz, "Tools", "New-Automation.ps1"), encoding="utf-8-sig"
    ) as arquivo:
        conteudo = arquivo.read()
    assert "automation.manifest.json" in conteudo

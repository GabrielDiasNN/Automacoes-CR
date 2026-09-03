"""Unit: `get_dashboard_path` e a precedência do override de diretório.

O override `ORCHESTRATOR_DASHBOARD_DIST` foi adicionado para os testes E2E
servirem um build de verificação sem tocar o `Dashboard/dist` que a instância
de produção desta máquina serve ao vivo (mesmo diretório).
"""

import os
from pathlib import Path

import pytest
from app import runtime


@pytest.mark.unitario
def test_override_valido_tem_precedencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alvo = tmp_path / "build-verificacao"
    alvo.mkdir()
    monkeypatch.setenv("ORCHESTRATOR_DASHBOARD_DIST", str(alvo))

    assert runtime.get_dashboard_path() == str(alvo)


@pytest.mark.unitario
def test_override_para_diretorio_inexistente_e_ignorado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ORCHESTRATOR_DASHBOARD_DIST", os.path.join(os.sep, "nao", "existe", "xyz")
    )

    caminho = runtime.get_dashboard_path().replace("\\", "/")

    assert caminho.endswith("Dashboard/dist") or caminho.endswith("Dashboard")


@pytest.mark.unitario
def test_sem_override_usa_dist_quando_existe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORCHESTRATOR_DASHBOARD_DIST", raising=False)

    caminho = runtime.get_dashboard_path().replace("\\", "/")

    # A árvore do repo tem Dashboard/dist buildado; o fallback vanilla só
    # dispara se ele sumir.
    assert caminho.endswith("Dashboard/dist") or caminho.endswith("Dashboard")

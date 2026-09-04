"""Unit: `get_dashboard_path` e a precedência do override de diretório.

O override `ORCHESTRATOR_DASHBOARD_DIST` foi adicionado para os testes E2E
servirem um build de verificação sem tocar o `Dashboard/dist` que a instância
de produção desta máquina serve ao vivo (mesmo diretório).
"""

from pathlib import Path

import pytest
from app import runtime


@pytest.mark.unitario
def test_override_valido_tem_precedencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Override ORCHESTRATOR_DASHBOARD_DIST tem precedência máxima."""
    # Configurar PROJECT_ROOT para tmp_path e criar dist dentro
    monkeypatch.setattr(runtime, "PROJECT_ROOT", str(tmp_path))

    # Criar Dashboard/dist no tmp_path (será ignorado)
    (tmp_path / "Dashboard" / "dist").mkdir(parents=True)

    # Criar um override válido
    override = tmp_path / "build-verificacao"
    override.mkdir()
    monkeypatch.setenv("ORCHESTRATOR_DASHBOARD_DIST", str(override))

    # O override deve vencer mesmo com dist/ presente
    assert runtime.get_dashboard_path() == str(override)


@pytest.mark.unitario
def test_sem_override_usa_dist_quando_existe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quando dist/ existe e não há override, Dashboard/dist é retornado."""
    # Configurar PROJECT_ROOT para tmp_path
    monkeypatch.setattr(runtime, "PROJECT_ROOT", str(tmp_path))

    # Criar Dashboard/dist
    dist_path = tmp_path / "Dashboard" / "dist"
    dist_path.mkdir(parents=True)

    # Sem override
    monkeypatch.delenv("ORCHESTRATOR_DASHBOARD_DIST", raising=False)

    # Deve retornar o caminho exato de dist/
    expected = str(dist_path)
    assert runtime.get_dashboard_path() == expected


@pytest.mark.unitario
def test_sem_override_usa_fallback_quando_dist_ausente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quando dist/ não existe e não há override, Dashboard/ é retornado (fallback)."""
    # Configurar PROJECT_ROOT para tmp_path
    monkeypatch.setattr(runtime, "PROJECT_ROOT", str(tmp_path))

    # Criar apenas Dashboard/ (sem dist/)
    dashboard_path = tmp_path / "Dashboard"
    dashboard_path.mkdir()

    # Sem override
    monkeypatch.delenv("ORCHESTRATOR_DASHBOARD_DIST", raising=False)

    # Deve retornar o caminho exato do fallback
    expected = str(dashboard_path)
    assert runtime.get_dashboard_path() == expected

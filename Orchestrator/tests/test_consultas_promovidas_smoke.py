"""Smoke tests de contrato das consultas promovidas em ``Consultas Promovidas/``."""

from __future__ import annotations

from pathlib import Path

import pytest
from promovidas.config import carregar_config

_SLUGS = (
    "rama-risco-atraso",
    "rama-pulmao-autonomia",
    "gargalo-receitas-tingimento",
    "quimicos-ruptura-compra",
    "qualidade-separacao-montagem",
    "qualidade-pecas-restricao-montagem",
)


@pytest.mark.unitario
@pytest.mark.parametrize("slug", _SLUGS)
def test_consulta_promovida_artefatos_obrigatorios_existem(slug: str) -> None:
    root = Path(__file__).resolve().parents[2]
    pasta = root / "Consultas Promovidas" / slug

    assert (pasta / "run.ps1").is_file()
    assert (pasta / "promocao.json").is_file()
    assert (pasta / "consulta.sql").is_file()
    assert (pasta / "automation.manifest.json").is_file()
    assert (pasta / "README.md").is_file()
    assert (pasta / "CONTEXT.md").is_file()
    assert (root / "docs" / "runbooks" / f"{slug}-runbook.md").is_file()

    cfg = carregar_config(pasta / "promocao.json")
    assert cfg.slug == slug
    assert cfg.modo == "sombra"
    assert (pasta / cfg.consulta).is_file()

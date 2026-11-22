"""Testes da API /api/promovidas/* e descoberta Modelo 2 no catalogo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.portfolio_manifest import CatalogManifest, load_catalog_manifests
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from promovidas import ConfigPainel, ConfigPromocao
from promovidas.snapshot import gravar_snapshot


@pytest.mark.unitario
def test_manifesto_aceita_canal_dashboard_e_descobre_consultas_promovidas() -> None:
    root = Path(__file__).resolve().parents[2]
    entries = load_catalog_manifests(root, include_template=False)
    ids = {entry.manifest.id for entry in entries}
    assert {"CP-01", "CP-02", "CP-03", "CP-04", "CP-05", "CP-06"}.issubset(ids)

    cp01 = next(e for e in entries if e.manifest.id == "CP-01")
    assert cp01.manifest.directory_name == "Consultas Promovidas/rama-risco-atraso"
    assert "dashboard" in cp01.manifest.channels

    with pytest.raises(ValueError):
        CatalogManifest.v_channels(["telegram"])


@pytest.mark.integracao
def test_api_promovidas_lista_latest_historico_e_erros(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pasta = tmp_path / "Consultas Promovidas" / "rama-risco-atraso"
    pasta.mkdir(parents=True)
    (pasta / "promocao.json").write_text(
        json.dumps(
            {
                "slug": "rama-risco-atraso",
                "nome": "Risco Atraso Ramas",
                "consulta": "consulta.sql",
                "modo": "sombra",
                "chave": ["NUMERO_OB"],
                "destinos": ["whatsapp", "dashboard"],
                "painel": {"titulo": "Risco nas Ramas", "kpis": ["count"]},
            }
        ),
        encoding="utf-8",
    )
    latest = tmp_path / "Consultas Promovidas" / "snapshots" / "latest"
    latest.mkdir(parents=True)
    (latest / "rama-risco-atraso.json").write_text(
        json.dumps(
            {
                "slug": "rama-risco-atraso",
                "nome": "Risco Atraso Ramas",
                "titulo": "Risco nas Ramas",
                "modo": "sombra",
                "generated_at": "2026-11-21T22:00:00+00:00",
                "total_rows": 2,
                "excecoes_count": 1,
                "kpis": {"count": 2},
                "columns": ["NUMERO_OB"],
                "rows": [{"NUMERO_OB": "123"}, {"NUMERO_OB": "456"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.routers.promovidas.get_project_root", lambda: str(tmp_path)
    )

    resp_list = client.get("/api/promovidas/", headers=AUTH_HEADERS)
    assert resp_list.status_code == 200
    items = resp_list.json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "rama-risco-atraso"
    assert items[0]["has_snapshot"] is True
    assert items[0]["total_rows"] == 2

    resp_latest = client.get(
        "/api/promovidas/rama-risco-atraso/latest", headers=AUTH_HEADERS
    )
    assert resp_latest.status_code == 200
    assert len(resp_latest.json()["rows"]) == 2

    resp_hist = client.get(
        "/api/promovidas/rama-risco-atraso/history", headers=AUTH_HEADERS
    )
    assert resp_hist.status_code == 200
    assert resp_hist.json()["items"] == []

    cfg_snap = ConfigPromocao(
        slug="rama-risco-atraso",
        nome="Risco Atraso Ramas",
        consulta="consulta.sql",
        modo="sombra",
        chave=("NUMERO_OB",),
        destinos=("whatsapp", "dashboard"),
        painel=ConfigPainel(titulo="Risco nas Ramas", kpis=("count",), colunas=()),
        excecao=None,
    )
    gravar_snapshot(
        tmp_path,
        cfg_snap,
        [{"NUMERO_OB": "123"}, {"NUMERO_OB": "456"}],
        {"count": 2},
        excecoes_count=1,
    )
    resp_hist_com_dados = client.get(
        "/api/promovidas/rama-risco-atraso/history", headers=AUTH_HEADERS
    )
    assert resp_hist_com_dados.status_code == 200
    assert len(resp_hist_com_dados.json()["items"]) == 1

    assert (
        client.get(
            "/api/promovidas/inexistente/latest", headers=AUTH_HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/promovidas/Slug_Invalido/latest", headers=AUTH_HEADERS
        ).status_code
        == 400
    )


@pytest.mark.integracao
def test_preflight_aceita_consulta_promovida_sem_whatsapp_config(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modelo 2 usa promocao.json em vez de whatsapp-config.json."""
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr("app.routers.automations.PROJECT_ROOT", str(root))
    manifest = json.loads(
        (
            root / "Consultas Promovidas" / "rama-risco-atraso" / "automation.manifest.json"
        ).read_text(encoding="utf-8")
    )
    payload = {
        "name": manifest["name"],
        "script_path": manifest["orchestrator"]["script_path"],
        "queue_group": manifest["queue_group"],
        "sla_minutes": manifest["sla_minutes"],
        "max_runtime_minutes": manifest["max_runtime_minutes"],
        "max_retries": manifest["max_retries"],
        "notification_channels": ",".join(manifest["channels"]),
    }
    resp = client.post("/api/automations/preflight", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True, body
    assert body["governance"]["status"] != "incident"
    assert body["governance"]["blocking_issues"] == []

"""Testes da API /api/promovidas/* e descoberta Modelo 2 no catalogo."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from app.services.automation_preflight import _promocao_config_issues
from app.services.portfolio_manifest import CatalogManifest, load_catalog_manifests
from app.services.promovidas import (
    _AUTOMACOES_POR_SLUG,
    _coletar_cards_automacao,
    _extrair_linhas_automacao,
    _float_seguro,
    _idade_minutos,
    _int_seguro,
    _kpis_linhas_automacao,
    _kpis_seguros,
    _montar_item_promovida,
    _obter_snapshot_automacao,
    _setor_por_owner,
    _validar_card_manifesto,
    resolver_card_png,
)
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
    assert client.get("/api/promovidas/").status_code == 403
    assert client.get("/api/promovidas/rama-risco-atraso/latest").status_code == 403
    assert client.get("/api/promovidas/rama-risco-atraso/history").status_code == 403
    assert (
        client.get("/api/promovidas/rama-risco-atraso/cards/card.png").status_code
        == 403
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
            root
            / "Consultas Promovidas"
            / "rama-risco-atraso"
            / "automation.manifest.json"
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


@pytest.mark.unitario
def test_promocao_config_issues_e_helpers_defensivos(tmp_path: Path) -> None:
    """Cobre branches defensivos de _promocao_config_issues, _int_seguro e _kpis_seguros."""
    vazio = tmp_path / "sem_promocao"
    vazio.mkdir()
    issues_missing = _promocao_config_issues(str(vazio))
    assert [i.code for i in issues_missing] == ["promocao_config_missing"]

    invalido = tmp_path / "json_invalido"
    invalido.mkdir()
    (invalido / "promocao.json").write_text("{invalido", encoding="utf-8")
    issues_invalid = _promocao_config_issues(str(invalido))
    assert [i.code for i in issues_invalid] == ["promocao_config_invalid"]

    lista = tmp_path / "json_lista"
    lista.mkdir()
    (lista / "promocao.json").write_text("[]", encoding="utf-8")
    issues_lista = _promocao_config_issues(str(lista))
    assert [i.code for i in issues_lista] == ["promocao_config_invalid"]

    assert _int_seguro(True, 7) == 7
    assert _int_seguro("nao-int", 5) == 5
    assert _int_seguro(None, 3) == 3
    assert _kpis_seguros('{"count": 2}') == {"count": 2}
    assert _kpis_seguros("[1, 2]") == {}
    assert _kpis_seguros("{quebrado") == {}
    assert _kpis_seguros(123) == {}


@pytest.mark.integracao
def test_api_promovidas_inclui_automacoes_e_serve_cards_png(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Valida leitura unificada de snapshots das automacoes e entrega segura de cards PNG."""
    pasta_obp = tmp_path / "OBs Paradas Fase"
    (pasta_obp / "images").mkdir(parents=True)
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    (pasta_obp / "images" / "FELPAGEM.png").write_bytes(png_bytes)
    (pasta_obp / "obs_result.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "NUMERO_OB": 193374,
                        "FASE_ATUAL": "FEL-FELPAGEM",
                        "DIAS_PARADO": 4.1,
                        "QT_KILOS_REAL": 1042.8,
                    }
                ],
                "total": 1,
                "extracted_at": "2026-11-22T14:00:00",
            }
        ),
        encoding="utf-8",
    )
    (pasta_obp / "phase_cards.json").write_text(
        json.dumps(
            [
                {
                    "phase_key": "FELPAGEM",
                    "phase_display": "Felpagem",
                    "image_path": "images/FELPAGEM.png",
                    "caption": "Felpagem - 1 OB parada",
                }
            ]
        ),
        encoding="utf-8",
    )

    pasta_rb = tmp_path / "Receitas Bloqueadas"
    pasta_rb.mkdir(parents=True)
    (pasta_rb / "receitas_state.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-11-22T11:00:00",
                "records": [{"Cor Rec.": "00001", "EP Rec.": 19}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.routers.promovidas.get_project_root", lambda: str(tmp_path)
    )

    resp = client.get("/api/promovidas/", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    slugs = [i["slug"] for i in items]
    assert "obs-paradas-fase" in slugs
    assert "receitas-bloqueadas" in slugs

    obp = next(i for i in items if i["slug"] == "obs-paradas-fase")
    assert obp["origem"] == "automacao"
    assert obp["codigo"] == "OBP-04"
    assert obp["cards_count"] == 1
    assert obp["total_rows"] == 1

    snap = client.get("/api/promovidas/obs-paradas-fase/latest", headers=AUTH_HEADERS)
    assert snap.status_code == 200
    body = snap.json()
    assert body["kpis"]["sum:KG_PARADO"] == 1042.8
    assert len(body["cards"]) == 1
    assert body["cards"][0]["filename"] == "FELPAGEM.png"

    card_ok = client.get(
        "/api/promovidas/obs-paradas-fase/cards/FELPAGEM.png", headers=AUTH_HEADERS
    )
    assert card_ok.status_code == 200
    assert card_ok.headers["content-type"] == "image/png"
    assert card_ok.headers.get("cache-control") == "no-cache"
    assert card_ok.content == png_bytes

    card_bad_ext = client.get(
        "/api/promovidas/obs-paradas-fase/cards/obs_result.json", headers=AUTH_HEADERS
    )
    assert card_bad_ext.status_code == 400

    card_not_found = client.get(
        "/api/promovidas/obs-paradas-fase/cards/INEXISTENTE.png", headers=AUTH_HEADERS
    )
    assert card_not_found.status_code == 404


@pytest.mark.integracao
def test_api_promovidas_ofst_cards_na_raiz(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OFST-06 le cards_manifest.json e card.png gravados na raiz da pasta."""
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    pasta_ofst = tmp_path / "OBs Fluxo Sem Tingimento"
    pasta_ofst.mkdir(parents=True)
    (pasta_ofst / "card.png").write_bytes(png_bytes)
    (pasta_ofst / "cards_manifest.json").write_text(
        json.dumps([{"phase_key": "p1", "image_path": "card.png", "caption": "OFST"}]),
        encoding="utf-8",
    )
    (pasta_ofst / "ofst_result.json").write_text(
        json.dumps({"rows": [{"OB": "1"}], "extracted_at": "2026-11-22T14:00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.routers.promovidas.get_project_root", lambda: str(tmp_path)
    )
    snap_ofst = client.get(
        "/api/promovidas/obs-fluxo-sem-tingimento/latest", headers=AUTH_HEADERS
    )
    assert snap_ofst.status_code == 200
    assert len(snap_ofst.json()["cards"]) == 1
    assert (
        client.get(
            "/api/promovidas/obs-fluxo-sem-tingimento/cards/card.png",
            headers=AUTH_HEADERS,
        ).status_code
        == 200
    )


@pytest.mark.unitario
def test_idade_minutos_naive_brt_e_manifesto_cards_sem_traversal(
    tmp_path: Path,
) -> None:
    agora_brt_naive = (
        datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None).isoformat()
    )
    idade = _idade_minutos(agora_brt_naive)
    assert idade is not None
    assert 0.0 <= idade < 5.0

    pasta = tmp_path / "OBs Paradas Fase"
    (pasta / "images").mkdir(parents=True)
    (pasta / "images" / "OK.png").write_bytes(b"png")
    (pasta / "RAIZ.png").write_bytes(b"png")
    (tmp_path / "FORA.png").write_bytes(b"png")
    spec = _AUTOMACOES_POR_SLUG["obs-paradas-fase"]

    assert _validar_card_manifesto(pasta, spec, "images/OK.png") == "OK.png"
    assert _validar_card_manifesto(pasta, spec, "RAIZ.png") is None
    assert _validar_card_manifesto(pasta, spec, "../FORA.png") is None
    assert _validar_card_manifesto(pasta, spec, "images/NAO_EXISTE.png") is None
    assert _validar_card_manifesto(pasta, spec, "images/OK.jpg") is None
    assert _idade_minutos("data-invalida") is None


@pytest.mark.unitario
def test_promovidas_helpers_conversao_e_setores() -> None:
    assert _float_seguro(True) == 0.0
    assert _float_seguro("12.5") == 12.5
    assert _float_seguro("invalido") == 0.0
    assert _int_seguro(False) == 0

    assert _setor_por_owner("Ramagem") == "Acabamento & Ramas"
    assert _setor_por_owner("Tinturaria") == "Tinturaria & Receitas"
    assert _setor_por_owner("Montagem") == "Qualidade & Montagem"
    assert _setor_por_owner("Faturamento") == "Comercial & Expedição"
    assert _setor_por_owner("Outro") == "Beneficiamento & PCP"

    assert _kpis_seguros({"itens": "abc", "qtd": 5}) == {"itens": "abc", "qtd": 5}
    assert _kpis_linhas_automacao("outra", [], {"record_counts": {"read": 9}}) == {
        "count": 0,
        "lidos": 9,
    }


@pytest.mark.unitario
def test_promovidas_extracao_montagem_e_cards(tmp_path: Path) -> None:
    pasta_mt = tmp_path / "Montagem de Terceirizados"
    pasta_mt.mkdir(parents=True)
    spec_mt = _AUTOMACOES_POR_SLUG["montagem-terceirizados"]
    (pasta_mt / ".cache_erros.json").write_text(
        json.dumps(
            {
                "itens": {
                    "OB-1": {"OB": "OB-1", "QTD": 2},
                    "invalido": "ignorar",
                },
                "timestamp": "2026-11-23T12:00:00",
            }
        ),
        encoding="utf-8",
    )
    rows_mt, kpis_mt, ts_mt, total_mt = _extrair_linhas_automacao(pasta_mt, spec_mt)
    assert len(rows_mt) == 2
    assert total_mt == 2
    assert ts_mt == "2026-11-23T12:00:00"
    assert kpis_mt["count"] == 2

    pasta_obs = tmp_path / "OBs Paradas Fase"
    (pasta_obs / "images").mkdir(parents=True)
    (pasta_obs / "images" / "A.png").write_bytes(b"png")
    (pasta_obs / "images" / "OBSOLETO.png").write_bytes(b"png")
    (pasta_obs / "phase_cards.json").write_text(
        json.dumps(
            [
                "ignorar",
                {
                    "phase_key": "A",
                    "phase_display": "Fase A",
                    "image_path": "images/A.png",
                    "caption": "Cap A",
                },
                {"image_path": "images/A.png"},
            ]
        ),
        encoding="utf-8",
    )
    cards_obs = _coletar_cards_automacao(
        pasta_obs, _AUTOMACOES_POR_SLUG["obs-paradas-fase"]
    )
    assert [c["filename"] for c in cards_obs] == ["A.png"]
    assert cards_obs[0]["title"] == "Fase A"
    assert cards_obs[0]["caption"] == "Cap A"


@pytest.mark.unitario
def test_promovidas_extracao_receitas_e_erros_404(tmp_path: Path) -> None:
    pasta_rb = tmp_path / "Receitas Bloqueadas"
    pasta_rb.mkdir(parents=True)
    (pasta_rb / "receitas_state.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-11-23T13:00:00",
                "records": [{"REC": "1"}],
            }
        ),
        encoding="utf-8",
    )
    (pasta_rb / "rb_result.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-11-23T13:00:00",
                "record_counts": {"read": 1, "new": 2, "changed": 1},
            }
        ),
        encoding="utf-8",
    )
    rows_rb, kpis_rb, _, _ = _extrair_linhas_automacao(
        pasta_rb, _AUTOMACOES_POR_SLUG["receitas-bloqueadas"]
    )
    assert isinstance(rows_rb, list)
    assert len(rows_rb) == 1
    assert kpis_rb["count"] == 1
    assert kpis_rb["novos"] == 2
    assert kpis_rb["alterados"] == 1

    pasta_re = tmp_path / "Receitas Emitidas"
    pasta_re.mkdir(parents=True)
    spec_re = _AUTOMACOES_POR_SLUG["receitas-emitidas"]
    (pasta_re / "re_result.json").write_text(
        json.dumps({"record_counts": {"read": 4}, "timestamp": "2026-11-23T14:00:00"}),
        encoding="utf-8",
    )
    rows_re, kpis_re, _, total_re = _extrair_linhas_automacao(pasta_re, spec_re)
    assert rows_re == []
    assert isinstance(total_re, int)
    assert kpis_re == {"count": 4, "lidos": 4}

    assert _montar_item_promovida(tmp_path, tmp_path / "nao_existe") is None

    with pytest.raises(Exception) as exc_pasta:
        _obter_snapshot_automacao(tmp_path / "inexistente", spec_re)
    assert getattr(exc_pasta.value, "status_code", None) == 404

    with pytest.raises(Exception) as exc_slug:
        resolver_card_png(tmp_path, "slug-inexistente", "a.png")
    assert getattr(exc_slug.value, "status_code", None) == 404

    with pytest.raises(Exception) as exc_card:
        resolver_card_png(tmp_path, "obs-paradas-fase", "../invalido.png")
    assert getattr(exc_card.value, "status_code", None) in {400, 404}

"""Testes unitarios do motor declarativo de consultas promovidas."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import hub_runner as hr
import hub_whatsapp as hw
import oracle_queue
import pytest
from app.services.promovidas import obter_historico
from promovidas import (
    CondicaoFiltro,
    ConfigExcecao,
    ConfigPainel,
    ConfigPromocao,
    calcular_kpis,
    carregar_config,
    extrair_chave,
    filtrar_excecoes,
)
from promovidas.card import gerar_artefatos_whatsapp
from promovidas.estado import gravar_estado, ler_estado, selecionar_pendentes
from promovidas.extracao import validar_sql_somente_leitura
from promovidas.run_promocao import (
    _despachar_excecoes,
    _executar_promocao,
    _resolver_destino_whatsapp,
)
from promovidas.snapshot import gravar_snapshot


def _cfg_exemplo(tmp_path: Path, *, modo: str = "sombra") -> ConfigPromocao:
    _ = tmp_path
    return ConfigPromocao(
        slug="teste-promovida",
        nome="Teste Promovida",
        consulta="consulta.sql",
        modo="sombra" if modo == "sombra" else "producao",
        chave=("NUMERO_OB",),
        destinos=("whatsapp", "dashboard"),
        painel=ConfigPainel(
            titulo="Teste Painel",
            kpis=("count", "sum:KG_OB", "min:AUTONOMIA"),
            colunas=(),
        ),
        excecao=ConfigExcecao(
            condicoes=(
                CondicaoFiltro(coluna="RISCO", op="in", valor=["CRITICO", "ALTO"]),
                CondicaoFiltro(coluna="AUTONOMIA", op="lt", valor=6.0),
            ),
            renotificar_apos_horas=24.0,
            colunas_card=("NUMERO_OB", "RISCO", "AUTONOMIA", "KG_OB"),
            titulo_alerta="Alerta Teste",
            destino_whatsapp_env="TESTE_WA_DESTINO",
        ),
    )


@pytest.mark.unitario
def test_regras_filtrar_excecoes_and_e_kpis() -> None:
    rows: list[dict[str, Any]] = [
        {"NUMERO_OB": 1, "RISCO": "CRITICO", "AUTONOMIA": 2.5, "KG_OB": 100.5},
        {"NUMERO_OB": 2, "RISCO": "CRITICO", "AUTONOMIA": 8.0, "KG_OB": 200.0},
        {"NUMERO_OB": 3, "RISCO": "REGULAR", "AUTONOMIA": 1.0, "KG_OB": 50.0},
    ]
    conds = [
        CondicaoFiltro("RISCO", "in", ["CRITICO", "ALTO"]),
        CondicaoFiltro("AUTONOMIA", "lt", 6.0),
    ]
    excecoes = filtrar_excecoes(rows, conds)
    assert [r["NUMERO_OB"] for r in excecoes] == [1]

    # "0 linhas" continua valido e variante relaxada (sem condicoes) retorna tudo
    assert filtrar_excecoes([], conds) == []
    assert len(filtrar_excecoes(rows, [])) == 3

    kpis = calcular_kpis(rows, ("count", "sum:KG_OB", "min:AUTONOMIA", "max:KG_OB"))
    assert kpis == {
        "count": 3,
        "sum:KG_OB": 350.5,
        "min:AUTONOMIA": 1.0,
        "max:KG_OB": 200.0,
    }
    assert extrair_chave(rows[0], ("NUMERO_OB", "RISCO")) == "1|CRITICO"


@pytest.mark.unitario
def test_estado_idempotencia_ttl_e_limpeza_de_chave_resolvida(tmp_path: Path) -> None:
    state_path = tmp_path / "seen_state.json"
    t0 = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)
    exc = [{"NUMERO_OB": "100"}, {"NUMERO_OB": "200"}]

    pend1, st1 = selecionar_pendentes(
        exc, ("NUMERO_OB",), ler_estado(state_path), agora=t0, renotificar_apos_horas=24
    )
    assert [r["NUMERO_OB"] for r in pend1] == ["100", "200"]
    gravar_estado(state_path, st1, exec_id="EXEC-1")

    # Dentro da janela de 24h, nao renotifica
    t1 = t0 + timedelta(hours=2)
    pend2, st2 = selecionar_pendentes(
        exc, ("NUMERO_OB",), ler_estado(state_path), agora=t1, renotificar_apos_horas=24
    )
    assert not pend2
    assert set(st2.keys()) == {"100", "200"}

    # OB 100 saiu das excecoes e depois voltou: deve alertar imediatamente
    _, st3 = selecionar_pendentes(
        [{"NUMERO_OB": "200"}],
        ("NUMERO_OB",),
        st2,
        agora=t1 + timedelta(hours=1),
        renotificar_apos_horas=24,
    )
    assert "100" not in st3

    pend4, _ = selecionar_pendentes(
        exc,
        ("NUMERO_OB",),
        st3,
        agora=t1 + timedelta(hours=2),
        renotificar_apos_horas=24,
    )
    assert [r["NUMERO_OB"] for r in pend4] == ["100"]

    # Apos TTL de 24h, OB 200 volta a ser notificada
    pend5, _ = selecionar_pendentes(
        [{"NUMERO_OB": "200"}],
        ("NUMERO_OB",),
        st3,
        agora=t0 + timedelta(hours=25),
        renotificar_apos_horas=24,
    )
    assert [r["NUMERO_OB"] for r in pend5] == ["200"]


@pytest.mark.unitario
def test_snapshot_e_card_png_validado_por_hub_whatsapp(tmp_path: Path) -> None:
    cfg = _cfg_exemplo(tmp_path, modo="sombra")
    rows = [
        {"NUMERO_OB": "9001", "RISCO": "CRITICO", "AUTONOMIA": 1.5, "KG_OB": 320.0},
    ]
    kpis = calcular_kpis(rows, cfg.painel.kpis)
    snap_path = gravar_snapshot(tmp_path, cfg, rows, kpis, excecoes_count=1)
    assert snap_path.is_file()
    dados = json.loads(snap_path.read_text(encoding="utf-8"))
    assert dados["total_rows"] == 1
    assert dados["excecoes_count"] == 1

    hist = obter_historico(tmp_path, cfg.slug)
    assert len(hist) == 1
    assert hist[0]["total_rows"] == 1

    png_path, msg_path, manifest_path = gerar_artefatos_whatsapp(cfg, rows, tmp_path)
    assert png_path.is_file()
    assert "[MODO SOMBRA]" in msg_path.read_text(encoding="utf-8")
    manifest = hw.read_cards_manifest(manifest_path, base_dir=tmp_path)
    assert manifest.valid is True
    assert len(manifest.cards) == 1
    assert manifest.cards[0].ob_ids == ("9001",)


@pytest.mark.unitario
def test_modo_sombra_forca_grupo_alerta_e_guard_bloqueia_dml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AUTOMACAO_ALERT_WHATSAPP", "grupo-alerta@g.us")
    monkeypatch.setenv("TESTE_WA_DESTINO", "grupo-producao@g.us")

    cfg_sombra = _cfg_exemplo(tmp_path, modo="sombra")
    assert _resolver_destino_whatsapp(cfg_sombra) == ("grupo-alerta@g.us", "hub-global")

    cfg_prod = _cfg_exemplo(tmp_path, modo="producao")
    assert _resolver_destino_whatsapp(cfg_prod) == ("grupo-producao@g.us", "hub-global")

    cfg_json = tmp_path / "promocao.json"
    cfg_json.write_text(
        json.dumps(
            {
                "slug": "x",
                "nome": "X",
                "consulta": "consulta.sql",
                "modo": "sombra",
                "chave": ["ID"],
                "destinos": ["dashboard"],
                "painel": {"titulo": "X"},
            }
        ),
        encoding="utf-8",
    )
    carregada = carregar_config(cfg_json)
    assert carregada.slug == "x"
    assert carregada.excecao is None

    root = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="bloqueado"):
        validar_sql_somente_leitura(root, "DELETE FROM SGTPRD.OB")


@pytest.mark.unitario
def test_carregar_config_rejeita_chave_vazia_destinos_invalido_e_traversal(
    tmp_path: Path,
) -> None:
    base = {
        "slug": "x",
        "nome": "X",
        "consulta": "consulta.sql",
        "modo": "sombra",
        "chave": ["  "],
        "destinos": ["dashboard"],
        "painel": {"titulo": "X"},
    }
    cfg_path = tmp_path / "promocao.json"
    cfg_path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match="chave"):
        carregar_config(cfg_path)

    base["chave"] = ["ID"]
    base["destinos"] = "dashboard"
    cfg_path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match="destinos"):
        carregar_config(cfg_path)

    base["destinos"] = ["dashboard"]
    base["consulta"] = "../fora.sql"
    cfg_path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match="caminho relativo"):
        carregar_config(cfg_path)


@pytest.mark.unitario
def test_run_promocao_reconciliacao_parcial_e_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AUTOMACAO_ALERT_WHATSAPP", "grupo-alerta@g.us")
    cfg = _cfg_exemplo(tmp_path, modo="sombra")
    spec = hr.AutomationSpec(
        automacao=cfg.nome,
        slug=cfg.slug,
        trace_slug=cfg.slug,
        lock_key="TEST",
        log_dir=tmp_path / "Logs",
        non_failure_codes=(0, 2, 22),
    )
    ctx = hr.create_run_context(spec, exec_id="TEST-1", project_root=tmp_path)

    # 17 excecoes -> 2 paginas (MAX_OBS_PER_PAGE=15 + 2)
    excecoes = [
        {"NUMERO_OB": str(i), "RISCO": "CRITICO", "AUTONOMIA": 1.0, "KG_OB": 10.0}
        for i in range(1, 18)
    ]

    def _fake_send_partial(*_args: Any, **kwargs: Any) -> int:
        batch_out = Path(kwargs["batch_result_file"])
        batch_out.write_text(
            json.dumps(
                [
                    {"phase_key": f"{cfg.slug}_p01", "success": True},
                    {"phase_key": f"{cfg.slug}_p02", "success": False},
                ]
            ),
            encoding="utf-8",
        )
        return 1

    monkeypatch.setattr(hw, "send_whatsapp", _fake_send_partial)
    code = _despachar_excecoes(ctx, cfg, tmp_path, excecoes, dry_run=False)
    assert code == 4
    notified = ler_estado(tmp_path / "seen_state.json")
    assert set(notified.keys()) == {str(i) for i in range(1, 16)}
    assert not (tmp_path / "seen_state.json.tmp").exists()

    # Exit 22 preserva codigo 22 sem gravar os restantes
    monkeypatch.setattr(hw, "send_whatsapp", lambda *_a, **_k: 22)
    code22 = _despachar_excecoes(ctx, cfg, tmp_path, excecoes[15:], dry_run=False)
    assert code22 == 22
    assert set(ler_estado(tmp_path / "seen_state.json").keys()) == {
        str(i) for i in range(1, 16)
    }

    # Falha de extracao com OracleQueueWorkerOfflineError devolve 26 (canonico)
    (tmp_path / "consulta.sql").write_text("SELECT 1 FROM DUAL", encoding="utf-8")
    (tmp_path / "card.png").write_bytes(b"stale")
    monkeypatch.setattr(hr, "run_preflight", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "promovidas.extracao.executar_consulta_promovida",
        lambda *_a, **_k: (_ for _ in ()).throw(
            oracle_queue.OracleQueueWorkerOfflineError("WORKER_OFFLINE", "offline")
        ),
    )
    assert _executar_promocao(ctx, cfg, tmp_path, dry_run=False) == 26
    assert not (tmp_path / "card.png").exists()

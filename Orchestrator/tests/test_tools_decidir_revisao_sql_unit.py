"""Regra fixa da revisão de SQL lida dos JSONs de evidência (decidir_revisao_sql.py)."""

import json
from pathlib import Path
from typing import Any

import pytest
from tests.carregadores_modulos import carregar_tool_oracle as _carregar

dr = _carregar("decidir_revisao_sql")

pytestmark = pytest.mark.unitario


def _unidade(
    tmp_path: Path,
    *,
    head_ms: float = 1000.0,
    wt_ms: float = 400.0,
    divergencias: list[Any] | None = None,
    sql: str = "select 1 from dual",
) -> tuple[Path, Path]:
    prefixo = tmp_path / "u1"
    resumo = {"n": 7, "noise_ms": 10.0}
    arquivos: dict[str, Any] = {
        "validar-wt": {"status": "validated"},
        "head-medicao": {"summary": {**resumo, "median_ms": head_ms}},
        "wt-medicao": {"summary": {**resumo, "median_ms": wt_ms}},
        "equivalencia": {"divergences": divergencias or [], "status": "ok"},
    }
    for sufixo, conteudo in arquivos.items():
        Path(f"{prefixo}-{sufixo}.json").write_text(
            json.dumps(conteudo), encoding="utf-8"
        )
    sql_wt = tmp_path / "wt.sql"
    sql_wt.write_text(sql, encoding="utf-8")
    return prefixo, sql_wt


def test_mantem_wt_com_paridade_e_ganho(tmp_path: Path) -> None:
    prefixo, sql_wt = _unidade(tmp_path)
    assert dr.decidir(prefixo, sql_wt, tem_wt_diferente=True)["acao"] == "manter_wt"


def test_reverte_quando_diverge(tmp_path: Path) -> None:
    prefixo, sql_wt = _unidade(tmp_path, divergencias=["cardinalidade"])
    assert dr.decidir(prefixo, sql_wt, tem_wt_diferente=True)["acao"] == "reverter_head"


def test_correcao_aprovada_e_alcancavel_mesmo_com_divergencia(tmp_path: Path) -> None:
    """Regressão: antes a paridade revertia antes de olhar a correção aprovada."""
    prefixo, sql_wt = _unidade(
        tmp_path, head_ms=1000.0, wt_ms=1800.0, divergencias=["pedido determinístico"]
    )
    decisao = dr.decidir(prefixo, sql_wt, tem_wt_diferente=True, correcao_aprovada=True)
    assert decisao["acao"] == "manter_wt"


def test_ponto_e_virgula_fora_de_comentario_reverte(tmp_path: Path) -> None:
    prefixo, sql_wt = _unidade(tmp_path, sql="select 1 from dual /* a;b */;")
    assert dr.decidir(prefixo, sql_wt, tem_wt_diferente=True)["acao"] == "reverter_head"
    assert dr.sem_ponto_e_virgula("select ';' from dual -- fim;")


def test_evidencia_ausente_fica_pendente(tmp_path: Path) -> None:
    sql_wt = tmp_path / "wt.sql"
    sql_wt.write_text("select 1 from dual", encoding="utf-8")
    decisao = dr.decidir(tmp_path / "nada", sql_wt, tem_wt_diferente=True)
    assert decisao["acao"] == "pendente"


def test_exigir_sai_com_1_quando_decisao_difere(tmp_path: Path) -> None:
    prefixo, sql_wt = _unidade(tmp_path)
    argv = ["--prefixo", str(prefixo), "--sql-wt", str(sql_wt), "--tem-wt-diferente"]
    assert dr.main([*argv, "--exigir", "reverter_head"]) == 1
    assert dr.main([*argv, "--exigir", "manter_wt"]) == 0

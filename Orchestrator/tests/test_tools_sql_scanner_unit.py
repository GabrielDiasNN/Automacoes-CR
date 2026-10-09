"""Testes unitarios do scanner SQL compartilhado por oracle_catalog e validar_sql_oracle."""

from pathlib import Path

import pytest
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

oc = _carregar("oracle_catalog")
vs = _carregar("validar_sql_oracle")


_bind_names = _priv(vs, "_bind_names")
_ensure_select_only = _priv(oc, "_ensure_select_only")
_single_statement = _priv(vs, "_single_statement")
_statement_terminators = _priv(vs, "_statement_terminators")
_strip_comments = _priv(vs, "_strip_comments")
_validate_one = _priv(vs, "_validate_one")

pytestmark = pytest.mark.unitario


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT NVL(A,'--') X, B FROM T",
        "SELECT '/* nao e comentario */' X FROM T",
        "SELECT LISTAGG(A, '; ') X FROM T",
        "SELECT q'[don't -- x]' FROM dual",
        "SELECT Q'{a;b}' , nq'(c -- d)' , q'<e /* f>' , q'#g'h -- #' FROM dual",
        'SELECT "COL--X" FROM T',
    ],
)
def test_strip_comments_preserva_literais(sql: str) -> None:
    assert _strip_comments(sql) == sql


def test_strip_comments_remove_comentarios_e_preserva_hint() -> None:
    sql = "SELECT /*+ INDEX(T I) */ A -- fim\nFROM T /* x */"
    out = _strip_comments(sql)
    assert "/*+ INDEX(T I) */" in out
    assert "fim" not in out and "/* x */" not in out


def test_single_statement_nao_trunca_literal() -> None:
    assert _single_statement("SELECT NVL(A,'--') X, B FROM T;\n") == (
        "SELECT NVL(A,'--') X, B FROM T"
    )


def test_terminadores_ignoram_literais_e_q_quote() -> None:
    assert _statement_terminators("SELECT q'[a;b]', '; ' FROM T") == (0, False)
    assert _statement_terminators("SELECT 1 FROM T;") == (1, True)
    assert _statement_terminators("SELECT 1 FROM T; DELETE FROM T") == (1, False)


def test_bind_names_ignora_literais_e_q_quote() -> None:
    sql = "SELECT ':x', q'[:y]' FROM T WHERE A = :dt_inicio -- :z"
    assert _bind_names(sql) == ["DT_INICIO"]


def test_split_sql_q_quote_nao_trunca() -> None:
    sql = "SELECT q'[don't -- x]' FROM dual"
    assert _ensure_select_only(sql) == sql


def test_q_quote_nao_fechado_e_rejeitado() -> None:
    with pytest.raises(oc.GuardError):
        _ensure_select_only("SELECT q'[abc; DELETE FROM T")
    with pytest.raises(oc.GuardError):
        _ensure_select_only("SELECT q'")


def test_ponto_e_virgula_apos_q_quote_fechado_e_detectado() -> None:
    with pytest.raises(oc.GuardError):
        _ensure_select_only("SELECT q'[a]' FROM T; DELETE FROM T")


def test_identificador_terminado_em_q_nao_e_q_quote() -> None:
    sql = "SELECT faq 'x' FROM T"
    assert _ensure_select_only(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM T",
        "SELECT 1 FROM T; DROP TABLE T",
        "SELECT q'[x]' FROM T WHERE 1=1 UNION SELECT 1 FROM T; TRUNCATE TABLE T",
        "BEGIN NULL; END;",
    ],
)
def test_dml_e_plsql_continuam_bloqueados(sql: str) -> None:
    with pytest.raises(oc.GuardError):
        _ensure_select_only(sql)


def test_guard_codigo_4_bloqueia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT 1 FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard", lambda _p, _g: (4, "x"))
    opts = vs.RunOptions(timeout=1, execute=True, explicit_binds={}, guard=f)
    assert _validate_one(f, None, opts)["status"] == "blocked_guard"


def test_guard_codigo_0_segue_para_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT 1 FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard", lambda _p, _g: (0, ""))
    monkeypatch.setattr(vs, "_oracle_stage", lambda *_a: {"status": "validated"})
    opts = vs.RunOptions(timeout=1, execute=True, explicit_binds={}, guard=f)
    assert _validate_one(f, None, opts)["status"] == "validated"

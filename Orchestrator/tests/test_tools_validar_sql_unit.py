"""Testes unitarios de Tools/oracle/validar_sql_oracle.py: nivel "so parse" do guard (sem tocar o Oracle)."""

import json
from pathlib import Path
from typing import Any

import pytest
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

vs = _carregar("validar_sql_oracle")

_so_parse_permitido = _priv(vs, "_so_parse_permitido")
_validate_one = _priv(vs, "_validate_one")

pytestmark = pytest.mark.unitario


def _veredito(classe: str) -> str:
    return json.dumps({"classe": classe, "permitido": False, "motivos": ["x"]})


@pytest.mark.parametrize(
    ("classe", "esperado"),
    [
        ("chamada_funcao", True),
        ("ddl", False),
        ("mutacao", False),
        ("plsql", False),
        ("transacao", False),
        ("chamada_sensivel", False),
    ],
)
def test_so_parse_so_vale_para_funcao_customizada(classe: str, esperado: bool) -> None:
    assert _so_parse_permitido(vs.GUARD_SO_PARSE, _veredito(classe)) is esperado


def test_so_parse_com_json_ilegivel_bloqueia() -> None:
    assert _so_parse_permitido(vs.GUARD_SO_PARSE, "saida truncada {") is False


def test_so_parse_sem_exit_3_nao_decide_nada() -> None:
    assert _so_parse_permitido(vs.GUARD_LIBERADO, "") is True


def _opcoes(arquivo: Path) -> Any:
    return vs.RunOptions(timeout=1, execute=True, explicit_binds={}, guard=arquivo)


def _sem_oracle(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Troca `_oracle_stage` por um espião: a chamada registra e devolve status fixo."""
    chamadas: list[str] = []

    def espiao(sql: str, *_a: Any, **_k: Any) -> dict[str, Any]:
        chamadas.append(sql)
        return {"status": "parse_ok"}

    monkeypatch.setattr(vs, "_oracle_stage", espiao)
    return chamadas


def test_ddl_com_exit_3_bloqueia_sem_chamar_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão (achado 5): o parse de DDL executa o DDL; não pode chegar ao Oracle."""
    f = tmp_path / "a.sql"
    f.write_text("CREATE TABLE t_x (a NUMBER)", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (3, _veredito("ddl")))
    chamadas = _sem_oracle(monkeypatch)

    resultado = _validate_one(f, None, _opcoes(f))

    assert resultado["status"] == "blocked_guard"
    assert not chamadas


def test_dml_com_exit_3_bloqueia_sem_chamar_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("DELETE FROM t_x", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (3, _veredito("mutacao")))
    chamadas = _sem_oracle(monkeypatch)

    assert _validate_one(f, None, _opcoes(f))["status"] == "blocked_guard"
    assert not chamadas


def test_chamada_funcao_com_exit_3_segue_para_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT pkg.fn(1) FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(
        vs, "_guard_texto", lambda _t, _g: (3, _veredito("chamada_funcao"))
    )
    chamadas = _sem_oracle(monkeypatch)

    resultado = _validate_one(f, None, _opcoes(f))

    assert resultado["status"] == "parse_ok"
    assert len(chamadas) == 1


def test_veredito_ilegivel_com_exit_3_bloqueia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT pkg.fn(1) FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (3, "nao e json"))
    chamadas = _sem_oracle(monkeypatch)

    assert _validate_one(f, None, _opcoes(f))["status"] == "blocked_guard"
    assert not chamadas


class _Cursor:
    """Cursor falso: registra o que executa e devolve `linhas` na verificação."""

    def __init__(self, linhas: list[tuple[str, str, str]]) -> None:
        self.linhas = linhas
        self.executados: list[str] = []
        self.description: list[Any] = []
        self.prefetchrows = 0
        self.arraysize = 0

    def parse(self, _sql: str) -> None:
        return None

    def execute(self, sql: str, *_a: Any) -> None:
        self.executados.append(sql)

    def fetchall(self) -> list[tuple[str, str, str]]:
        return self.linhas

    def fetchmany(self, _n: int) -> list[Any]:
        return []

    def close(self) -> None:
        return None


class _Conexao:  # pylint: disable=too-few-public-methods
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor

    def cancel(self) -> None:
        return None


def test_smoke_nao_executa_quando_o_catalogo_acha_funcao() -> None:
    """Regressão (revisão do PR #77): `SELECT PKG.FN FROM DUAL` sai do guard com exit 0;
    a `consulta_verificacao` roda antes do smoke e impede a execução."""
    cursor = _Cursor([("SGTPRD", "PKG", "PACKAGE")])
    resultado = _priv(vs, "_run_with_watchdog")(
        _Conexao(cursor),
        "select pkg.fn from dual",
        5,
        {},
        consulta_verificacao="SELECT verificacao",
    )
    assert resultado["smoke"] == "blocked_custom_function"
    assert "SGTPRD.PKG (PACKAGE)" in resultado["error"]
    assert cursor.executados == ["SELECT verificacao"]


def test_smoke_executa_quando_o_catalogo_nao_acha_funcao() -> None:
    cursor = _Cursor([])
    resultado = _priv(vs, "_run_with_watchdog")(
        _Conexao(cursor),
        "select col from t",
        5,
        {},
        consulta_verificacao="SELECT verificacao",
    )
    assert resultado["smoke"] == "pass"
    assert cursor.executados == ["SELECT verificacao", "select col from t"]


def test_guard_liberado_com_veredito_ilegivel_bloqueia_sem_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem o JSON do guard não há `consulta_verificacao`: não executa (fail-closed)."""
    f = tmp_path / "a.sql"
    f.write_text("SELECT 1 FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (0, "saida truncada {"))
    chamadas = _sem_oracle(monkeypatch)

    assert _validate_one(f, None, _opcoes(f))["status"] == "blocked_guard"
    assert not chamadas


def test_guard_liberado_repassa_a_consulta_de_verificacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT 1 FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    veredito = json.dumps({"classe": "leitura", "consulta_verificacao": "SELECT v"})
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (0, veredito))
    recebidas: list[Any] = []

    def espiao(*_a: Any, **kwargs: Any) -> dict[str, Any]:
        recebidas.append(kwargs.get("consulta"))
        return {"status": "validated"}

    monkeypatch.setattr(vs, "_oracle_stage", espiao)

    assert _validate_one(f, None, _opcoes(f))["status"] == "validated"
    assert recebidas == ["SELECT v"]

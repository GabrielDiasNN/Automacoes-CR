"""Testes unitarios do scanner SQL compartilhado por oracle_catalog e validar_sql_oracle."""

import argparse
import contextlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)
from oracle_queue import OracleQueueTransientError, QueueResult

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
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (4, "x"))
    opts = vs.RunOptions(timeout=1, execute=True, explicit_binds={}, guard=f)
    assert _validate_one(f, None, opts)["status"] == "blocked_guard"


def test_guard_codigo_0_segue_para_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT 1 FROM dual", encoding="utf-8")
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "_guard_texto", lambda _t, _g: (0, "{}"))
    monkeypatch.setattr(vs, "_oracle_stage", lambda *_a, **_k: {"status": "validated"})
    opts = vs.RunOptions(timeout=1, execute=True, explicit_binds={}, guard=f)
    assert _validate_one(f, None, opts)["status"] == "validated"


@pytest.mark.parametrize(
    "where",
    [
        "1=1 AND SGTPRD.PKG_X.GRAVA_LOG('x') IS NULL",
        "1=1 AND SGTPRD.PKG_X.SEQ.NEXTVAL > 0",
    ],
)
def test_sample_where_com_funcao_com_efeito_colateral_e_rejeitado(where: str) -> None:
    # Sem o guard canonico disponivel o resultado tambem e rejeicao (fail-closed).
    assert _priv(oc, "_resolve_sample_where_clause")(where) == (None, False)


def test_guard_recebe_o_texto_executado_pela_entrada_padrao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamada: dict[str, Any] = {}

    @dataclass
    class _Concluido:
        returncode: int = 0
        stdout: str = "{}"
        stderr: str = ""

    def _run_falso(args: list[str], **kwargs: Any) -> _Concluido:
        chamada["args"] = args
        chamada.update(kwargs)
        return _Concluido()

    monkeypatch.setattr(vs.subprocess, "run", _run_falso)
    codigo, _ = _priv(vs, "_guard_texto")("SELECT 'ação' FROM dual", Path("guard.py"))

    assert codigo == 0
    assert chamada["input"] == "SELECT 'ação' FROM dual"
    assert "--arquivo" not in chamada["args"]
    assert "--sql" not in chamada["args"]
    assert chamada["env"]["PYTHONUTF8"] == "1"


def test_hash_do_guard_e_do_texto_executado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.sql"
    f.write_text("SELECT 1 FROM dual\n", encoding="utf-8")
    visto: list[str] = []
    monkeypatch.setattr(vs, "ROOT", tmp_path)

    def _guard_gravador(texto: str, _g: Path) -> tuple[int, str]:
        visto.append(texto)
        return 0, ""

    monkeypatch.setattr(vs, "_guard_texto", _guard_gravador)
    monkeypatch.setattr(vs, "_oracle_stage", lambda *_a: {"status": "validated"})
    opts = vs.RunOptions(timeout=1, execute=True, explicit_binds={}, guard=f)
    resultado = _validate_one(f, None, opts)

    assert visto == ["SELECT 1 FROM dual"]
    assert resultado["guard_input_sha256"] == _priv(vs, "_sha256")(
        b"SELECT 1 FROM dual"
    )


def test_codigos_de_saida_do_guard_sao_nomeados() -> None:
    assert vs.GUARD_LIBERADO == 0
    assert vs.GUARD_SO_PARSE == 3


def test_arquivo_dentro_da_raiz_aceita_raiz_relativa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pasta").mkdir()
    arquivo = tmp_path / "pasta" / "a.sql"
    arquivo.write_text("SELECT 1 FROM dual", encoding="utf-8")

    resolvido = _priv(vs, "_arquivo_dentro_da_raiz")(Path("pasta/a.sql"), Path("pasta"))

    assert resolvido == arquivo.resolve()


def test_rotulo_do_arquivo_fora_do_repositorio_nao_quebra(tmp_path: Path) -> None:
    arquivo = tmp_path / "a.sql"

    assert _priv(vs, "_rotulo_do_arquivo")(arquivo) == str(arquivo).replace("\\", "/")


def test_rotulo_do_arquivo_dentro_do_repositorio_e_relativo() -> None:
    dentro = vs.ROOT / "Tools" / "oracle" / "validar_sql_oracle.py"

    assert (
        _priv(vs, "_rotulo_do_arquivo")(dentro) == "Tools/oracle/validar_sql_oracle.py"
    )


def test_arquivo_fora_da_raiz_relativa_e_rejeitado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pasta").mkdir()
    (tmp_path / "outra").mkdir()
    (tmp_path / "outra" / "b.sql").write_text("SELECT 1 FROM dual", encoding="utf-8")

    with pytest.raises(SystemExit, match="dentro de --root"):
        _priv(vs, "_arquivo_dentro_da_raiz")(Path("outra/b.sql"), Path("pasta"))


_SQL_COM_FUNCAO = "SELECT SGTPRD.PKGBENF0001.FNC_RETORNA_ULT_CONF_OB(1) FROM DUAL"


def test_check_e_explain_aceitam_chamada_de_funcao_so_parse() -> None:
    """Sem execução, chamada de função é o nível 'só parse' do guard, não bloqueio."""
    assert (
        _ensure_select_only(_SQL_COM_FUNCAO, permitir_funcoes=True) == _SQL_COM_FUNCAO
    )


def test_comandos_que_executam_continuam_bloqueando_funcao() -> None:
    with pytest.raises(oc.GuardError, match="chamada a função"):
        _ensure_select_only(_SQL_COM_FUNCAO)


def test_permitir_funcoes_nao_libera_mutacao() -> None:
    with pytest.raises(oc.GuardError):
        _ensure_select_only("SELECT 1 FROM DUAL FOR UPDATE", permitir_funcoes=True)


def test_oracle_catalog_bloqueia_acima_do_limite_de_nomes() -> None:
    colunas = ", ".join(f"C{i}" for i in range(501))
    sql_texto = " ".join(["SELECT", colunas, "FROM DUAL"])
    with pytest.raises(oc.GuardError, match="aceita até 500"):
        _priv(oc, "_preparar_para_execucao")(sql_texto)


def test_oracle_catalog_carrega_canonico_uma_vez_por_preparacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cargas: list[int] = []
    classificacoes: list[int] = []

    class _Guarda:
        LIMITE_NOMES_VERIFICADOS = 500

        @staticmethod
        def load_canonical() -> object:
            cargas.append(1)
            return object()

        @staticmethod
        def patch_canonical(_c: Any) -> Any:
            def _classificar(_sql: str, **_k: Any) -> dict[str, Any]:
                classificacoes.append(1)
                return {
                    "permitido": True,
                    "classe": "leitura",
                    "consulta_verificacao": "SELECT v",
                }

            return SimpleNamespace(classificar=_classificar)

        @staticmethod
        def extrair_consulta_verificacao(v: dict[str, Any]) -> str | None:
            return str(v.get("consulta_verificacao"))

    _priv(oc, "_cache_canonico").clear()
    monkeypatch.setattr(oc, "_carregar_guard", lambda: _Guarda)
    sql, consulta = _priv(oc, "_preparar_para_execucao")("SELECT 1 FROM DUAL")
    assert sql == "SELECT 1 FROM DUAL"
    assert consulta == "SELECT v"
    assert len(cargas) == 1
    assert len(classificacoes) == 1

    _ensure_select_only("SELECT 2 FROM DUAL")
    assert len(cargas) == 1
    assert len(classificacoes) == 2


def test_oracle_catalog_queue_retenta_transitorio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chamadas_exec: list[int] = []

    def exec_falso(*_a: Any, **_k: Any) -> QueueResult:
        chamadas_exec.append(1)
        if len(chamadas_exec) == 1:
            raise OracleQueueTransientError("smb", "queda")
        return QueueResult(columns=["X"], types=["number"], rows=[(1,)])

    monkeypatch.setattr(oc, "verificar_objetos_fila", lambda *_a, **_k: None)
    monkeypatch.setattr(oc, "executar_consulta_fila", exec_falso)
    cols, rows = _priv(oc, "_run_catalog_queue_query")(
        "SELECT 1 FROM DUAL", "SELECT v", "G", "Q"
    )
    assert cols == ["X"] and rows == [(1,)]
    assert len(chamadas_exec) == 2

    chamadas_plan: list[int] = []

    def plan_falso(*_a: Any, **_k: Any) -> tuple[list[str], float]:
        chamadas_plan.append(1)
        if len(chamadas_plan) == 1:
            raise OracleQueueTransientError("smb", "queda")
        return ["PLAN"], 1.0

    sql_file = tmp_path / "q.sql"
    sql_file.write_text("SELECT 1 FROM DUAL\n", encoding="utf-8")
    monkeypatch.setattr(oc, "_resolve_online_creds", lambda: oc.QUEUE_MODE_SENTINEL)
    monkeypatch.setattr(oc, "explicar_plano_fila", plan_falso)
    assert oc.cmd_check(argparse.Namespace(arquivo=str(sql_file))) == 0
    assert len(chamadas_plan) == 2
    chamadas_plan.clear()
    assert oc.cmd_explain(argparse.Namespace(arquivo=str(sql_file))) == 0
    assert len(chamadas_plan) == 2


def test_build_oracle_catalog_deduplica_antes_de_contar_total_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boc = _carregar("build_oracle_catalog")
    db = tmp_path / "schema.db"
    data = boc.CatalogData(
        objects=[
            ("T1", "TABLE", "VALID", 10, None, "Tabela"),
            ("T1", "SYNONYM", "VALID", None, None, "Sinonimo"),
        ],
        columns=[],
        constraints=[],
        constraint_columns=[],
        index_data=boc.IndexData([], []),
        view_deps=[],
        view_source=[],
    )
    _priv(boc, "_write_catalog")(db, "SGTPRD", data)
    monkeypatch.setattr(oc, "CATALOG_PATH", db)
    with contextlib.closing(_priv(oc, "_connect_catalog")()) as conn:
        total_rows = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        meta_total = conn.execute(
            "SELECT value FROM meta WHERE key = 'total_objects'"
        ).fetchone()[0]
    assert total_rows == 1
    assert meta_total == "1"


def test_auditar_acervo_suporta_root_externo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    aa = _carregar("auditar_acervo_sql")
    externo = tmp_path / "fora.sql"
    externo.write_text("SELECT 1 FROM DUAL", encoding="utf-8")
    monkeypatch.setattr(
        aa.subprocess,
        "run",
        lambda *_a, **_k: argparse.Namespace(returncode=1, stdout="", stderr="ok"),
    )
    registro = aa.audit_file(externo, 3, 5)
    assert registro["file"] == externo.as_posix()

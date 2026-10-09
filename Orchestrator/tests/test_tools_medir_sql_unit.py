"""Testes unitarios de Tools/oracle/medir_sql_oracle.py (sem tocar o Oracle)."""

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import oracle_session
import pytest
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

mm = _carregar("medir_sql_oracle")
ce = _carregar("comparar_equivalencia")

_check_runs = _priv(mm, "_check_runs")
_run_with_retry = _priv(mm, "_run_with_retry")
_load_resultado = _priv(ce, "_load")

pytestmark = pytest.mark.unitario


def _opcoes(runs: int = 5, dump: bool = False) -> Any:
    return mm.MeasureOptions(runs=runs, timeout=5, arraysize=10, keep_first_rows=dump)


def _ok(total: float, rows: int = 2) -> dict[str, Any]:
    return {
        "status": "ok",
        "execute_ms": 1.0,
        "total_ms": total,
        "rows": rows,
        "columns": ["A", "B"],
        "types": {"A": "DB_TYPE_NUMBER", "B": "DB_TYPE_VARCHAR"},
        "data": [(1, "x "), (2, "y")],
    }


def _script(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[dict[str, Any]]
) -> list[int]:
    """Substitui `_attempt` por uma fila de resultados; devolve o contador de chamadas."""
    calls: list[int] = []

    def fake(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        return dict(outcomes[len(calls) - 1])

    monkeypatch.setattr(mm, "_attempt", fake)
    return calls


def test_summarize_mediana_e_ruido() -> None:
    resumo = mm.summarize([10.0, 30.0, 12.0, 11.0, 13.0])
    assert resumo == {
        "n": 5,
        "median_ms": 12.0,
        "min_ms": 10.0,
        "max_ms": 30.0,
        "noise_ms": 20.0,
    }


def test_summarize_vazio_e_erro() -> None:
    with pytest.raises(ValueError):
        mm.summarize([])


@pytest.mark.parametrize(
    ("candidata", "esperado"),
    [
        (500.0, "MELHORA"),  # ganho 500 > ruido 50
        (960.0, "NEUTRO"),  # ganho 40 <= ruido 50
        (1040.0, "NEUTRO"),  # piora dentro do ruido
        (1200.0, "PIOR"),  # piora 200 > ruido 50
    ],
)
def test_decide_usa_ruido_como_piso(candidata: float, esperado: str) -> None:
    base = {"median_ms": 1000.0, "noise_ms": 50.0}
    veredito = mm.decide(base, {"median_ms": candidata}, 2.0)
    assert veredito["verdict"] == esperado


def test_decide_ganho_minimo_percentual_vence_ruido_pequeno() -> None:
    base = {"median_ms": 1000.0, "noise_ms": 1.0}
    # ganho de 15 ms passa o ruido (1) mas nao os 2% (20 ms)
    assert mm.decide(base, {"median_ms": 985.0}, 2.0)["verdict"] == "NEUTRO"
    assert mm.decide(base, {"median_ms": 970.0}, 2.0)["verdict"] == "MELHORA"


@pytest.mark.parametrize(
    "mensagem",
    [
        "DatabaseError: ORA-00028: sua sessao foi eliminada",
        "OperationalError: DPY-4011: conexao fechada",
        "DPI-1080: connection was closed by ORA-3113",
        "InterfaceError: DPY-1001: not connected to database DPI-1010: not connected",
    ],
)
def test_is_transient_reconhece_queda_de_rede(mensagem: str) -> None:
    assert mm.is_transient(mensagem)


def test_is_transient_ignora_erro_de_sql_e_cancelamento() -> None:
    assert not mm.is_transient("DatabaseError: ORA-00942: tabela nao existe")
    assert not mm.is_transient("DatabaseError: ORA-01013: cancelado pelo usuario")


@pytest.mark.parametrize("valor", ["2", "4", "1", "0"])
def test_check_runs_rejeita_par_ou_menor_que_tres(valor: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _check_runs(valor)


def test_check_runs_aceita_impar() -> None:
    assert _check_runs("5") == 5


def test_retry_repete_so_em_erro_transitorio(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = _script(
        monkeypatch,
        [{"status": "transient", "error": "ORA-00028"}, _ok(10.0)],
    )
    resultado = _run_with_retry(None, "select 1", {}, _opcoes(), False)
    assert resultado["status"] == "ok"
    assert resultado["attempts"] == 2
    assert len(chamadas) == 2


def test_retry_desiste_apos_o_limite(monkeypatch: pytest.MonkeyPatch) -> None:
    transitorio = {"status": "transient", "error": "ORA-00028"}
    chamadas = _script(monkeypatch, [transitorio] * mm.MAX_ATTEMPTS)
    resultado = _run_with_retry(None, "select 1", {}, _opcoes(), False)
    assert resultado["status"] == "transient"
    assert resultado["attempts"] == mm.MAX_ATTEMPTS
    assert len(chamadas) == mm.MAX_ATTEMPTS


def test_retry_nao_repete_erro_de_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = _script(monkeypatch, [{"status": "error", "error": "ORA-00942"}])
    resultado = _run_with_retry(None, "select 1", {}, _opcoes(), False)
    assert resultado["status"] == "error"
    assert len(chamadas) == 1


def test_measure_resume_so_as_execucoes_validas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _script(
        monkeypatch,
        [_ok(10.0), _ok(12.0), {"status": "timeout"}, _ok(11.0), _ok(13.0)],
    )
    resultado = mm.measure(None, "select 1", {}, _opcoes(5))
    assert resultado["valid_runs"] == 4
    assert resultado["summary"]["median_ms"] == 11.5
    assert resultado["sufficient"] is True
    assert resultado["row_count_stable"] is True


def test_measure_insuficiente_com_menos_de_tres_validas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _script(
        monkeypatch,
        [_ok(10.0), {"status": "timeout"}, {"status": "timeout"}]
        + [{"status": "timeout"}] * 2,
    )
    resultado = mm.measure(None, "select 1", {}, _opcoes(5))
    assert resultado["valid_runs"] == 1
    assert resultado["sufficient"] is False


def test_measure_sem_nenhuma_valida_nao_quebra(monkeypatch: pytest.MonkeyPatch) -> None:
    _script(monkeypatch, [{"status": "error", "error": "ORA-00942"}] * 3)
    resultado = mm.measure(None, "select 1", {}, _opcoes(3))
    assert resultado["summary"] is None
    assert resultado["sufficient"] is False


def test_measure_detecta_contagem_de_linhas_instavel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _script(monkeypatch, [_ok(10.0, rows=2), _ok(11.0, rows=3), _ok(12.0, rows=2)])
    resultado = mm.measure(None, "select 1", {}, _opcoes(3))
    assert resultado["row_count_stable"] is False


def test_measure_guarda_dump_so_da_primeira_boa_e_limpa_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _script(monkeypatch, [{"status": "timeout"}, _ok(10.0), _ok(11.0), _ok(12.0)])
    resultado = mm.measure(None, "select 1", {}, _opcoes(3, dump=True))
    assert resultado["dump"]["columns"] == ["A", "B"]
    assert resultado["dump"]["data"] == [(1, "x "), (2, "y")]
    assert all("data" not in run for run in resultado["runs"])


def test_write_dump_json_e_lido_pelo_comparador(tmp_path: Path) -> None:
    dump = {
        "columns": ["A", "B"],
        "types": {"A": "DB_TYPE_NUMBER", "B": "DB_TYPE_VARCHAR"},
        "data": [(1, "x "), (2, "y")],
    }
    info = mm.write_dump(dump, tmp_path / "saida.json")
    assert info["rows"] == 2 and info["columns"] == 2
    rows, columns, types = _load_resultado(tmp_path / "saida.json")
    assert columns == ["A", "B"]
    assert rows == [{"A": 1, "B": "x"}, {"A": 2, "B": "y"}]
    assert types == {"A": "DB_TYPE_NUMBER", "B": "DB_TYPE_VARCHAR"}


def test_write_dump_csv(tmp_path: Path) -> None:
    dump = {"columns": ["A", "B"], "types": {}, "data": [(1, None)]}
    info = mm.write_dump(dump, tmp_path / "saida.csv")
    assert info["rows"] == 1
    linhas = (tmp_path / "saida.csv").read_text(encoding="utf-8").splitlines()
    assert linhas == ["A,B", "1,"]


def test_write_dump_hash_estavel_e_sensivel_ao_conteudo(tmp_path: Path) -> None:
    base = {"columns": ["A"], "types": {}, "data": [(1,), (2,)]}
    igual = {"columns": ["A"], "types": {}, "data": [(1,), (2,)]}
    outro = {"columns": ["A"], "types": {}, "data": [(1,), (3,)]}
    h1 = mm.write_dump(base, tmp_path / "a.json")["result_hash"]
    h2 = mm.write_dump(igual, tmp_path / "b.json")["result_hash"]
    h3 = mm.write_dump(outro, tmp_path / "c.json")["result_hash"]
    assert h1 == h2 != h3


def test_write_dump_serializa_tipos_nao_json(tmp_path: Path) -> None:
    dump = {
        "columns": ["D", "B"],
        "types": {},
        "data": [(datetime(2026, 9, 29, 8, 30), b"\x01")],
    }
    mm.write_dump(dump, tmp_path / "t.json")
    payload = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert payload["rows"][0]["D"] == "2026-09-29T08:30:00"


class _TipoFalso:  # pylint: disable=too-few-public-methods
    def __init__(self, nome: str) -> None:
        self.name = nome


class _CursorFalso:
    """Cursor mínimo: descrição com nomes repetidos e uma única linha."""

    def __init__(self, nomes: list[str], linhas: list[tuple[Any, ...]]) -> None:
        self.description = [(n, _TipoFalso("DB_TYPE_NUMBER")) for n in nomes]
        self.arraysize = 0
        self.prefetchrows = 0
        self._linhas = linhas

    def execute(self, *_a: Any, **_k: Any) -> None:
        return None

    def fetchmany(self, _n: int) -> list[tuple[Any, ...]]:
        lote, self._linhas = self._linhas, []
        return lote

    def close(self) -> None:
        return None


class _ConexaoFalsa:  # pylint: disable=too-few-public-methods
    def __init__(self, cursor: _CursorFalso) -> None:
        self._cursor = cursor

    def cursor(self) -> _CursorFalso:
        return self._cursor


def test_unique_names_renomeia_repetidas() -> None:
    assert _priv(mm, "_unique_names")(["A", "A", "B", "A"]) == [
        "A",
        "A__2",
        "B",
        "A__3",
    ]


def test_dump_preserva_os_dois_valores_de_colunas_duplicadas(tmp_path: Path) -> None:
    conexao = _ConexaoFalsa(_CursorFalso(["A", "A"], [(1, 2)]))
    lido = _priv(mm, "_timed_fetch")(conexao, "select 1", {}, _opcoes(dump=True), True)
    assert lido["columns"] == ["A", "A__2"]
    assert list(lido["types"]) == ["A", "A__2"]
    mm.write_dump(
        {"columns": lido["columns"], "types": lido["types"], "data": lido["data"]},
        tmp_path / "d.json",
    )
    rows, columns, _ = _load_resultado(tmp_path / "d.json")
    assert columns == ["A", "A__2"]
    assert rows == [{"A": 1, "A__2": 2}]


def test_comparador_detecta_mudanca_na_primeira_coluna_duplicada(
    tmp_path: Path,
) -> None:
    def dump(primeiro: int, caminho: Path) -> Path:
        cur = _CursorFalso(["A", "A"], [(primeiro, 2)])
        lido = _priv(mm, "_timed_fetch")(
            _ConexaoFalsa(cur), "select 1", {}, _opcoes(dump=True), True
        )
        mm.write_dump(
            {"columns": lido["columns"], "types": lido["types"], "data": lido["data"]},
            caminho,
        )
        return caminho

    controle = dump(1, tmp_path / "c.json")
    candidata = dump(9, tmp_path / "n.json")
    rows_c, _, _ = _load_resultado(controle)
    rows_n, _, _ = _load_resultado(candidata)
    assert rows_c != rows_n


def test_explain_plan_negado_nao_derruba_a_medicao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Cursor:  # pylint: disable=too-few-public-methods
        def execute(self, *_a: Any, **_k: Any) -> None:
            raise mm.oracledb.DatabaseError("ORA-01031: privilegios insuficientes")

    class Conexao:
        closed = False

        def cursor(self) -> Cursor:
            return Cursor()

        def close(self) -> None:
            self.closed = True

    conexao = Conexao()
    monkeypatch.setattr(mm.oracledb, "connect", lambda **_k: conexao)
    creds = argparse.Namespace(user=None, password=None, dsn=None)
    plano = mm.explain_plan(creds, "select 1", {})
    assert len(plano) == 1 and plano[0].startswith("plano indisponível")
    assert conexao.closed


def test_baseline_sem_execucoes_validas_sai_com_erro_claro(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"summary": None}), encoding="utf-8")
    alvo = tmp_path / "q.sql"
    alvo.write_text("select 1 from dual", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["medir", str(alvo), "--baseline", str(base)])
    monkeypatch.setattr(mm, "_prepare", lambda _a: ("select 1", {}, None))
    monkeypatch.setattr(
        mm,
        "measure",
        lambda *_a, **_k: {
            "summary": {"median_ms": 1.0, "noise_ms": 0.1, "n": 3},
            "sufficient": True,
            "dump": None,
        },
    )
    with pytest.raises(SystemExit, match="baseline sem execuções válidas"):
        mm.main()


def test_bind_de_data_iso_vira_datetime_e_texto_comum_continua_texto() -> None:
    parse = _priv(sys.modules["validar_sql_oracle"], "_parse_bind_args")
    binds = parse(["dt_inicio=2026-09-01", "ini=2026-09-01 08:30:00", "cod=ABC", "n=7"])
    assert binds["DT_INICIO"] == datetime(2026, 9, 1)
    assert binds["INI"] == datetime(2026, 9, 1, 8, 30)
    assert binds["COD"] == "ABC"
    assert binds["N"] == 7
    assert parse(["x=2026-13-45"])["X"] == "2026-13-45"


def test_lista_de_queda_de_sessao_e_unica_entre_runner_e_ferramentas() -> None:
    validar_partes = _carregar("validar_partes_oracle")
    retryable = _priv(validar_partes, "_retryable")
    for marcador in oracle_session.SESSION_DROP_MARKERS:
        assert mm.is_transient(f"erro {marcador} qualquer")
        assert retryable(RuntimeError(f"erro {marcador} qualquer"))
    assert not retryable(RuntimeError("ORA-00942: tabela nao existe"))


def test_medir_nao_fecha_conexao_de_thread_abandonada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fechadas: list[bool] = []

    class Conexao:  # pylint: disable=too-few-public-methods
        def close(self) -> None:
            fechadas.append(True)

    monkeypatch.setattr(mm.oracledb, "connect", lambda **_k: Conexao())
    creds = argparse.Namespace(user=None, password=None, dsn=None)
    attempt = _priv(mm, "_attempt")

    monkeypatch.setattr(
        mm, "_run_watched", lambda *_a: {"status": "timeout", "abandoned": True}
    )
    # `abandoned` chega ao chamador: o relatório registra a sessão abandonada.
    assert attempt(creds, "select 1", {}, _opcoes(), False) == {
        "status": "timeout",
        "abandoned": True,
    }
    assert not fechadas

    monkeypatch.setattr(mm, "_run_watched", lambda *_a: {"status": "timeout"})
    attempt(creds, "select 1", {}, _opcoes(), False)
    assert fechadas == [True]


def test_validar_nao_fecha_conexao_de_thread_abandonada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vs = sys.modules["validar_sql_oracle"]
    fechadas: list[bool] = []

    class Conexao:  # pylint: disable=too-few-public-methods
        def close(self) -> None:
            fechadas.append(True)

    monkeypatch.setattr(vs, "_connect", lambda _c: Conexao())
    opcoes = argparse.Namespace(execute=True, explicit_binds={}, timeout=1)
    estagio = _priv(vs, "_oracle_stage")

    monkeypatch.setattr(
        vs,
        "_run_with_watchdog",
        lambda *_a: {"parse": "unknown", "smoke": "timeout", "abandoned": True},
    )
    resultado = estagio("select 1 from dual", 0, None, opcoes)
    assert resultado["status"] == "timeout" and "abandoned" not in resultado
    assert not fechadas

    monkeypatch.setattr(
        vs, "_run_with_watchdog", lambda *_a: {"parse": "unknown", "smoke": "timeout"}
    )
    estagio("select 1 from dual", 0, None, opcoes)
    assert fechadas == [True]


def test_validar_parse_sem_execucao_respeita_o_prazo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vs = sys.modules["validar_sql_oracle"]
    liberar = threading.Event()

    class Cursor:  # pylint: disable=too-few-public-methods
        def parse(self, _sql: str) -> None:
            liberar.wait(timeout=5)
            raise RuntimeError("ORA-01013: cancelado")

    class Conexao:
        def cursor(self) -> Cursor:
            return Cursor()

        def cancel(self) -> None:
            liberar.set()

        def close(self) -> None:
            pass

    monkeypatch.setattr(vs, "_connect", lambda _c: Conexao())
    opcoes = argparse.Namespace(execute=False, explicit_binds={}, timeout=0.1)
    resultado = _priv(vs, "_oracle_stage")("select 1 from dual", 0, None, opcoes)
    assert resultado["status"] == "timeout"


def test_validar_conexao_travada_vira_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    vs = sys.modules["validar_sql_oracle"]
    liberar = threading.Event()

    def conecta_devagar(_c: Any) -> Any:
        liberar.wait(timeout=5)
        return argparse.Namespace(close=lambda: None)

    monkeypatch.setattr(vs, "_connect", conecta_devagar)
    opcoes = argparse.Namespace(execute=True, explicit_binds={}, timeout=0.1)
    try:
        resultado = _priv(vs, "_oracle_stage")("select 1 from dual", 0, None, opcoes)
    finally:
        liberar.set()
    assert resultado["status"] == "timeout"

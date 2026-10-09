"""Testes unitários de Tools/oracle/auditar_acervo_sql.py (sem tocar o Oracle)."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

aa = _carregar("auditar_acervo_sql")

_select = _priv(aa, "_select")

pytestmark = pytest.mark.unitario


def _relatorio(
    rows: int = 5,
    median: float = 100.0,
    valid: int = 3,
    stable: bool = True,
) -> dict[str, Any]:
    runs = [{"status": "ok", "rows": rows, "total_ms": median}] * valid
    return {
        "valid_runs": valid,
        "sufficient": valid >= 3,
        "row_count_stable": stable,
        "summary": {"median_ms": median, "noise_ms": 1.0},
        "runs": runs,
    }


@pytest.mark.parametrize(
    ("sql", "esperado"),
    [
        ("SELECT 1 FROM DUAL FETCH FIRST 100 ROWS ONLY", 100),
        ("SELECT 1 FROM DUAL fetch first 5 row only", 5),
        ("SELECT * FROM (SELECT 1 FROM DUAL) WHERE ROWNUM <= 50", 50),
        ("SELECT 1 FROM DUAL", None),
        # cap só em comentário não vale
        ("-- FETCH FIRST 10 ROWS ONLY\nSELECT 1 FROM DUAL", None),
        ("/* ROWNUM <= 3 */ SELECT 1 FROM DUAL", None),
        # com vários, vale o último (SELECT externo)
        (
            "SELECT 1 FROM (SELECT 2 FROM DUAL FETCH FIRST 10 ROWS ONLY) "
            "FETCH FIRST 500 ROWS ONLY",
            500,
        ),
    ],
)
def test_detect_row_cap(sql: str, esperado: int | None) -> None:
    assert aa.detect_row_cap(sql) == esperado


def test_detect_row_cap_ignora_literal_que_parece_teto() -> None:
    sql = "SELECT 'FETCH FIRST 9 ROWS ONLY' AS T FROM DUAL"
    assert aa.detect_row_cap(sql) is None


def test_classify_sem_relatorio_ou_sem_execucao_valida_e_falha() -> None:
    assert aa.classify(None, None) == ["FALHA"]
    assert aa.classify({"valid_runs": 0, "runs": []}, None) == ["FALHA"]


def test_classify_consulta_saudavel_nao_tem_marca() -> None:
    assert aa.classify(_relatorio(rows=10, median=500.0), 100) == []


def test_classify_lenta_acima_de_3s() -> None:
    assert "LENTA" in aa.classify(_relatorio(median=3001.0), None)
    assert "LENTA" not in aa.classify(_relatorio(median=3000.0), None)


def test_classify_vazia() -> None:
    assert aa.classify(_relatorio(rows=0), None) == ["VAZIA"]


def test_classify_teto_atingido_so_quando_linhas_alcancam_o_teto() -> None:
    assert "TETO_ATINGIDO" in aa.classify(_relatorio(rows=100), 100)
    assert "TETO_ATINGIDO" not in aa.classify(_relatorio(rows=99), 100)
    assert "TETO_ATINGIDO" not in aa.classify(_relatorio(rows=100), None)


def test_classify_instavel_com_menos_de_tres_execucoes_validas() -> None:
    assert "INSTAVEL" in aa.classify(_relatorio(valid=2), None)


def test_classify_linhas_instaveis() -> None:
    assert "LINHAS_INSTAVEIS" in aa.classify(_relatorio(stable=False), None)


def test_classify_acumula_marcas() -> None:
    marcas = aa.classify(_relatorio(rows=100, median=4000.0), 100)
    assert marcas == ["LENTA", "TETO_ATINGIDO"]


def test_first_rows_pula_execucoes_com_falha() -> None:
    relatorio = {
        "runs": [{"status": "timeout"}, {"status": "ok", "rows": 7}],
    }
    assert aa.first_rows(relatorio) == 7
    assert aa.first_rows({"runs": [{"status": "timeout"}]}) is None


def test_summarize_flags_conta_ok_e_marcas() -> None:
    registros = [
        {"flags": []},
        {"flags": ["VAZIA"]},
        {"flags": ["LENTA", "TETO_ATINGIDO"]},
        {"flags": []},
    ]
    assert aa.summarize_flags(registros) == {
        "LENTA": 1,
        "OK": 2,
        "TETO_ATINGIDO": 1,
        "VAZIA": 1,
    }


def test_select_ignora_pastas_de_view_e_dml_e_filtra_por_texto(tmp_path: Path) -> None:
    for pasta in ("01_a", "11_views_referencia_sgt", "12_manutencao_dml_restrito"):
        (tmp_path / pasta).mkdir()
        (tmp_path / pasta / f"{pasta}_q.sql").write_text("SELECT 1", encoding="utf-8")
    todos = _select(tmp_path, 1, 1, None)
    assert [p.parent.name for p in todos] == ["01_a"]
    assert _select(tmp_path, 1, 1, "nao_existe") == []


def test_audit_file_sem_relatorio_vira_falha_com_erro_do_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = tmp_path / "q.sql"
    sql.write_text("SELECT 1 FROM DUAL FETCH FIRST 10 ROWS ONLY", encoding="utf-8")
    monkeypatch.setattr(aa, "ROOT", tmp_path)

    def falso(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout="", stderr="guard bloqueou")

    monkeypatch.setattr(aa.subprocess, "run", falso)
    registro = aa.audit_file(sql, 3, 5)
    assert registro["flags"] == ["FALHA"]
    assert registro["row_cap"] == 10
    assert "guard bloqueou" in registro["error"]
    assert registro["file"] == "q.sql"


def test_audit_file_le_o_relatorio_do_medidor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = tmp_path / "q.sql"
    sql.write_text("SELECT 1 FROM DUAL", encoding="utf-8")
    monkeypatch.setattr(aa, "ROOT", tmp_path)

    def falso(comando: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        saida = Path(comando[comando.index("--out") + 1])
        saida.write_text(json.dumps(_relatorio(rows=0, median=12.0)), encoding="utf-8")
        return subprocess.CompletedProcess(comando, 1, stdout="", stderr="")

    monkeypatch.setattr(aa.subprocess, "run", falso)
    registro = aa.audit_file(sql, 3, 5)
    assert registro["flags"] == ["VAZIA"]
    assert registro["median_ms"] == 12.0
    assert registro["rows"] == 0
    assert registro["valid_runs"] == 3


def test_audit_file_timeout_do_medidor_vira_falha_e_nao_aborta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = tmp_path / "q.sql"
    sql.write_text("SELECT 1 FROM DUAL", encoding="utf-8")
    monkeypatch.setattr(aa, "ROOT", tmp_path)

    def estoura(comando: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(comando, 1)

    monkeypatch.setattr(aa.subprocess, "run", estoura)
    registro = aa.audit_file(sql, 3, 5)
    assert registro["flags"] == ["FALHA"]
    assert registro["error"] == "timeout do medidor"
    assert registro["valid_runs"] == 0


def test_varredura_continua_depois_de_um_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "01_a"
    pasta.mkdir()
    for nome in ("a.sql", "b.sql"):
        (pasta / nome).write_text("SELECT 1 FROM DUAL", encoding="utf-8")
    monkeypatch.setattr(aa, "ROOT", tmp_path)

    def falso(comando: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        if comando[2].endswith("a.sql"):
            raise subprocess.TimeoutExpired(comando, 1)
        saida = Path(comando[comando.index("--out") + 1])
        saida.write_text(json.dumps(_relatorio(rows=4)), encoding="utf-8")
        return subprocess.CompletedProcess(comando, 0, stdout="", stderr="")

    monkeypatch.setattr(aa.subprocess, "run", falso)
    destino = tmp_path / "saida.json"
    monkeypatch.setattr(
        sys, "argv", ["auditar", "--root", str(tmp_path), "--out", str(destino)]
    )
    assert aa.main() == 1
    resultados = json.loads(destino.read_text(encoding="utf-8"))["results"]
    assert [r["flags"] for r in resultados] == [["FALHA"], []]


def test_prazo_do_medidor_cobre_todas_as_tentativas() -> None:
    prazo = _priv(aa, "_measurer_deadline")(3, 20)
    pior_caso = 3 * aa.MAX_ATTEMPTS * (20 + 5)
    assert prazo > pior_caso


@pytest.mark.parametrize("valor", ["2", "4", "1"])
def test_runs_par_ou_pequeno_e_recusado_com_erro_de_argumento(
    valor: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["auditar", "--runs", valor, "--out", str(tmp_path / "s.json")]
    )
    with pytest.raises(SystemExit) as saida:
        aa.main()
    assert saida.value.code == 2

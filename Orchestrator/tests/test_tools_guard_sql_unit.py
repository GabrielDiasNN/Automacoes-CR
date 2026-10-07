"""Testes do guard padrão dos validadores: resolução, wrapper de CTE e comando portável."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_TOOLS = Path(__file__).resolve().parents[2] / "Tools" / "oracle"


def _carregar(nome: str) -> ModuleType:
    if str(_TOOLS) not in sys.path:
        sys.path.insert(0, str(_TOOLS))
    spec = importlib.util.spec_from_file_location(nome, _TOOLS / f"{nome}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nome] = module
    spec.loader.exec_module(module)
    return module


wrapper = _carregar("guard_sql")
validador = _carregar("validar_sql_oracle")

_CTE = "WITH x (a) AS (SELECT 1 FROM DUAL) SELECT a FROM x"


def _usar_canonico_falso(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, existe: bool
) -> Path:
    falso = tmp_path / "guard_sql.py"
    if existe:
        falso.write_text("", encoding="utf-8")
    monkeypatch.setattr(wrapper, "canonical_guard_file", lambda: falso)
    monkeypatch.setattr(validador, "canonical_guard_file", lambda: falso)
    return falso


def test_resolve_guard_padrao_e_o_wrapper_versionado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ORACLE_SQL_GUARD", raising=False)
    _usar_canonico_falso(monkeypatch, tmp_path, existe=True)

    assert validador.resolve_guard() == _TOOLS / "guard_sql.py"


def test_resolve_guard_respeita_variavel_de_ambiente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outro = tmp_path / "outro_guard.py"
    outro.write_text("", encoding="utf-8")
    monkeypatch.setenv("ORACLE_SQL_GUARD", str(outro))
    _usar_canonico_falso(monkeypatch, tmp_path / "nada", existe=False)

    assert validador.resolve_guard() == outro


def test_canonico_ausente_e_erro_de_ferramenta_nao_bloqueio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ORACLE_SQL_GUARD", raising=False)
    _usar_canonico_falso(monkeypatch, tmp_path, existe=False)

    with pytest.raises(SystemExit, match="canônico não encontrado"):
        validador.resolve_guard()


def test_variavel_apontando_para_arquivo_inexistente_e_erro_de_ferramenta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ORACLE_SQL_GUARD", str(tmp_path / "nao_existe.py"))

    with pytest.raises(SystemExit, match="não encontrado"):
        validador.resolve_guard()


def test_normalizacao_remove_lista_de_colunas_da_cte() -> None:
    assert wrapper.normalize_cte_column_lists(_CTE).startswith("WITH x AS (SELECT")


def test_normalizacao_nao_toca_chamada_de_funcao() -> None:
    sql = "SELECT TRUNC(SYSDATE) FROM DUAL"

    assert wrapper.normalize_cte_column_lists(sql) == sql


def test_wrapper_sem_canonico_sai_com_erro(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _usar_canonico_falso(monkeypatch, tmp_path / "nada", existe=False)

    assert wrapper.main() == 1
    assert "[ERRO]" in capsys.readouterr().out


def test_wrapper_libera_cte_com_lista_de_colunas_no_canonico_real() -> None:
    canonico = wrapper.canonical_guard_file()
    if not canonico.is_file():
        pytest.skip("guard canônico da skill oracle-sql não instalado nesta máquina")

    classificar: Any = wrapper.patch_canonical(wrapper.load_canonical()).classificar
    analise = classificar(_CTE)

    assert analise["permitido"] is True


def test_comando_da_evidencia_nao_vaza_caminho_absoluto(tmp_path: Path) -> None:
    raiz = validador.ROOT
    argv = [
        str(raiz / "Tools" / "oracle" / "validar_sql_oracle.py"),
        "--file",
        str(raiz / "Produção Beneficimento" / "sql" / "x.sql"),
        "--out",
        str(tmp_path / "saida.json"),
        "--timeout",
        "20",
    ]

    comando = validador.portable_command(argv)

    assert comando[1:] == [
        "Tools/oracle/validar_sql_oracle.py",
        "--file",
        "Produção Beneficimento/sql/x.sql",
        "--out",
        "saida.json",
        "--timeout",
        "20",
    ]
    assert all(":\\" not in parte and not parte.startswith("/") for parte in comando)

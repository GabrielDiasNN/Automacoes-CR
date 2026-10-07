"""Testes de `Tools/oracle/comparar_equivalencia.py`: falsos verdes que o comparador não pode dar."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unitario

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "Tools"
    / "oracle"
    / "comparar_equivalencia.py"
)


def _carregar() -> ModuleType:
    spec = importlib.util.spec_from_file_location("comparar_equivalencia", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ce = _carregar()


def _dataset(rows: list[dict[str, Any]], columns: list[str] | None = None) -> Any:
    cols = columns if columns is not None else (list(rows[0]) if rows else [])
    return (rows, cols, {})


def _spec(**kwargs: Any) -> Any:
    base: dict[str, Any] = {
        "keys": [],
        "metrics": [],
        "columns": [],
        "tolerance": 1e-6,
        "require_non_empty": True,
    }
    base.update(kwargs)
    return ce.CompareSpec(**base)


ROWS = [{"ID": 1, "QTD": 10.0, "COR": "A"}, {"ID": 2, "QTD": 5.0, "COR": "B"}]


def test_identicos_com_chave_sao_equivalentes() -> None:
    assert (
        ce.compare(_dataset(ROWS), _dataset(ROWS), _spec(keys=["id"], metrics=["qtd"]))
        == []
    )


@pytest.mark.parametrize("campo", ["keys", "metrics", "columns"])
def test_coluna_inexistente_nao_e_equivalente(campo: str) -> None:
    resultado = ce.compare(
        _dataset(ROWS),
        _dataset(ROWS),
        _spec(**{"keys": ["ID"], "metrics": ["QTD"], campo: ["NAO_EXISTE"]}),
    )
    assert any("NAO_EXISTE" in item and "não existe" in item for item in resultado)


def test_coluna_inexistente_so_na_candidata() -> None:
    candidata = [{"ID": 1, "COR": "A"}, {"ID": 2, "COR": "B"}]
    resultado = ce.compare(
        _dataset(ROWS), _dataset(candidata), _spec(keys=["ID"], metrics=["QTD"])
    )
    assert any("QTD" in item and "candidata" in item for item in resultado)


def test_metrica_fora_de_colunas_e_comparada() -> None:
    candidata = [{"ID": 1, "QTD": 99.0, "COR": "A"}, {"ID": 2, "QTD": 5.0, "COR": "B"}]
    resultado = ce.compare(
        _dataset(ROWS),
        _dataset(candidata),
        _spec(keys=["ID"], metrics=["QTD"], columns=["COR"]),
    )
    assert any("Valor diverge em QTD" in item for item in resultado)


def test_sem_chaves_mesmas_somas_linhas_diferentes_diverge() -> None:
    controle = [{"COR": "A", "QTD": 1.0}, {"COR": "B", "QTD": 3.0}]
    candidata = [{"COR": "A", "QTD": 2.0}, {"COR": "B", "QTD": 2.0}]
    resultado = ce.compare(
        _dataset(controle), _dataset(candidata), _spec(metrics=["QTD"])
    )
    assert (
        resultado
    ), "somas iguais (4.0) com linhas diferentes não podem ser equivalentes"


def test_sem_chaves_ordem_diferente_e_equivalente() -> None:
    invertida = list(reversed(ROWS))
    assert ce.compare(_dataset(ROWS), _dataset(invertida), _spec(metrics=["QTD"])) == []


def test_sem_chaves_texto_diferente_em_coluna_nao_metrica_diverge() -> None:
    candidata = [{"ID": 1, "QTD": 10.0, "COR": "X"}, {"ID": 2, "QTD": 5.0, "COR": "B"}]
    assert ce.compare(_dataset(ROWS), _dataset(candidata), _spec(metrics=["QTD"]))


def test_texto_em_metrica_diverge_em_vez_de_virar_zero() -> None:
    controle = [{"ID": 1, "QTD": "abc"}]
    candidata = [{"ID": 1, "QTD": 0}]
    for keys in ([], ["ID"]):
        resultado = ce.compare(
            _dataset(controle), _dataset(candidata), _spec(keys=keys, metrics=["QTD"])
        )
        assert any("não numérico" in item for item in resultado)


def test_texto_em_metrica_nos_dois_lados_tambem_diverge() -> None:
    linhas = [{"ID": 1, "QTD": "abc"}]
    resultado = ce.compare(_dataset(linhas), _dataset(linhas), _spec(metrics=["QTD"]))
    assert any("não numérico" in item for item in resultado)


def test_nulo_em_metrica_e_tratado_explicitamente() -> None:
    controle = [{"ID": 1, "QTD": None}]
    assert (
        ce.compare(_dataset(controle), _dataset(controle), _spec(metrics=["QTD"])) == []
    )
    zero = [{"ID": 1, "QTD": 0}]
    assert ce.compare(_dataset(controle), _dataset(zero), _spec(metrics=["QTD"]))


def test_tolerancia_absoluta_pequena_nao_esconde_diferenca() -> None:
    controle = [{"ID": 1, "QTD": 0.00001}]
    candidata = [{"ID": 1, "QTD": 0.00005}]
    assert ce.compare(
        _dataset(controle), _dataset(candidata), _spec(keys=["ID"], metrics=["QTD"])
    )
    # tolerância maior configurada explicitamente aceita.
    assert not ce.compare(
        _dataset(controle),
        _dataset(candidata),
        _spec(keys=["ID"], metrics=["QTD"], tolerance=1e-3),
    )


def test_tolerancia_relativa_separada_da_absoluta() -> None:
    controle = [{"ID": 1, "QTD": 1_000_000.0}]
    candidata = [{"ID": 1, "QTD": 1_000_050.0}]  # 5e-5 relativo, 50 absoluto
    assert ce.compare(
        _dataset(controle), _dataset(candidata), _spec(keys=["ID"], metrics=["QTD"])
    )
    assert not ce.compare(
        _dataset(controle),
        _dataset(candidata),
        _spec(keys=["ID"], metrics=["QTD"], rel_tolerance=1e-4),
    )


def test_tolerancia_relativa_padrao_nao_esconde_milesimo_em_valor_grande() -> None:
    # 1e-9 relativo aceitava 0,0009 kg em 1 milhão; ruído de float é ~1e-14.
    controle = [{"ID": 1, "QTD": 1_000_000.0}]
    assert ce.compare(
        _dataset(controle),
        _dataset([{"ID": 1, "QTD": 1_000_000.0009}]),
        _spec(keys=["ID"], metrics=["QTD"]),
    )
    assert not ce.compare(
        _dataset([{"ID": 1, "QTD": sum([0.01] * 1000)}]),
        _dataset([{"ID": 1, "QTD": 10.0}]),
        _spec(keys=["ID"], metrics=["QTD"]),
    )


def test_coluna_nao_metrica_ignora_formato_csv_versus_json() -> None:
    controle = [{"ID": "1", "QTD": "5", "COD": "5", "DESCR": "ABC "}]
    candidata = [{"ID": 1, "QTD": 5, "COD": 5, "DESCR": "ABC"}]
    assert not ce.compare(
        _dataset(controle), _dataset(candidata), _spec(keys=["ID"], metrics=["QTD"])
    )
    # valor diferente continua divergindo.
    candidata[0]["COD"] = 6
    assert ce.compare(
        _dataset(controle), _dataset(candidata), _spec(keys=["ID"], metrics=["QTD"])
    )


def test_vazio_dos_dois_lados_nao_e_prova_silenciosa() -> None:
    vazio = _dataset([], ["ID", "QTD"])
    assert ce.compare(
        vazio, vazio, _spec(metrics=["QTD"])
    )  # padrão: fixture vazio rejeitado
    assert not ce.compare(vazio, vazio, _spec(metrics=["QTD"], require_non_empty=False))
    assert any("vazios" in aviso for aviso in ce.collect_warnings(vazio, vazio))


def test_cli_coluna_inexistente_sai_com_codigo_1(tmp_path: Path) -> None:
    arquivo = tmp_path / "dados.json"
    arquivo.write_text(json.dumps(ROWS), encoding="utf-8")
    argv = [
        "--controle",
        str(arquivo),
        "--candidata",
        str(arquivo),
        "--metricas",
        "NAO_EXISTE",
    ]
    assert ce.main(argv) == 1
    assert (
        ce.main(
            [
                "--controle",
                str(arquivo),
                "--candidata",
                str(arquivo),
                "--metricas",
                "QTD",
            ]
        )
        == 0
    )

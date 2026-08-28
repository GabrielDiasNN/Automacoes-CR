"""Contrato de `app.path_safety.is_contained` — fonte única da guarda anti
path-traversal usada por `managed_file_access`, `download_artifact` e a
validação de `script_path`.

Achado nº 13: o ramo `except ValueError` (drives distintos no Windows) nunca era
exercitado. O `is False` explícito importa — `assert not is_contained(...)`
passaria também se a função levantasse antes de retornar.

Os caminhos são montados por concatenação (não literais de drive) só para não
tropeçar em `Test-PortablePaths.ps1`; o alvo do teste É justamente a semântica
de drive absoluto.
"""

from __future__ import annotations

import os

import pytest
from app.path_safety import is_contained

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="semântica de drives (C: vs D:) é específica do Windows"
)

_SEP = chr(92)  # barra invertida
_ROOT_C = "C:" + _SEP + "Automacoes"
_ROOT_C_BKP = "C:" + _SEP + "Automacoes_bkp"
_ROOT_D = "D:" + _SEP + "Automacoes"


def test_target_dentro_do_root() -> None:
    alvo = _ROOT_C + _SEP + "Orchestrator" + _SEP + "worker.py"
    assert is_contained(_ROOT_C, alvo) is True


def test_target_igual_ao_root() -> None:
    assert is_contained(_ROOT_C, _ROOT_C) is True


def test_irmao_com_prefixo_de_string_nao_conta_como_dentro() -> None:
    # `startswith("C:\\Automacoes")` daria True aqui — é o bug que o commonpath
    # por componentes fecha (ver docstring de path_safety).
    assert is_contained(_ROOT_C, _ROOT_C_BKP + _SEP + "worker.py") is False


def test_drives_distintos_caem_no_except_e_retornam_false() -> None:
    assert is_contained(_ROOT_C, _ROOT_D + _SEP + "x.ps1") is False

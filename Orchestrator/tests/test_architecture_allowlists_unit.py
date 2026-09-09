"""Trava as allowlists de `Tools/architecture-standard.rules.json` contra órfãs.

`Tools/Test-ArchitectureStandard.ps1` usa duas allowlists para isentar arquivos
das regras `SUBPROCESS_OUTSIDE_RUNTIME_ALLOWLIST` e
`SQLITE_DIRECT_ACCESS_OUTSIDE_DB_LAYER`. O gate cobre bem a direção "arquivo
que usa o padrão e NÃO está na allowlist" — é para isso que ele existe.

A direção contrária não era coberta por nada: uma entrada que não corresponde
a uso algum ("órfã") é invisível para o gate, porque ele só consulta a
allowlist quando já encontrou uma ocorrência. Órfã não é inofensiva — ela
isenta silenciosamente qualquer uso FUTURO naquele caminho, sem revisão. A
revisão de 08/09/2026 encontrou 5 órfãs acumuladas assim: 2 em
`python_subprocess_allowlist` (`routers/automations.py`,
`services/execution_runtime.py`, que nunca importaram `subprocess` em todo o
histórico) e 3 em `python_sqlite_allowlist`. Todas foram removidas, exceto uma
exceção legítima, registrada em `EXCECOES_DOCUMENTADAS` abaixo.

O que este teste NÃO faz: substituir o gate PowerShell. Ele não procura uso
fora da allowlist — essa é a direção que `Test-ArchitectureStandard.ps1` já
cobre, e duplicá-la aqui criaria dois gates divergindo sobre a mesma regra.
Este teste é portável (roda no Linux do CI e na máquina Windows), o que o gate
Pester/PowerShell não é.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_RULES = _RAIZ / "Tools" / "architecture-standard.rules.json"

# Entradas que NÃO usam o padrão literal da regra, mas cuja isenção é
# deliberada e tem justificativa escrita. Manter esta lista curta e sempre
# apontando para onde a razão está registrada — uma entrada aqui sem doc
# correspondente é exatamente a órfã que este teste existe para impedir.
EXCECOES_DOCUMENTADAS = {
    # Camada canônica de banco: manipula a conexão SQLite crua via
    # `dbapi_connection` no listener `set_sqlite_pragma` (PRAGMA journal_mode
    # =WAL, busy_timeout) em vez de `import sqlite3`. A isenção é por design.
    # Razão em `docs/architecture-standard.md`.
    "Orchestrator/app/database.py": "docs/architecture-standard.md",
}

_PADROES = {
    "python_subprocess_allowlist": re.compile(
        r"^\s*(?:import subprocess|from subprocess import)", re.MULTILINE
    ),
    "python_sqlite_allowlist": re.compile(
        r"^\s*(?:import sqlite3|from sqlite3 import)", re.MULTILINE
    ),
}


_ALTERNANCIA = re.compile(r"\(\?:([^)]+)\)")


def _caminhos(allowlist: list[str]) -> list[str]:
    r"""Converte os regex de caminho Windows do rules.json em caminhos POSIX.

    Uma entrada pode usar alternancia para cobrir varios arquivos numa linha
    (`data\\(?:schema|writer|queries)\.py`). Cada ramo vira um caminho — sem
    isso o teste procuraria um arquivo com `(?:...)` literal no nome e falharia
    por defeito proprio, nao por orfa real.
    """
    caminhos: list[str] = []
    for entrada in allowlist:
        cru = (
            entrada.removeprefix("^")
            .removesuffix("$")
            .replace("\\\\", "/")
            .replace("\\.", ".")
        )
        alternancia = _ALTERNANCIA.search(cru)
        if alternancia is None:
            caminhos.append(cru)
            continue
        caminhos.extend(
            cru[: alternancia.start()] + ramo + cru[alternancia.end() :]
            for ramo in alternancia.group(1).split("|")
        )
    return caminhos


def _entradas() -> list[tuple[str, str]]:
    regras = json.loads(_RULES.read_text(encoding="utf-8"))
    return [(nome, caminho) for nome in _PADROES for caminho in _caminhos(regras[nome])]


@pytest.mark.unitario
@pytest.mark.parametrize("allowlist,caminho", _entradas())
def test_entrada_de_allowlist_aponta_para_arquivo_existente(
    allowlist: str, caminho: str
) -> None:
    """Caminho que não existe mais isenta um arquivo fantasma."""
    assert (_RAIZ / caminho).is_file(), (
        f"{allowlist}: '{caminho}' nao existe no repositorio. Entrada morta — "
        f"remova de {_RULES.name} ou corrija o caminho."
    )


@pytest.mark.unitario
@pytest.mark.parametrize("allowlist,caminho", _entradas())
def test_entrada_de_allowlist_isenta_uso_real(allowlist: str, caminho: str) -> None:
    """Entrada que não isenta nada hoje isenta qualquer uso futuro, sem revisão."""
    arquivo = _RAIZ / caminho
    if not arquivo.is_file():
        pytest.skip(
            "coberto por test_entrada_de_allowlist_aponta_para_arquivo_existente"
        )

    if _PADROES[allowlist].search(arquivo.read_text(encoding="utf-8")):
        return

    doc = EXCECOES_DOCUMENTADAS.get(caminho)
    assert doc is not None, (
        f"{allowlist}: '{caminho}' nao usa o padrao que a regra detecta, entao "
        f"a entrada nao isenta nada hoje — mas isentaria qualquer uso futuro "
        f"sem revisao. Remova de {_RULES.name}; se a isencao for deliberada, "
        f"registre a razao numa doc e adicione o caminho a EXCECOES_DOCUMENTADAS."
    )
    assert (
        _RAIZ / doc
    ).is_file(), (
        f"{allowlist}: '{caminho}' e excecao documentada, mas '{doc}' nao existe."
    )

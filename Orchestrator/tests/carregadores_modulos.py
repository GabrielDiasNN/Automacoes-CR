"""Carregadores de módulos por caminho para os testes unitários do Orchestrator.

Os scripts de Tools/oracle e das automações de domínio não são pacotes instaláveis:
os testes os carregam a partir do caminho do arquivo, com `spec_from_file_location`.
Este módulo concentra esse carregamento, que antes estava copiado em cada arquivo
de teste.

Os testes o importam pelo caminho `tests.carregadores_modulos`, o mesmo de
`from tests.conftest import AUTH_HEADERS`: `Orchestrator/` está no `sys.path` pelo
`pythonpath = .` do pytest.ini. Pelo nome curto o mypy --strict não resolve o
módulo, o import vira `Any` e o `no-any-return` reprova os retornos dos wrappers.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

TOOLS_ORACLE = Path(__file__).resolve().parents[2] / "Tools" / "oracle"


def carregar_tool_oracle(nome: str) -> ModuleType:
    """Carrega Tools/oracle/<nome>.py e o registra em sys.modules sob o nome curto."""
    spec = importlib.util.spec_from_file_location(nome, TOOLS_ORACLE / f"{nome}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nome] = module
    spec.loader.exec_module(module)
    return module


def carregar_modulo_automacao(name: str, path: Path) -> ModuleType:
    """Carrega um módulo da automação sob o seu nome canônico.

    O nome importa: validators.py faz `from errors import DadoIncompletoError`, então
    carregar errors.py sob um apelido criaria uma SEGUNDA classe de exceção e o
    pytest.raises nunca casaria com a que validators realmente levanta. Reaproveitar
    sys.modules garante uma instância só por módulo.
    """
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def acessar_privado(modulo: ModuleType, nome: str) -> Any:
    """Acessa membro privado do módulo sob teste sem `protected-access`."""
    return getattr(modulo, nome)

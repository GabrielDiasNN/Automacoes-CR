"""SQL de produção só com tabelas: sem view (VW_*), função de pacote ou agregador próprio.

Regra do responsável (17/10/2026): as automações consultam apenas tabelas indexadas.
Views e funções do ERP escondem regra (o corpo do PKGBENF0001 nem é legível pela conta
de leitura) e o guard_sql não deixa medir a paridade de função. Comentários são ignorados:
eles registram de qual view ou função a regra foi tirada.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unitario

_RAIZ = Path(__file__).resolve().parents[2]
_PASTAS = (
    "Receitas Bloqueadas",
    "Montagem de Terceirizados",
    "Receitas Emitidas",
    "OBs Paradas Fase",
    "OBs Fluxo Sem Tingimento",
    "OBs Restricao Branco",
)
_PROIBIDO = re.compile(
    r"\b(VW_\w+|PKG\w*\s*\.\s*\w+|FNC_\w+|OPTSTRAGG\w*)\b", re.IGNORECASE
)
_COMENTARIO = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)


def _arquivos() -> list[Path]:
    arquivos = [p for pasta in _PASTAS for p in (_RAIZ / pasta).glob("SQL-*.sql")]
    arquivos += list(
        (_RAIZ / "Produção Beneficimento" / "sql" / "templates").glob("*.sql")
    )
    return sorted(arquivos)


def test_ha_sql_de_producao_para_conferir() -> None:
    assert len(_arquivos()) >= 10


@pytest.mark.parametrize("arquivo", _arquivos(), ids=lambda p: p.name)
def test_sql_de_producao_nao_usa_view_nem_funcao(arquivo: Path) -> None:
    sem_comentarios = _COMENTARIO.sub(" ", arquivo.read_text(encoding="utf-8"))
    proibidos = sorted(
        {m.group(1).upper() for m in _PROIBIDO.finditer(sem_comentarios)}
    )
    assert not proibidos, f"{arquivo.name} usa view/função: {proibidos}"

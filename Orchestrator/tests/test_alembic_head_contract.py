"""Contrato entre `ORCHESTRATOR_SCHEMA_VERSION` e o head real do Alembic.

Até 31/07/2026 `run_alembic_migrations` decidia se havia migração a aplicar
comparando o `version_num` do banco com a constante `ORCHESTRATOR_SCHEMA_VERSION`
— nunca com o head do diretório `migrations/versions/`. Adicionar uma migration
sem bumpar a constante fazia o early-return disparar e o `upgrade head` **nunca**
rodar, sem erro algum. `validate_database_schema()` só compara tabelas e colunas,
então migrations de índice, constraint ou backfill de dados passavam
despercebidas.

Não havia nada amarrando as duas pontas: busca por `ScriptDirectory` ou
`get_current_head` no repositório retornava zero ocorrências, e
`ORCHESTRATOR_SCHEMA_VERSION` não aparecia em nenhum teste.

O código agora deriva o head do `ScriptDirectory`, então a constante deixou de
governar a decisão. Ela continua alimentando o diagnóstico de divergência
(`diagnostic_checks.py`), e este teste garante que não fique para trás.
"""

import os

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.constants import ORCHESTRATOR_SCHEMA_VERSION

ORCHESTRATOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_INI = os.path.join(ORCHESTRATOR_DIR, "alembic.ini")


def _script_directory() -> ScriptDirectory:
    cfg = Config(ALEMBIC_INI)
    return ScriptDirectory.from_config(cfg)


@pytest.mark.unitario
def test_constante_acompanha_o_head_real() -> None:
    """A constante declarada precisa ser o head do diretório de migrations."""
    head = _script_directory().get_current_head()
    assert head == ORCHESTRATOR_SCHEMA_VERSION, (
        f"ORCHESTRATOR_SCHEMA_VERSION é '{ORCHESTRATOR_SCHEMA_VERSION}' mas o head "
        f"real das migrations é '{head}'. Atualize a constante em "
        "Orchestrator/app/constants.py ao adicionar uma migration."
    )


@pytest.mark.unitario
def test_existe_exatamente_um_head() -> None:
    """Heads múltiplos significam ramificação não resolvida no histórico.

    Com dois heads, `upgrade head` falha e o startup do Orchestrator quebra.
    """
    heads = _script_directory().get_heads()
    assert len(heads) == 1, (
        f"O diretório de migrations tem {len(heads)} heads ({heads}). "
        "Resolva a ramificação com uma migration de merge."
    )


@pytest.mark.unitario
def test_cadeia_de_revisoes_nao_tem_buraco() -> None:
    """Toda revisão precisa ser alcançável a partir do head."""
    script = _script_directory()
    head = script.get_current_head()
    assert head is not None

    alcancaveis = {rev.revision for rev in script.walk_revisions("base", head)}
    todas = {rev.revision for rev in script.walk_revisions()}
    orfas = todas - alcancaveis
    assert not orfas, (
        f"Revisões inalcançáveis a partir do head: {sorted(orfas)}. "
        "Elas nunca serão aplicadas por `upgrade head`."
    )

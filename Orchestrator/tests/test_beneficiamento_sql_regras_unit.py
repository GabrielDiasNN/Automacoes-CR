"""Regras estáticas dos templates SQL de runtime do Beneficiamento.

``validate_static_sql`` proíbe ``SELECT *`` e janela fixa com ``TRUNC(SYSDATE``
e exige os binds ``:dt_inicio`` e ``:dt_fim`` fora de comentários e de literais.
O pre-commit cobre só ``SELECT *`` (``Tools/Test-SqlPerformance.ps1``); as demais
regras existiam apenas na função, sem chamador. Este teste aplica a função a todo
``*.sql`` do diretório de templates.
"""

import sys
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from beneficiamento import (  # noqa: E402  pylint: disable=wrong-import-position
    settings,
    sql_repository,
)

_TEMPLATES = sorted(settings.SQL_TEMPLATE_DIR.glob("*.sql"))


def test_diretorio_de_templates_tem_ao_menos_um_sql() -> None:
    assert _TEMPLATES, f"Nenhum template .sql em {settings.SQL_TEMPLATE_DIR}"


@pytest.mark.parametrize("template", _TEMPLATES, ids=lambda path: path.name)
def test_template_de_runtime_respeita_regras_estaticas(template: Path) -> None:
    sql = template.read_text(encoding="utf-8")

    assert not sql_repository.validate_static_sql(sql)


def test_regras_estaticas_detectam_violacoes_conhecidas() -> None:
    sql_com_violacoes = "SELECT * FROM t WHERE d >= TRUNC(SYSDATE)"

    assert len(sql_repository.validate_static_sql(sql_com_violacoes)) == 3


BINDS_AUSENTES = "Template deve possuir binds :dt_inicio e :dt_fim."


def _sem_binds_no_codigo(sql: str) -> str:
    """Tira do template as linhas de código que usam os binds; comentários ficam."""
    return "\n".join(
        linha
        for linha in sql.splitlines()
        if linha.lstrip().startswith("--") or ":dt_" not in linha.lower()
    )


@pytest.mark.parametrize("template", _TEMPLATES, ids=lambda path: path.name)
def test_bind_so_em_comentario_do_template_reprova(template: Path) -> None:
    """O cabeçalho cita os binds, mas o filtro de janela saiu do SQL executável."""
    sql = _sem_binds_no_codigo(template.read_text(encoding="utf-8"))

    assert sql_repository.validate_static_sql(sql) == [BINDS_AUSENTES]


def test_bind_so_em_comentario_nao_conta_como_bind() -> None:
    sql = (
        "SELECT a FROM t\n"
        "-- filtro: :dt_inicio e :dt_fim\n"
        "/* :dt_inicio :dt_fim */\n"
        "WHERE d > SYSDATE - 1"
    )

    assert sql_repository.validate_static_sql(sql) == [BINDS_AUSENTES]


@pytest.mark.parametrize(
    "trecho",
    [
        "x = '--'",
        "x = '/* aberto'",
        "x = 'it''s -- ok'",
        "x = q'[it's -- ok]'",
        "\"a--b\" = 1 AND x = 'y'",
    ],
    ids=[
        "traco_duplo",
        "barra_asterisco",
        "aspas_escapadas",
        "q_literal",
        "identificador",
    ],
)
def test_marcador_de_comentario_dentro_de_literal_nao_engole_os_binds(
    trecho: str,
) -> None:
    sql = f"SELECT a FROM t WHERE {trecho} AND d >= :dt_inicio AND d < :dt_fim"

    assert not sql_repository.validate_static_sql(sql)


def test_bind_depois_de_comentario_de_bloco_continua_valendo() -> None:
    sql = (
        "SELECT /*+ MATERIALIZE */ a FROM t /* janela */\n"
        "WHERE d >= :dt_inicio AND d < :dt_fim"
    )

    assert not sql_repository.validate_static_sql(sql)


@pytest.mark.parametrize(
    "where",
    [
        "x = ':dt_inicio' AND y = ':dt_fim'",
        "x = ':dt_inicio' AND d < :dt_fim",
        "d >= :dt_inicio AND x = ':dt_fim'",
        "x = q'[:dt_inicio :dt_fim]'",
    ],
    ids=["ambos_em_literal", "inicio_em_literal", "fim_em_literal", "q_literal"],
)
def test_bind_so_em_literal_nao_conta_como_bind(where: str) -> None:
    sql = f"SELECT a FROM t WHERE {where}"

    assert sql_repository.validate_static_sql(sql) == [BINDS_AUSENTES]


@pytest.mark.parametrize(
    "trecho",
    [
        "x = 'abc AND d >= :dt_inicio AND d < :dt_fim",
        "x = q'[abc AND d >= :dt_inicio AND d < :dt_fim",
    ],
    ids=["aspas_sem_fechamento", "q_literal_sem_fechamento"],
)
def test_literal_sem_fechamento_faz_acusar_bind_ausente(trecho: str) -> None:
    sql = f"SELECT a FROM t WHERE {trecho}"

    assert sql_repository.validate_static_sql(sql) == [BINDS_AUSENTES]


def test_bind_com_sufixo_nao_conta_como_bind() -> None:
    sql = "SELECT a FROM t WHERE d >= :dt_inicio_x AND d < :dt_fim_x"

    assert sql_repository.validate_static_sql(sql) == [BINDS_AUSENTES]


def test_bind_fora_de_literal_conta_mesmo_com_literal_no_sql() -> None:
    sql = "SELECT a FROM t WHERE x = 'abc' AND d >= :dt_inicio AND d < :dt_fim"

    assert not sql_repository.validate_static_sql(sql)

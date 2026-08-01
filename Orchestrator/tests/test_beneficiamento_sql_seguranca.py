"""Contrato de segurança do SQL do Beneficiamento.

Os 13 pontos que o bandit acusa como `B608` foram revisados um a um em
31/07/2026 e todos seguem o mesmo padrão: a cláusula WHERE é concatenada a
partir de fragmentos LITERAIS, e todo valor de request vai por parâmetro (`?`).
Cada ponto ganhou `# nosec B608`.

`nosec` silencia o scanner — quem protege de fato é este arquivo. Se alguém
passar a interpolar um valor de filtro direto no SQL, o bandit continuará
calado e estes testes é que devem reprovar.
"""

from typing import Any

import pytest
from beneficiamento.contracts._queries_common import _build_filtered_where
from beneficiamento.contracts.detail import _target_filter
from beneficiamento.contracts.tingimento import _build_where

# Cargas que só aparecem no SQL se o valor tiver sido interpolado em vez de
# ligado por parâmetro.
_CARGAS = [
    "' OR 1=1 --",
    "'; DROP TABLE fato_producao_historica; --",
    "x' UNION SELECT NULL, NULL --",
    "%'; ATTACH DATABASE 'evil.db' AS evil; --",
]

_CAMPOS_DE_FILTRO = [
    "maquina",
    "fase",
    "turno",
    "alternativo",
    "setor",
    "grupo_fase",
    "tipo_maquina",
    "q",
    "status",
    "reprocesso",
]


def _marcadores(sql: str) -> int:
    return sql.count("?")


@pytest.mark.unitario
@pytest.mark.parametrize("campo", _CAMPOS_DE_FILTRO)
@pytest.mark.parametrize("carga", _CARGAS)
def test_filtro_nunca_entra_no_sql(campo: str, carga: str) -> None:
    where_sql, params = _build_filtered_where({campo: carga}, None, None)

    assert carga not in where_sql, (
        f"O valor do filtro '{campo}' foi interpolado no SQL. O `# nosec B608` "
        "nos call sites pressupõe que isso nunca aconteça."
    )
    assert _marcadores(where_sql) == len(params), (
        "Marcadores e parâmetros divergiram: sinal de que um valor passou a ser "
        "concatenado em vez de ligado."
    )


@pytest.mark.unitario
@pytest.mark.parametrize("carga", _CARGAS)
def test_janela_de_datas_nunca_entra_no_sql(carga: str) -> None:
    where_sql, params = _build_filtered_where({}, carga, None)

    assert carga not in where_sql
    assert _marcadores(where_sql) == len(params)


@pytest.mark.unitario
@pytest.mark.parametrize("carga", _CARGAS)
def test_where_do_tingimento_nunca_recebe_valor(carga: str) -> None:
    where_sql, params = _build_where(carga, None)

    assert carga not in where_sql
    assert _marcadores(where_sql) == len(params)


@pytest.mark.unitario
@pytest.mark.parametrize(
    "target_type", ["produto", "maquina_fase", "fase", "turno", "ob", "inexistente"]
)
@pytest.mark.parametrize("carga", _CARGAS)
def test_target_filter_nunca_recebe_valor(target_type: str, carga: str) -> None:
    """`_target_filter` é concatenado ao WHERE do drill-down."""
    normalized: dict[str, Any] = {
        chave: carga
        for chave in (
            "alternativo",
            "maquina",
            "fase",
            "turno",
            "ob",
            "setor",
            "grupo_fase",
            "tipo_maquina",
            "q",
            "status",
            "reprocesso",
        )
    }

    target_sql, params, _label = _target_filter(
        target_type, {"codigo": carga}, normalized
    )

    assert carga not in target_sql
    assert _marcadores(target_sql) == len(params)


@pytest.mark.unitario
def test_where_base_e_estavel_sem_filtros() -> None:
    """Guarda contra os testes acima passarem por devolverem SQL vazio."""
    where_sql, params = _build_filtered_where({}, None, None)
    assert where_sql == "1=1"
    assert not params


@pytest.mark.unitario
def test_filtros_validos_produzem_marcadores() -> None:
    """Guarda: os filtros legítimos continuam gerando cláusula parametrizada."""
    where_sql, params = _build_filtered_where(
        {"maquina": "TIN-01", "fase": "TINGIMENTO"}, "2026-07-01", "2026-07-31"
    )
    assert _marcadores(where_sql) == 4
    assert len(params) == 4
    assert "TIN-01" in params

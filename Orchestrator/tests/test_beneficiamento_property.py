"""Testes de propriedade (hypothesis) para as funções puras de beneficiamento/core/."""

import os
import statistics
import sys

from hypothesis import given, strategies as st

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "Produção Beneficimento",
        "src",
    ),
)

from beneficiamento.core.coercion import (  # noqa: E402  pylint: disable=wrong-import-position
    round_or_zero,
    safe_text,
    to_float,
)
from beneficiamento.core.metrics import (  # noqa: E402  pylint: disable=wrong-import-position
    time_efficiency,
    weighted_average,
)
from beneficiamento.core.schema import (  # noqa: E402  pylint: disable=wrong-import-position
    first_present,
)
from beneficiamento.core.shifts import (  # noqa: E402  pylint: disable=wrong-import-position
    normalize_shift,
)

_FINITE_FLOAT = st.floats(allow_nan=False, allow_infinity=False, width=64)


@given(_FINITE_FLOAT)
def test_to_float_reconstroi_qualquer_float_finito(valor: float) -> None:
    assert to_float(valor) == valor


@given(st.text())
def test_to_float_texto_arbitrario_nunca_lanca_excecao(texto: str) -> None:
    resultado = to_float(texto)
    assert isinstance(resultado, float)


@given(st.one_of(st.none(), st.just("")))
def test_to_float_none_ou_vazio_retorna_zero(valor: str | None) -> None:
    assert to_float(valor) == 0.0


@given(st.text(min_size=1, max_size=50).filter(lambda s: s.strip()))
def test_safe_text_nunca_vazio_quando_ha_conteudo_apos_strip(texto: str) -> None:
    assert safe_text(texto) != ""


@given(st.one_of(st.none(), st.just(""), st.just("   ")))
def test_safe_text_fallback_sem_valor(valor: str | None) -> None:
    assert safe_text(valor) == "SEM_VALOR"


@given(
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12),
    st.integers(min_value=0, max_value=6),
)
def test_round_or_zero_e_deterministico_e_bate_com_round_nativo(
    valor: float, digits: int
) -> None:
    assert round_or_zero(valor, digits) == round_or_zero(valor, digits)
    assert round_or_zero(valor, digits) == round(float(valor), digits)


def test_round_or_zero_none_retorna_zero() -> None:
    assert round_or_zero(None) == 0.0


@given(
    st.floats(min_value=0.01, max_value=1e6, allow_nan=False),
    st.floats(min_value=0.01, max_value=1e6, allow_nan=False),
)
def test_time_efficiency_sempre_nao_negativo(min_prev: float, min_real: float) -> None:
    assert time_efficiency(min_prev, min_real) >= 0.0


@given(st.floats(min_value=-1e6, max_value=0, allow_nan=False))
def test_time_efficiency_min_real_nao_positivo_retorna_zero(min_real: float) -> None:
    assert time_efficiency(10.0, min_real) == 0.0


@given(
    st.lists(
        st.one_of(
            st.none(),
            st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
        ),
        max_size=20,
    )
)
def test_weighted_average_ignora_none_e_bate_com_fmean(
    valores: list[float | None],
) -> None:
    resultado = weighted_average(valores, 4)
    usaveis = [v for v in valores if v is not None]
    if not usaveis:
        assert resultado is None
    else:
        assert resultado == round(statistics.fmean(usaveis), 4)


@given(st.text(min_size=1, max_size=20))
def test_normalize_shift_com_turno_prod_preenchido_nunca_retorna_id_none(
    turno: str,
) -> None:
    turno_id, _ = normalize_shift({"TURNO_PROD": turno})
    if turno.strip():
        assert turno_id is not None
    else:
        assert turno_id is None


def test_normalize_shift_sem_dados_retorna_ambos_none() -> None:
    assert normalize_shift({}) == (None, None)


@given(
    st.dictionaries(
        st.sampled_from(["A", "B", "C"]), st.one_of(st.none(), st.integers())
    )
)
def test_first_present_retorna_o_primeiro_valor_nao_none(
    record: dict[str, int | None],
) -> None:
    resultado = first_present(record, ("A", "B", "C"))
    esperado = next(
        (record.get(f) for f in ("A", "B", "C") if record.get(f) is not None), None
    )
    assert resultado == esperado

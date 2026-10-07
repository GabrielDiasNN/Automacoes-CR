"""O SQL de runtime do Beneficiamento precisa existir no caminho configurado."""

import sys
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from beneficiamento import (  # noqa: E402  pylint: disable=wrong-import-position
    settings,
)


@pytest.mark.parametrize("periodo", settings.PERIOD_ORDER)
def test_template_de_cada_periodo_existe_no_disco(periodo: str) -> None:
    config = settings.get_period_config(periodo)
    template = settings.SQL_TEMPLATE_DIR / config.sql_template

    assert template.is_file(), (
        f"Template do período '{periodo}' ausente: {template}. O runner de produção "
        "depende dele; se o acervo foi reorganizado, ajuste settings.SQL_TEMPLATE_DIR."
    )


def test_template_nao_esta_vazio() -> None:
    config = settings.get_period_config("diario")
    texto = (settings.SQL_TEMPLATE_DIR / config.sql_template).read_text(
        encoding="utf-8"
    )

    assert ":dt_inicio" in texto and ":dt_fim" in texto

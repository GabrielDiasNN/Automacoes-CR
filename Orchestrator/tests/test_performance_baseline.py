# pylint: disable=protected-access
"""Baseline de performance (pytest-benchmark) — job não-bloqueante no CI.

Não afirma limites de tempo via assert (a tolerância de hardware varia entre
runners); os resultados são apenas registrados via --benchmark-json para
detectar regressões ao longo do tempo (comparação manual/externa ao CI).
"""

import os
import sys
from typing import Any

import pytest
from app import schemas
from app.services import portfolio_catalog as pc
from app.services.system_diagnostics import build_diagnostics_payload
from app.services.system_runtime import get_worker_status

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "python"
    ),
)

from oracle_extract import (  # noqa: E402  pylint: disable=wrong-import-position
    serialize_rows,
)


class _FakeScheduler:  # pylint: disable=too-few-public-methods
    running = True

    def get_jobs(self) -> list[Any]:
        return []


@pytest.mark.benchmark
def test_bench_system_diagnostics_build_payload(
    benchmark: Any, db_session: Any
) -> None:
    resultado = benchmark(
        build_diagnostics_payload,
        db_session,
        _FakeScheduler(),
        get_worker_status,
        include_history=False,
    )
    assert isinstance(resultado, dict)


@pytest.mark.benchmark
def test_bench_portfolio_catalog_build_summary(benchmark: Any) -> None:
    itens = [
        schemas.PortfolioHealthItem(
            catalog_id=f"CAT-{i}",
            name=f"Automação {i}",
            slug=f"automacao-{i}",
            criticality=["critical", "high", "medium", "low"][i % 4],
            runtime="powershell",
            docs_status="complete" if i % 5 else "missing",
            drift_count=i % 3,
        )
        for i in range(500)
    ]
    resultado = benchmark(pc._build_portfolio_summary, itens)
    assert resultado.total_items == 500


@pytest.mark.benchmark
def test_bench_schedule_parse(benchmark: Any) -> None:
    payload = (
        '{"schedule_version": 2, "schedule_type": "cron", '
        '"cron_expression": "30 7,13 * * 1-5", "timezone": "America/Sao_Paulo"}'
    )
    resultado = benchmark(schemas.parse_schedule, payload)
    assert resultado is not None
    assert resultado["schedule_type"] == "cron"


@pytest.mark.benchmark
def test_bench_oracle_extract_serialize_rows_1000(benchmark: Any) -> None:
    columns = ["NUMERO_OB", "QT_KG", "DESCR_ITEM"]
    rows = [(f"90{i:04d}", float(i), f"  Produto {i}  ") for i in range(1000)]

    resultado = benchmark(serialize_rows, columns, rows)
    assert len(resultado) == 1000

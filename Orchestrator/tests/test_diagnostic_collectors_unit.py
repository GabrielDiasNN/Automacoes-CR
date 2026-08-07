"""Testes unitários de app/services/diagnostic_collectors.py.

Cobre o achado de performance #9 (revisão de `[1.3.34]`): três coletores
faziam `join` com `Automation` só para filtrar, sem eager loading da
relação — o acesso a `.automation.name`/`.automation.sla_minutes` dentro do
loop de formatação disparava um SELECT lazy por linha. Corrigido com
`contains_eager(models.Execution.automation)`, reaproveitando o `join` já
existente.

Cada teste conta as queries SQL de fato emitidas (via hook
`before_cursor_execute` no `test_engine`) para duas execuções de automações
distintas: com o eager load correto, a busca inteira é 1 única query. Sem
`contains_eager` (regressão), o acesso a `.automation` por linha reintroduz
1 query adicional por automação distinta — o teste reprova.
"""

from datetime import timedelta
from typing import Any

from app import models, schemas
from app.constants import EXECUTION_STATUS_RUNNING
from app.services import diagnostic_collectors as dc
from app.timezone import get_now_local
from conftest import test_engine
from sqlalchemy import event


def _contar_queries(fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, list[str]]:
    """Executa `fn` contando as queries SQL emitidas no `test_engine`."""
    statements: list[str] = []

    def _listener(
        _conn: Any, _cursor: Any, statement: str, _params: Any, _ctx: Any, _many: Any
    ) -> None:
        statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", _listener)
    try:
        resultado = fn(*args, **kwargs)
    finally:
        event.remove(test_engine, "before_cursor_execute", _listener)
    return resultado, statements


def _duas_automacoes_com_execucao_running(
    db_session: Any,
) -> tuple[models.Automation, models.Automation]:
    auto_a = models.Automation(
        name="Automacao Diagnostico A",
        script_path="./test/run.ps1",
        max_runtime_minutes=5,
        sla_minutes=10,
    )
    auto_b = models.Automation(
        name="Automacao Diagnostico B",
        script_path="./test/run.ps1",
        max_runtime_minutes=5,
        sla_minutes=10,
    )
    db_session.add_all([auto_a, auto_b])
    db_session.flush()
    return auto_a, auto_b


def test_collect_running_over_runtime_nao_faz_lazy_load_por_automacao(
    db_session: Any,
) -> None:
    auto_a, auto_b = _duas_automacoes_com_execucao_running(db_session)
    started = get_now_local() - timedelta(minutes=30)
    db_session.add_all(
        [
            models.Execution(
                id="RUN_A",
                automation_id=auto_a.id,
                status=EXECUTION_STATUS_RUNNING,
                started_at=started,
                claimed_at=started,
            ),
            models.Execution(
                id="RUN_B",
                automation_id=auto_b.id,
                status=EXECUTION_STATUS_RUNNING,
                started_at=started,
                claimed_at=started,
            ),
        ]
    )
    db_session.commit()

    resultado, statements = _contar_queries(dc.collect_running_over_runtime, db_session)

    assert {item["automation_name"] for item in resultado} == {
        "Automacao Diagnostico A",
        "Automacao Diagnostico B",
    }
    assert len(statements) == 1, (
        "esperada 1 unica query (join com contains_eager); "
        f"obteve {len(statements)}: {statements}"
    )


def test_collect_orphaned_running_nao_faz_lazy_load_por_automacao(
    db_session: Any,
) -> None:
    auto_a, auto_b = _duas_automacoes_com_execucao_running(db_session)
    db_session.add_all(
        [
            models.Execution(
                id="ORPH_A",
                automation_id=auto_a.id,
                status=EXECUTION_STATUS_RUNNING,
                started_at=get_now_local(),
            ),
            models.Execution(
                id="ORPH_B",
                automation_id=auto_b.id,
                status=EXECUTION_STATUS_RUNNING,
                started_at=get_now_local(),
            ),
        ]
    )
    db_session.commit()

    # worker offline: todo RUNNING vira orfao, garantindo que o loop acesse
    # `.automation.name` para as duas linhas (duas automacoes distintas).
    worker_status = schemas.WorkerStatus(is_alive=False)

    resultado, statements = _contar_queries(
        dc.collect_orphaned_running, db_session, worker_status
    )

    assert {item["automation_name"] for item in resultado} == {
        "Automacao Diagnostico A",
        "Automacao Diagnostico B",
    }
    assert len(statements) == 1, (
        "esperada 1 unica query (join com contains_eager); "
        f"obteve {len(statements)}: {statements}"
    )


def test_collect_sla_breaches_nao_faz_lazy_load_por_automacao(
    db_session: Any,
) -> None:
    auto_a, auto_b = _duas_automacoes_com_execucao_running(db_session)
    finished = get_now_local() - timedelta(hours=1)
    db_session.add_all(
        [
            models.Execution(
                id="SLA_A",
                automation_id=auto_a.id,
                status="SUCCESS",
                finished_at=finished,
                duration_seconds=900.0,  # 15min > sla_minutes(10)
            ),
            models.Execution(
                id="SLA_B",
                automation_id=auto_b.id,
                status="SUCCESS",
                finished_at=finished,
                duration_seconds=900.0,
            ),
        ]
    )
    db_session.commit()

    resultado, statements = _contar_queries(
        dc.collect_sla_breaches, db_session, get_now_local()
    )

    assert {item["automation_name"] for item in resultado} == {
        "Automacao Diagnostico A",
        "Automacao Diagnostico B",
    }
    assert len(statements) == 1, (
        "esperada 1 unica query (join com contains_eager); "
        f"obteve {len(statements)}: {statements}"
    )

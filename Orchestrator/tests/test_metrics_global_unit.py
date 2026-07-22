"""Testes de consistência das contagens globais/por-automação de erro (metrics.py)."""

from typing import Any

from app import models
from app.services.metrics import (
    build_global_metrics_response,
    get_global_execution_counts,
)
from app.timezone import get_now_local


def _make_automation(db_session: Any) -> int:
    auto = models.Automation(name="Metrics Global Auto", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    return int(auto.id)


def test_get_global_execution_counts_conta_timeout_e_terminated_como_erro(
    db_session: Any,
) -> None:
    # TIMEOUT/TERMINATED/FAILED_BY_REBOOT são status terminais de falha
    # (EXECUTION_FAILED_STATUSES) e precisam entrar na contagem de erros global,
    # assim como já entram em get_failure_hotspots_24h e get_automation_metrics_24h.
    automation_id = _make_automation(db_session)
    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_GLOBAL_1",
                automation_id=automation_id,
                status="ERROR",
                started_at=now,
            ),
            models.Execution(
                id="EXEC_GLOBAL_2",
                automation_id=automation_id,
                status="TIMEOUT",
                started_at=now,
            ),
            models.Execution(
                id="EXEC_GLOBAL_3",
                automation_id=automation_id,
                status="TERMINATED",
                started_at=now,
            ),
            models.Execution(
                id="EXEC_GLOBAL_4",
                automation_id=automation_id,
                status="SUCCESS",
                started_at=now,
            ),
        ]
    )
    db_session.commit()

    total, success, errors, pending = get_global_execution_counts(db_session)

    assert total == 4
    assert success == 1
    assert errors == 3
    assert pending == 0


def test_build_global_metrics_response_total_errors_por_automacao_inclui_timeout(
    db_session: Any,
) -> None:
    automation_id = _make_automation(db_session)
    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_GLOBAL_5",
                automation_id=automation_id,
                status="ERROR",
                started_at=now,
            ),
            models.Execution(
                id="EXEC_GLOBAL_6",
                automation_id=automation_id,
                status="TIMEOUT",
                started_at=now,
            ),
        ]
    )
    db_session.commit()

    response = build_global_metrics_response(db_session)

    assert response.summary.error_count == 2
    auto_metric = next(
        a for a in response.automations if a.name == "Metrics Global Auto"
    )
    assert auto_metric.total_errors == 2

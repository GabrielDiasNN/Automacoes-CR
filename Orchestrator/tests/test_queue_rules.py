"""
Suite de testes focado em regras de fila, retry e concorrência (Fase 5.2).

Valida:
1. Requeue respeitando o limite do queue_group ativo.
2. Limite de retries baseado em max_retries.
3. Classificação operacional de falhas através de exit codes conhecidos.
"""

from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.constants import (
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PARTIAL,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    FAILURE_REASON_CHANNEL_DELIVERY_FAILED,
    FAILURE_REASON_WHATSAPP_SESSION_EXPIRED,
    RECOVERY_ACTION_REAUTHENTICATE_WHATSAPP_SESSION,
    RECOVERY_ACTION_REVIEW_CHANNEL_STATE_BEFORE_REQUEUE,
)
from app.services.execution_runtime import claim_next_task, classify_process_result


def test_classify_process_result() -> None:
    """Valida que exit codes conhecidos são classificados com precisão técnica."""
    # Exit code 21 -> WhatsApp Session Expired
    status, reason, action = classify_process_result(21)
    assert status == EXECUTION_STATUS_ERROR
    assert reason == FAILURE_REASON_WHATSAPP_SESSION_EXPIRED
    assert action == RECOVERY_ACTION_REAUTHENTICATE_WHATSAPP_SESSION

    # Exit code 24 -> Channel Delivery Failed (entrega parcial: e-mail OK, WhatsApp falhou).
    # Classificado como PARTIAL para não disparar alerta crítico nem penalizar SLA,
    # preservando o motivo e a ação de recuperação do canal.
    status, reason, action = classify_process_result(24)
    assert status == EXECUTION_STATUS_PARTIAL
    assert reason == FAILURE_REASON_CHANNEL_DELIVERY_FAILED
    assert action == RECOVERY_ACTION_REVIEW_CHANNEL_STATE_BEFORE_REQUEUE

    # Exit code desconhecido (ex: 5) -> Erro Genérico
    status, reason, action = classify_process_result(5)
    assert status == EXECUTION_STATUS_ERROR
    assert reason == "EXIT_CODE_5"


def test_requeue_respects_queue_group(client: TestClient, db_session: Session) -> None:
    """Garante que requeue manual falha (409) se já existir execução ativa no mesmo grupo."""
    # Criar automação A de teste com queue_group 'grupo_a'
    auto1 = models.Automation(
        id=901,
        name="Automacao Grupo A1",
        script_path="Orchestrator/tests/test/run1.ps1",
        queue_group="grupo_a",
        max_retries=3,
        enabled=True,
    )
    # Criar automação B de teste no mesmo queue_group 'grupo_a'
    auto2 = models.Automation(
        id=909,
        name="Automacao Grupo A2",
        script_path="Orchestrator/tests/test/run1.ps1",
        queue_group="grupo_a",
        max_retries=3,
        enabled=True,
    )
    db_session.add(auto1)
    db_session.add(auto2)
    db_session.commit()

    # Criar execução original que falhou para Automacao A
    exec_source = models.Execution(
        id="SRC_001",
        automation_id=901,
        status="ERROR",
        retry_count=0,
        max_retries=3,
        queue_group="grupo_a",
    )
    db_session.add(exec_source)

    # Criar execução concorrente ativa no mesmo grupo para Automacao B
    exec_active = models.Execution(
        id="ACT_001",
        automation_id=909,
        status=EXECUTION_STATUS_RUNNING,
        retry_count=0,
        max_retries=3,
        queue_group="grupo_a",
    )
    db_session.add(exec_active)
    db_session.commit()

    # Tentar dar requeue na execução original
    response = client.post(
        "/api/executions/SRC_001/requeue",
        headers=AUTH_HEADERS,
        json={"requested_by": "TestOperator", "reason": "Teste de concorrência"},
    )
    assert response.status_code == 409
    assert (
        "Já existe uma execução ativa no mesmo grupo operacional"
        in response.json()["detail"]
    )


def test_requeue_enforces_max_retries(client: TestClient, db_session: Session) -> None:
    """Garante que o requeue falha (409) se a contagem de retry atingir o limite max_retries."""
    # Criar automação de teste com limite de 2 retries
    auto = models.Automation(
        id=902,
        name="Automacao Retry Limit",
        script_path="Orchestrator/tests/test/run1.ps1",
        max_retries=2,
        enabled=True,
    )
    db_session.add(auto)
    db_session.commit()

    # Criar execução original que já atingiu o limite de retry (retry_count=2, max_retries=2)
    exec_source = models.Execution(
        id="SRC_002",
        automation_id=902,
        status="ERROR",
        retry_count=2,
        max_retries=2,
    )
    db_session.add(exec_source)
    db_session.commit()

    # Tentar dar requeue na execução original (deverá falhar porque 2 + 1 > 2)
    response = client.post(
        "/api/executions/SRC_002/requeue",
        headers=AUTH_HEADERS,
        json={"requested_by": "TestOperator", "reason": "Teste de limite retry"},
    )
    assert response.status_code == 409
    assert "Limite de retry excedido" in response.json()["detail"]


def test_claim_next_task_skips_blocked_queue_group(db_session: Session) -> None:
    auto_blocked = models.Automation(
        id=910,
        name="Automacao Bloqueada",
        script_path="Orchestrator/tests/test/run1.ps1",
        queue_group="grupo_claim",
        enabled=True,
    )
    auto_free = models.Automation(
        id=911,
        name="Automacao Livre",
        script_path="Orchestrator/tests/test/run1.ps1",
        queue_group="grupo_livre",
        enabled=True,
    )
    db_session.add_all([auto_blocked, auto_free])
    db_session.flush()
    db_session.add(
        models.Execution(
            id="RUNNING_GROUP",
            automation_id=910,
            status=EXECUTION_STATUS_RUNNING,
            queue_group="grupo_claim",
        )
    )
    db_session.add(
        models.Execution(
            id="PENDING_BLOCKED",
            automation_id=910,
            status=EXECUTION_STATUS_PENDING,
            priority="HIGH",
            queue_group="grupo_claim",
        )
    )
    db_session.add(
        models.Execution(
            id="PENDING_FREE",
            automation_id=911,
            status=EXECUTION_STATUS_PENDING,
            priority="NORMAL",
            queue_group="grupo_livre",
        )
    )
    db_session.commit()

    claimed = claim_next_task(
        db_session,
        worker_instance_id="worker-test",
        worker_pid=4321,
    )
    assert claimed == "PENDING_FREE"

    claimed_row = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == "PENDING_FREE")
        .first()
    )
    assert claimed_row is not None
    assert claimed_row.status == EXECUTION_STATUS_RUNNING
    assert claimed_row.worker_instance_id == "worker-test"
    assert claimed_row.worker_pid == 4321

    blocked_row = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == "PENDING_BLOCKED")
        .first()
    )
    assert blocked_row is not None
    assert blocked_row.status == EXECUTION_STATUS_PENDING

"""Regressoes do contrato de fila entre Orchestrator e Worker."""

import time
from typing import Any

from app import models
from app.middleware import RATE_LIMIT_EXEMPT_PATHS
from app.services.execution_runtime import (
    apply_internal_worker_error,
    apply_timeout_result,
    complete_process_execution,
    finalize_reboot_interrupted_task,
    mark_running_tasks_as_failed_by_reboot,
    mark_task_as_failed,
)
from app.timezone import get_now_local
from worker import _finalize_terminated_task, claim_next_task, classify_process_result


def _add_execution(
    db_session: Any, exec_id: str, automation_id: Any, priority: str = "NORMAL"
) -> None:
    db_session.add(
        models.Execution(
            id=exec_id,
            automation_id=automation_id,
            status="PENDING",
            priority=priority,
            requested_by="TEST",
            started_at=get_now_local(),
        )
    )


def test_claim_next_task_marks_only_one_pending_execution(db_session: Any) -> None:
    auto = models.Automation(name="Worker Claim", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()

    _add_execution(db_session, "EXEC_LOW", auto.id, "LOW")
    _add_execution(db_session, "EXEC_HIGH", auto.id, "HIGH")
    _add_execution(db_session, "EXEC_NORMAL", auto.id, "NORMAL")
    db_session.commit()

    claimed = claim_next_task(db_session)

    assert claimed == "EXEC_HIGH"
    statuses = {
        row.id: row.status
        for row in db_session.query(models.Execution)
        .order_by(models.Execution.id)
        .all()
    }
    assert statuses == {
        "EXEC_HIGH": "RUNNING",
        "EXEC_LOW": "PENDING",
        "EXEC_NORMAL": "PENDING",
    }


def test_worker_long_poll_endpoint_is_not_rate_limit_exempt() -> None:
    assert "/api/system/wait-for-task" not in RATE_LIMIT_EXEMPT_PATHS


def _app_com_rate_limit(rpm: int) -> Any:
    """App mínimo com o endpoint de long-poll e uma janela de rate limit nova."""
    from app.middleware import (  # pylint: disable=import-outside-toplevel
        RateLimitMiddleware,
    )
    from fastapi import FastAPI  # pylint: disable=import-outside-toplevel

    app_teste = FastAPI()

    @app_teste.get("/api/system/wait-for-task")
    def _wait() -> dict[str, str]:
        return {"status": "timeout"}

    app_teste.add_middleware(RateLimitMiddleware, rpm=rpm)
    return app_teste


def test_wait_for_task_isento_do_rate_limit_via_loopback() -> None:
    """O Worker não pode competir pelo bucket de 127.0.0.1 com o Dashboard.

    O long-poll é reenviado continuamente pelo Worker; sem isenção ele consome o
    bucket do IP de loopback, que é o mesmo do Dashboard servido no mesmo host.
    """
    from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
        TestClient,
    )

    with TestClient(_app_com_rate_limit(1), client=("127.0.0.1", 5000)) as c:
        assert c.get("/api/system/wait-for-task").status_code == 200
        assert c.get("/api/system/wait-for-task").status_code == 200


def test_wait_for_task_continua_limitado_fora_do_loopback() -> None:
    """A isenção é restrita ao socket de loopback.

    Cada long-poll prende um worker por até 30s: liberá-lo para qualquer origem
    seria um vetor de exaustão barato. Por isso o path fica em
    INTERNAL_LOOPBACK_PATHS e não em RATE_LIMIT_EXEMPT_PATHS.
    """
    from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
        TestClient,
    )

    with TestClient(_app_com_rate_limit(1), client=("10.0.0.5", 5000)) as c:
        assert c.get("/api/system/wait-for-task").status_code == 200
        assert c.get("/api/system/wait-for-task").status_code == 429


def test_finalize_terminated_task_persists_terminal_metadata(db_session: Any) -> None:
    auto = models.Automation(name="Worker Stop", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_STOP",
            automation_id=auto.id,
            status="RUNNING",
            requested_by="TEST",
            started_at=get_now_local(),
            logs="pre-stop\n",
        )
    )
    db_session.commit()

    _finalize_terminated_task(
        db_session,
        "EXEC_STOP",
        ["runtime log\n"],
        time.monotonic() - 3,
    )

    stopped = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == "EXEC_STOP")
        .first()
    )
    assert stopped.status == "TERMINATED"
    assert stopped.exit_code == -15
    assert stopped.duration_seconds >= 3
    assert stopped.failure_reason == "USER_TERMINATED"
    assert stopped.recovery_action == "REVIEW_LOGS_BEFORE_REQUEUE"
    assert "runtime log" in stopped.logs
    assert "[INTERROMPIDO PELO USUARIO]" in stopped.logs


def test_classify_process_result_identifies_channel_recovery_actions() -> None:
    assert classify_process_result(0) == ("SUCCESS", None, "NONE")
    assert classify_process_result(2) == ("SUCCESS", None, "NONE")
    assert classify_process_result(21) == (
        "ERROR",
        "WHATSAPP_SESSION_EXPIRED",
        "REAUTHENTICATE_WHATSAPP_SESSION",
    )
    assert classify_process_result(24) == (
        "PARTIAL",
        "CHANNEL_DELIVERY_FAILED",
        "REVIEW_CHANNEL_STATE_BEFORE_REQUEUE",
    )
    assert classify_process_result(99) == (
        "ERROR",
        "EXIT_CODE_99",
        "REVIEW_LOGS_AND_OPTIONALLY_REQUEUE",
    )


def test_execution_runtime_marks_missing_automation_failure(db_session: Any) -> None:
    auto = models.Automation(name="Missing Script", script_path="./missing.ps1")
    db_session.add(auto)
    db_session.flush()
    _add_execution(db_session, "EXEC_MISSING", auto.id)
    db_session.commit()

    mark_task_as_failed(db_session, "EXEC_MISSING", "api_key=super-secret")

    failed = db_session.query(models.Execution).filter_by(id="EXEC_MISSING").first()
    assert failed.status == "ERROR"
    assert failed.exit_code == -1
    assert failed.failure_reason == "AUTOMATION_NOT_FOUND"
    assert failed.recovery_action == "REVIEW_AUTOMATION_REGISTRY"
    assert "api_key=********" in failed.logs
    assert failed.finished_at is not None


def test_execution_runtime_applies_timeout_result(db_session: Any) -> None:
    auto = models.Automation(name="Timeout Script", script_path="./timeout.ps1")
    db_session.add(auto)
    db_session.flush()
    _add_execution(db_session, "EXEC_TIMEOUT", auto.id)
    db_session.commit()

    result = apply_timeout_result(
        db_session,
        "EXEC_TIMEOUT",
        ["partial log"],
        time.time() - 2,
    )

    assert result is not None
    assert result.status == "TIMEOUT"
    assert result.failure_reason == "MAX_RUNTIME_EXCEEDED"
    assert result.recovery_action == "REVIEW_TIMEOUT_AND_REQUEUE"
    assert "Tarefa excedeu" in result.logs


def test_execution_runtime_completes_process_execution(db_session: Any) -> None:
    auto = models.Automation(name="Complete Script", script_path="./complete.ps1")
    db_session.add(auto)
    db_session.flush()
    _add_execution(db_session, "EXEC_COMPLETE", auto.id)
    db_session.commit()

    result = complete_process_execution(
        db_session,
        "EXEC_COMPLETE",
        return_code=24,
        logs=["token=abc12345"],
        artifacts_json='{"file":"out.txt"}',
        duration_seconds=3.5,
    )

    assert result is not None
    assert result.status == "PARTIAL"
    assert result.failure_reason == "CHANNEL_DELIVERY_FAILED"
    assert result.recovery_action == "REVIEW_CHANNEL_STATE_BEFORE_REQUEUE"
    assert result.artifacts == '{"file":"out.txt"}'
    assert "token=********" in result.logs


def test_execution_runtime_internal_error_skips_terminal_execution(
    db_session: Any,
) -> None:
    auto = models.Automation(name="Terminal Script", script_path="./terminal.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_TERMINAL",
            automation_id=auto.id,
            status="TIMEOUT",
            requested_by="TEST",
            started_at=get_now_local(),
            logs="already terminal",
        )
    )
    db_session.commit()

    apply_internal_worker_error(
        db_session,
        "EXEC_TERMINAL",
        "password=should-not-append",
        time.time() - 1,
    )

    terminal = db_session.query(models.Execution).filter_by(id="EXEC_TERMINAL").first()
    assert terminal.status == "TIMEOUT"
    assert terminal.logs == "already terminal"


def test_execution_runtime_marks_running_tasks_failed_by_reboot(
    db_session: Any,
) -> None:
    auto = models.Automation(name="Running Script", script_path="./running.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_RUNNING_REBOOT",
            automation_id=auto.id,
            status="RUNNING",
            requested_by="TEST",
            started_at=get_now_local(),
            logs="before reboot",
            # Desde 31/07/2026 o recovery só alcança execuções COM dono
            # registrado: é o que distingue uma órfã de worker morto de uma
            # telemetria externa viva (que não tem worker_instance_id).
            worker_instance_id="worker-1",
            worker_pid=4242,
        )
    )
    db_session.commit()

    count = mark_running_tasks_as_failed_by_reboot(db_session)

    rebooted = (
        db_session.query(models.Execution).filter_by(id="EXEC_RUNNING_REBOOT").first()
    )
    assert count >= 1
    assert rebooted.status == "FAILED_BY_REBOOT"
    assert rebooted.failure_reason == "ORCHESTRATOR_REBOOT"
    assert rebooted.recovery_action == "REQUEUE_IF_SAFE"
    assert "[RECOVERY_AUDIT]" in rebooted.logs
    # Era o único finalizador que não gravava duração, deixando buracos na série.
    assert rebooted.duration_seconds is not None


def test_recovery_preserva_execucao_sem_dono(db_session: Any) -> None:
    """Regressão: telemetria externa não pode ser marcada como reboot.

    `POST /api/executions/telemetry/start` grava RUNNING sem
    `worker_instance_id`, disparada por um terminal externo. Antes, qualquer
    reinício da API a carimbava como interrompida por reboot enquanto o processo
    real seguia rodando — e o `/telemetry/end` depois sobrescrevia o status,
    produzindo histórico contraditório.
    """
    auto = models.Automation(name="Telemetria Externa", script_path="./tel.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="TEL_SEM_DONO",
            automation_id=auto.id,
            status="RUNNING",
            requested_by="TERMINAL",
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    mark_running_tasks_as_failed_by_reboot(db_session)

    preservada = db_session.query(models.Execution).filter_by(id="TEL_SEM_DONO").first()
    assert preservada.status == "RUNNING", (
        "Execução sem worker_instance_id foi marcada como FAILED_BY_REBOOT — "
        "o recovery de boot não deve tocar em execuções que não são dele."
    )
    assert preservada.finished_at is None


def test_finalize_reboot_interrupted_task_persists_reboot_metadata(
    db_session: Any,
) -> None:
    auto = models.Automation(name="Shutdown Helper", script_path="./run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_SHUTDOWN_HELPER",
            automation_id=auto.id,
            status="RUNNING",
            requested_by="TEST",
            started_at=get_now_local(),
            logs="antes do shutdown\n",
        )
    )
    db_session.commit()

    finalize_reboot_interrupted_task(
        db_session,
        "EXEC_SHUTDOWN_HELPER",
        ["log em andamento\n"],
        time.monotonic() - 4,
    )

    row = (
        db_session.query(models.Execution).filter_by(id="EXEC_SHUTDOWN_HELPER").first()
    )
    assert row.status == "FAILED_BY_REBOOT"
    assert row.exit_code == -1
    assert row.failure_reason == "ORCHESTRATOR_REBOOT"
    assert row.recovery_action == "REQUEUE_IF_SAFE"
    assert row.duration_seconds >= 4
    assert row.finished_at is not None
    assert "[INTERROMPIDO POR SHUTDOWN DO ORQUESTRADOR]" in row.logs
    assert "actor=WORKER_SHUTDOWN" in row.logs


def test_finalize_reboot_interrupted_task_skips_terminal_execution(
    db_session: Any,
) -> None:
    auto = models.Automation(name="Shutdown Terminal", script_path="./run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_SHUTDOWN_TERMINAL",
            automation_id=auto.id,
            status="TERMINATED",
            requested_by="TEST",
            started_at=get_now_local(),
            logs="já terminado",
        )
    )
    db_session.commit()

    finalize_reboot_interrupted_task(
        db_session,
        "EXEC_SHUTDOWN_TERMINAL",
        ["não deve anexar"],
        time.monotonic() - 1,
    )

    row = (
        db_session.query(models.Execution)
        .filter_by(id="EXEC_SHUTDOWN_TERMINAL")
        .first()
    )
    assert row.status == "TERMINATED"
    assert row.logs == "já terminado"

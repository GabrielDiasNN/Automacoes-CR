# pylint: disable=all
# mypy: ignore-errors
"""Contrato operacional compartilhado de execução."""

import os
import subprocess
import time
import uuid
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import case
from sqlalchemy.orm import Session

from .. import models
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_TERMINATED,
    EXECUTION_STATUS_TIMEOUT,
    FAILURE_REASON_AUTOMATION_NOT_FOUND,
    FAILURE_REASON_CHANNEL_DELIVERY_FAILED,
    FAILURE_REASON_INTERNAL_WORKER_ERROR,
    FAILURE_REASON_MAX_RUNTIME_EXCEEDED,
    FAILURE_REASON_ORCHESTRATOR_REBOOT,
    FAILURE_REASON_USER_TERMINATED,
    FAILURE_REASON_WHATSAPP_SESSION_EXPIRED,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    RECOVERY_ACTION_NONE,
    RECOVERY_ACTION_REAUTHENTICATE_WHATSAPP_SESSION,
    RECOVERY_ACTION_REQUEUE_IF_SAFE,
    RECOVERY_ACTION_REQUEUE_MANUAL,
    RECOVERY_ACTION_REQUEUED_TO_NEW_EXECUTION,
    RECOVERY_ACTION_REVIEW_AUTOMATION_REGISTRY,
    RECOVERY_ACTION_REVIEW_CHANNEL_STATE_BEFORE_REQUEUE,
    RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE,
    RECOVERY_ACTION_REVIEW_LOGS_BEFORE_REQUEUE,
    RECOVERY_ACTION_REVIEW_TIMEOUT_AND_REQUEUE,
    RECOVERY_ACTION_REVIEW_WORKER_LOGS,
    EXIT_CODE_MAP,
)
from ..timezone import get_now_local
from ..security import sanitize_log_payload, truncate_log_payload
from ..middleware import request_id_var


def generate_execution_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"


def build_queued_execution(
    automation: models.Automation,
    exec_id: str,
    requested_by: str,
    priority: str = PRIORITY_NORMAL,
    retry_count: int = 0,
    max_retries: Optional[int] = None,
    failure_reason: Optional[str] = None,
    recovery_action: str = RECOVERY_ACTION_NONE,
) -> models.Execution:
    correlation_id = request_id_var.get("SYSTEM")
    return models.Execution(
        id=exec_id,
        automation_id=automation.id,
        status=EXECUTION_STATUS_PENDING,
        priority=priority,
        retry_count=retry_count,
        max_retries=(
            max_retries if max_retries is not None else (automation.max_retries or 0)
        ),
        queue_group=automation.queue_group,
        requested_by=requested_by,
        failure_reason=failure_reason,
        recovery_action=recovery_action,
        logs=f"[TRACE] correlation_id={correlation_id} event=QUEUED requested_by={requested_by}",
    )


def resolve_script_path(project_root: str, script_path: str) -> str:
    path = script_path
    if path.startswith("./") or path.startswith(".\\"):
        path = os.path.join(project_root, path[2:])
    elif not os.path.isabs(path):
        path = os.path.join(project_root, path)
    return os.path.abspath(path)


def get_group_active_execution(
    db: Session,
    queue_group: Optional[str],
    exclude_automation_id: Optional[int] = None,
) -> Optional[models.Execution]:
    if not queue_group:
        return None

    query = (
        db.query(models.Execution)
        .join(models.Automation, models.Automation.id == models.Execution.automation_id)
        .filter(
            models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)),
            models.Automation.queue_group == queue_group,
        )
    )
    if exclude_automation_id is not None:
        query = query.filter(models.Automation.id != exclude_automation_id)
    return query.order_by(models.Execution.started_at.desc()).first()


def _has_running_execution_for_group(
    db: Session,
    queue_group: Optional[str],
) -> bool:
    if not queue_group:
        return False
    return (
        db.query(models.Execution.id)
        .filter(
            models.Execution.status == EXECUTION_STATUS_RUNNING,
            models.Execution.queue_group == queue_group,
        )
        .first()
        is not None
    )


def claim_next_task(
    db: Session,
    worker_instance_id: Optional[str] = None,
    worker_pid: Optional[int] = None,
) -> Optional[str]:
    priority_rank = case(
        (models.Execution.priority == PRIORITY_HIGH, 0),
        (models.Execution.priority == PRIORITY_NORMAL, 1),
        (models.Execution.priority == PRIORITY_LOW, 2),
        else_=1,
    )
    candidates = (
        db.query(models.Execution)
        .filter(models.Execution.status == EXECUTION_STATUS_PENDING)
        .order_by(priority_rank.asc(), models.Execution.started_at.asc())
        .limit(25)
        .all()
    )
    if not candidates:
        return None

    for candidate in candidates:
        if _has_running_execution_for_group(db, candidate.queue_group):
            continue

        claimed_at = get_now_local()
        updated = (
            db.query(models.Execution)
            .filter(
                models.Execution.id == candidate.id,
                models.Execution.status == EXECUTION_STATUS_PENDING,
            )
            .update(
                {
                    models.Execution.status: EXECUTION_STATUS_RUNNING,
                    models.Execution.started_at: claimed_at,
                    models.Execution.claimed_at: claimed_at,
                    models.Execution.worker_instance_id: worker_instance_id,
                    models.Execution.worker_pid: worker_pid,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if updated == 1:
            return candidate.id
    return None


def classify_process_result(
    return_code: Optional[int],
) -> tuple[str, Optional[str], str]:
    if return_code in EXIT_CODE_MAP:
        return EXIT_CODE_MAP[return_code]
    return (
        EXECUTION_STATUS_ERROR,
        f"EXIT_CODE_{return_code}",
        RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE,
    )


def mark_task_as_failed(
    db: Session,
    exec_id: str,
    message: str,
    exit_code: int = -1,
) -> None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        return
    db_exec.status = EXECUTION_STATUS_ERROR
    db_exec.logs = truncate_log_payload((db_exec.logs or "") + sanitize_log_payload(message))
    db_exec.exit_code = exit_code
    db_exec.failure_reason = FAILURE_REASON_AUTOMATION_NOT_FOUND
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_AUTOMATION_REGISTRY
    db_exec.finished_at = get_now_local()
    if db_exec.started_at and db_exec.finished_at:
        db_exec.duration_seconds = round(
            (db_exec.finished_at - db_exec.started_at).total_seconds(), 2
        )
    db.commit()


def finalize_terminated_task(
    db: Session,
    exec_id: str,
    logs: list[str],
    task_start_ts: float,
) -> None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        return
    termination_log = "\n[INTERROMPIDO PELO USUARIO]\n"
    db_exec.status = EXECUTION_STATUS_TERMINATED
    db_exec.exit_code = -15
    db_exec.duration_seconds = round(time.time() - task_start_ts, 2)
    db_exec.finished_at = get_now_local()
    db_exec.failure_reason = FAILURE_REASON_USER_TERMINATED
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_LOGS_BEFORE_REQUEUE
    db_exec.logs = truncate_log_payload(
        sanitize_log_payload((db_exec.logs or "") + "".join(logs) + termination_log)
    )
    db.commit()


def apply_timeout_result(
    db: Session,
    exec_id: str,
    logs: list[str],
    task_start_ts: float,
) -> Optional[models.Execution]:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        return None
    db_exec.status = EXECUTION_STATUS_TIMEOUT
    db_exec.finished_at = get_now_local()
    db_exec.duration_seconds = round(time.time() - task_start_ts, 2)
    db_exec.failure_reason = FAILURE_REASON_MAX_RUNTIME_EXCEEDED
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_TIMEOUT_AND_REQUEUE
    db_exec.logs = truncate_log_payload(
        sanitize_log_payload("".join(logs) + "\n[ERRO] Tarefa excedeu o tempo máximo.")
    )
    db.commit()
    return db_exec


def complete_process_execution(
    db: Session,
    exec_id: str,
    return_code: Optional[int],
    logs: list[str],
    artifacts_json: Optional[str],
    duration_seconds: float,
) -> Optional[models.Execution]:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec or db_exec.status in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        return db_exec

    status, failure_reason, recovery_action = classify_process_result(return_code)
    db_exec.exit_code = return_code
    db_exec.duration_seconds = duration_seconds
    db_exec.status = status
    db_exec.failure_reason = failure_reason
    db_exec.recovery_action = recovery_action
    db_exec.logs = truncate_log_payload(sanitize_log_payload("".join(logs)))
    db_exec.artifacts = artifacts_json
    db_exec.finished_at = get_now_local()
    db.commit()
    return db_exec


def apply_internal_worker_error(
    db: Session,
    exec_id: str,
    message: str,
    task_start_ts: float,
) -> None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec or db_exec.status in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        return
    db_exec.status = EXECUTION_STATUS_ERROR
    db_exec.logs = truncate_log_payload(
        (db_exec.logs or "") + f"\nInternal Worker Error: {sanitize_log_payload(message)}"
    )
    db_exec.exit_code = -1
    db_exec.failure_reason = FAILURE_REASON_INTERNAL_WORKER_ERROR
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_WORKER_LOGS
    db_exec.finished_at = get_now_local()
    db_exec.duration_seconds = round(time.time() - task_start_ts, 2)
    db.commit()


def mark_running_tasks_as_failed_by_reboot(db: Session) -> int:
    zombies = (
        db.query(models.Execution)
        .filter(models.Execution.status == EXECUTION_STATUS_RUNNING)
        .all()
    )
    for task in zombies:
        now = get_now_local()
        task.status = "FAILED_BY_REBOOT"
        task.finished_at = now
        task.failure_reason = FAILURE_REASON_ORCHESTRATOR_REBOOT
        task.recovery_action = RECOVERY_ACTION_REQUEUE_IF_SAFE
        reboot_audit_line = (
            f"[RECOVERY_AUDIT] actor=SYSTEM_STARTUP "
            f"action=MARK_FAILED_BY_REBOOT timestamp={now.strftime('%d/%m/%Y %H:%M:%S')}"
        )
        task.logs = (
            (task.logs or "")
            + "\n[REBOOT] Interrompida."
            + f"\n{reboot_audit_line}"
        )
    db.commit()
    return len(zombies)

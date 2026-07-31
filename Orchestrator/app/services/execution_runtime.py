"""Contrato operacional compartilhado de execução."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, cast

from sqlalchemy import case
from sqlalchemy.orm import Session

from .. import models
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_ALLOWED_PRIORITIES,
    EXECUTION_QUEUEABLE_SOURCE_STATUSES,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_FAILED_BY_REBOOT,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_REQUEUED,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_TERMINATED,
    EXECUTION_STATUS_TIMEOUT,
    EXIT_CODE_MAP,
    FAILURE_REASON_AUTOMATION_NOT_FOUND,
    FAILURE_REASON_INTERNAL_WORKER_ERROR,
    FAILURE_REASON_MAX_RUNTIME_EXCEEDED,
    FAILURE_REASON_ORCHESTRATOR_REBOOT,
    FAILURE_REASON_USER_TERMINATED,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    RECOVERY_ACTION_NONE,
    RECOVERY_ACTION_REQUEUE_IF_SAFE,
    RECOVERY_ACTION_REQUEUE_MANUAL,
    RECOVERY_ACTION_REQUEUED_TO_NEW_EXECUTION,
    RECOVERY_ACTION_REVIEW_AUTOMATION_REGISTRY,
    RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE,
    RECOVERY_ACTION_REVIEW_LOGS_BEFORE_REQUEUE,
    RECOVERY_ACTION_REVIEW_TIMEOUT_AND_REQUEUE,
    RECOVERY_ACTION_REVIEW_WORKER_LOGS,
)
from ..middleware import request_id_var
from ..security import sanitize_log_payload, truncate_log_payload
from ..timezone import get_now_local


def generate_execution_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"


def build_queued_execution(  # pylint: disable=too-many-arguments
    automation: models.Automation,
    exec_id: str,
    requested_by: str,
    *,
    priority: str = PRIORITY_NORMAL,
    retry_count: int = 0,
    max_retries: int | None = None,
    failure_reason: str | None = None,
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
    queue_group: str | None,
    exclude_automation_id: int | None = None,
) -> models.Execution | None:
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
    queue_group: str | None,
) -> bool:
    """Existe execução RUNNING no grupo, pelo valor ATUAL da automação?

    FONTE ÚNICA (31/07/2026): filtra por `Automation.queue_group`, igual a
    `get_group_active_execution`. Até então esta função filtrava por
    `Execution.queue_group` — cópia congelada no enfileiramento por
    `build_queued_execution` —, enquanto os guards HTTP e o scheduler já usavam
    o valor atual da automação. Depois de um `PUT /api/automations/{id}` que
    alterasse o grupo, as execuções PENDING já na fila carregavam o valor
    antigo: o worker serializava por um grupo e a API por outro, e duas
    automações que deveriam ser mutuamente exclusivas (grupo `hub-global`, que
    compartilha uma única sessão WhatsApp) podiam rodar em paralelo.

    O predicado de status aqui é só RUNNING, e não `EXECUTION_ACTIVE_STATUSES`
    como em `get_group_active_execution`: esta função decide se um candidato
    PENDING pode ser reivindicado, e incluir PENDING faria todo candidato
    bloquear a si mesmo. A divergência é deliberada.
    """
    if not queue_group:
        return False
    return (
        db.query(models.Execution.id)
        .join(models.Automation, models.Automation.id == models.Execution.automation_id)
        .filter(
            models.Execution.status == EXECUTION_STATUS_RUNNING,
            models.Automation.queue_group == queue_group,
        )
        .first()
        is not None
    )


def claim_next_task(
    db: Session,
    worker_instance_id: str | None = None,
    worker_pid: int | None = None,
) -> str | None:
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
        # Grupo ATUAL da automação, não o congelado em `candidate.queue_group`.
        # `Execution.queue_group` permanece gravado como registro histórico
        # ("sob qual grupo isto foi enfileirado"), mas nenhuma decisão de
        # concorrência o consulta — ver `_has_running_execution_for_group`.
        grupo_atual = cast(str | None, candidate.automation.queue_group)
        if _has_running_execution_for_group(db, grupo_atual):
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
                    # `started_at` continua marcando o INÍCIO DA EXECUÇÃO — é
                    # assim que as métricas o leem. O instante do enfileiramento,
                    # que este UPDATE destruía, vive em `queued_at` desde a
                    # migration 20260731_02; o tempo de fila é
                    # `started_at - queued_at`.
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
            return cast(str, candidate.id)
    return None


def classify_process_result(
    return_code: int | None,
) -> tuple[str, str | None, str]:
    if return_code in EXIT_CODE_MAP:
        return EXIT_CODE_MAP[return_code]
    return (
        EXECUTION_STATUS_ERROR,
        f"EXIT_CODE_{return_code}",
        RECOVERY_ACTION_REVIEW_LOGS_AND_OPTIONALLY_REQUEUE,
    )


def mark_task_as_failed(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    exec_id: str,
    message: str,
    exit_code: int = -1,
    failure_reason: str | None = None,
    recovery_action: str | None = None,
) -> None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        return
    db_exec.status = EXECUTION_STATUS_ERROR  # type: ignore[assignment]
    db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
        str(db_exec.logs or "") + sanitize_log_payload(message)
    )
    db_exec.exit_code = exit_code  # type: ignore[assignment]
    db_exec.failure_reason = failure_reason or FAILURE_REASON_AUTOMATION_NOT_FOUND  # type: ignore[assignment]
    db_exec.recovery_action = recovery_action or RECOVERY_ACTION_REVIEW_AUTOMATION_REGISTRY  # type: ignore[assignment]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    if db_exec.started_at and db_exec.finished_at:
        delta_seconds = round(
            (
                cast(Any, db_exec.finished_at) - cast(Any, db_exec.started_at)
            ).total_seconds(),
            2,
        )
        db_exec.duration_seconds = max(0.0, delta_seconds)  # type: ignore[arg-type]
    db.commit()


def finalize_terminated_task(
    db: Session,
    exec_id: str,
    logs: list[str],
    task_start_monotonic: float,
) -> None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        return
    termination_log = "\n[INTERROMPIDO PELO USUARIO]\n"
    db_exec.status = EXECUTION_STATUS_TERMINATED  # type: ignore[assignment]
    db_exec.exit_code = -15  # type: ignore[assignment]
    db_exec.duration_seconds = round(time.monotonic() - task_start_monotonic, 2)  # type: ignore[arg-type]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    db_exec.failure_reason = FAILURE_REASON_USER_TERMINATED  # type: ignore[assignment]
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_LOGS_BEFORE_REQUEUE  # type: ignore[assignment]
    db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
        sanitize_log_payload(str(db_exec.logs or "") + "".join(logs) + termination_log)
    )
    db.commit()


def finalize_reboot_interrupted_task(
    db: Session,
    exec_id: str,
    logs: list[str],
    task_start_monotonic: float,
) -> None:
    """Finaliza uma execução interrompida por shutdown do orquestrador.

    Mesma semântica de mark_running_tasks_as_failed_by_reboot (recovery no
    startup), porém aplicada de forma síncrona no próprio worker durante o
    graceful shutdown: evita a execução ficar presa em RUNNING na janela entre
    o encerramento e o próximo boot. Idempotente para status já terminais.
    """
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec or db_exec.status in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        return
    now = get_now_local()
    interruption_log = "\n[INTERROMPIDO POR SHUTDOWN DO ORQUESTRADOR]\n"
    reboot_audit_line = (
        f"[RECOVERY_AUDIT] actor=WORKER_SHUTDOWN "
        f"action=MARK_FAILED_BY_REBOOT timestamp={now.strftime('%d/%m/%Y %H:%M:%S')}"
    )
    db_exec.status = EXECUTION_STATUS_FAILED_BY_REBOOT  # type: ignore[assignment]
    db_exec.exit_code = -1  # type: ignore[assignment]
    db_exec.duration_seconds = round(time.monotonic() - task_start_monotonic, 2)  # type: ignore[arg-type]
    db_exec.finished_at = now  # type: ignore[assignment]
    db_exec.failure_reason = FAILURE_REASON_ORCHESTRATOR_REBOOT  # type: ignore[assignment]
    db_exec.recovery_action = RECOVERY_ACTION_REQUEUE_IF_SAFE  # type: ignore[assignment]
    db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
        sanitize_log_payload(
            str(db_exec.logs or "")
            + "".join(logs)
            + interruption_log
            + f"{reboot_audit_line}"
        )
    )
    db.commit()


def apply_timeout_result(
    db: Session,
    exec_id: str,
    logs: list[str],
    task_start_monotonic: float,
) -> models.Execution | None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        return None
    db_exec.status = EXECUTION_STATUS_TIMEOUT  # type: ignore[assignment]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    db_exec.duration_seconds = round(time.monotonic() - task_start_monotonic, 2)  # type: ignore[arg-type]
    db_exec.failure_reason = FAILURE_REASON_MAX_RUNTIME_EXCEEDED  # type: ignore[assignment]
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_TIMEOUT_AND_REQUEUE  # type: ignore[assignment]
    # Concatena para preservar a trilha `[TRACE]` do enfileiramento (ver
    # `complete_process_execution`).
    db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
        sanitize_log_payload(
            str(db_exec.logs or "")
            + "\n"
            + "".join(logs)
            + "\n[ERRO] Tarefa excedeu o tempo máximo."
        )
    )
    db.commit()
    return db_exec


def complete_process_execution(  # pylint: disable=too-many-arguments
    db: Session,
    exec_id: str,
    *,
    return_code: int | None,
    logs: list[str],
    artifacts_json: str | None,
    duration_seconds: float,
) -> models.Execution | None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec or db_exec.status in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        return db_exec

    status, failure_reason, recovery_action = classify_process_result(return_code)
    db_exec.exit_code = return_code  # type: ignore[assignment]
    db_exec.duration_seconds = duration_seconds  # type: ignore[assignment]
    db_exec.status = status  # type: ignore[assignment]
    db_exec.failure_reason = failure_reason  # type: ignore[assignment]
    db_exec.recovery_action = recovery_action  # type: ignore[assignment]
    # CONCATENA, não substitui. Este é o desfecho mais comum, e substituir
    # destruía a linha `[TRACE] correlation_id=... event=QUEUED requested_by=...`
    # gravada por `build_queued_execution` no enfileiramento — a única ligação
    # entre o pedido HTTP e a execução. O mesmo valia para a linha `[STOP]`
    # escrita pelo router quando o worker vence a corrida. Todos os demais
    # finalizadores já concatenavam; só este e o de timeout não.
    db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
        sanitize_log_payload(str(db_exec.logs or "") + "\n" + "".join(logs))
    )
    db_exec.artifacts = artifacts_json  # type: ignore[assignment]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    db.commit()
    return db_exec


def apply_internal_worker_error(
    db: Session,
    exec_id: str,
    message: str,
    task_start_monotonic: float,
) -> None:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec or db_exec.status in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        return
    db_exec.status = EXECUTION_STATUS_ERROR  # type: ignore[assignment]
    db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
        str(db_exec.logs or "")
        + f"\nInternal Worker Error: {sanitize_log_payload(message)}"
    )
    db_exec.exit_code = -1  # type: ignore[assignment]
    db_exec.failure_reason = FAILURE_REASON_INTERNAL_WORKER_ERROR  # type: ignore[assignment]
    db_exec.recovery_action = RECOVERY_ACTION_REVIEW_WORKER_LOGS  # type: ignore[assignment]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    db_exec.duration_seconds = round(time.monotonic() - task_start_monotonic, 2)  # type: ignore[arg-type]
    db.commit()


def mark_running_tasks_as_failed_by_reboot(db: Session) -> int:
    """Marca como interrompidas as execuções órfãs de um worker que morreu.

    Só alcança execuções que TÊM dono registrado (`worker_instance_id`). Até
    31/07/2026 a função varria toda linha RUNNING sem olhar as colunas de
    ownership — que existem no modelo exatamente para identificar o dono —,
    atingindo dois casos que não lhe pertencem:

    - `POST /api/executions/telemetry/start` grava RUNNING sem
      `worker_instance_id`, disparada por um terminal externo. Qualquer
      reinício da API a carimbava como interrompida por reboot enquanto o
      processo real seguia rodando, e o `telemetry/end` depois sobrescrevia o
      status — histórico contraditório.
    - `Start-Orchestrator.ps1` sobe o worker ANTES da API. Se o worker
      reivindicasse uma tarefa nesses segundos, a execução recém-iniciada era
      marcada como interrompida com o PowerShell ainda em execução, convidando
      a um requeue manual e a uma entrega duplicada.

    Também grava `duration_seconds`, que era o único finalizador a não gravar —
    deixando buracos na série de duração.
    """
    zombies = (
        db.query(models.Execution)
        .filter(
            models.Execution.status == EXECUTION_STATUS_RUNNING,
            models.Execution.worker_instance_id.isnot(None),
        )
        .all()
    )
    for task in zombies:
        now = get_now_local()
        task.status = "FAILED_BY_REBOOT"  # type: ignore[assignment]
        task.finished_at = now  # type: ignore[assignment]
        if task.started_at and task.duration_seconds is None:
            task.duration_seconds = round((now - task.started_at).total_seconds(), 2)
        task.failure_reason = FAILURE_REASON_ORCHESTRATOR_REBOOT  # type: ignore[assignment]
        task.recovery_action = RECOVERY_ACTION_REQUEUE_IF_SAFE  # type: ignore[assignment]
        reboot_audit_line = (
            f"[RECOVERY_AUDIT] actor=SYSTEM_STARTUP "
            f"action=MARK_FAILED_BY_REBOOT timestamp={now.strftime('%d/%m/%Y %H:%M:%S')}"
        )
        task.logs = str(task.logs or "") + "\n[REBOOT] Interrompida." + f"\n{reboot_audit_line}"  # type: ignore[assignment]
    db.commit()
    return len(zombies)


class RequeueValidationError(Exception):
    """Erro de validacao de negocio do requeue, com status HTTP correspondente."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def prepare_requeue(  # pylint: disable=too-many-arguments,too-many-locals
    db: Session,
    db_exec: models.Execution,
    *,
    payload_reason: str | None,
    payload_requested_by: str | None,
    payload_priority: str | None,
    fallback_requested_by: str,
) -> tuple[models.Execution, dict[str, Any]]:
    """Valida as regras de negocio do requeue e monta a nova execucao (nao commitada).

    Levanta RequeueValidationError com o status HTTP e a mensagem apropriados
    quando alguma regra de concorrencia/retry/prioridade e violada. O chamador
    (router) permanece responsavel por commit, audit log e wake-up do worker.
    """
    if db_exec.status not in EXECUTION_QUEUEABLE_SOURCE_STATUSES:
        raise RequeueValidationError(
            400,
            "Somente execuções terminais ou já reenfileiradas podem ser reabertas.",
        )
    if not db_exec.automation:
        raise RequeueValidationError(404, "Automação não encontrada.")

    if (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == db_exec.automation_id,
            models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)),
        )
        .first()
    ):
        raise RequeueValidationError(
            409, "Já existe uma execução ativa para esta automação."
        )

    # Grupo ATUAL da automação. Antes de 31/07/2026 esta expressão preferia
    # `db_exec.queue_group` (o valor CONGELADO no enfileiramento) e entregava
    # esse valor a `get_group_active_execution`, que compara contra
    # `Automation.queue_group` (o valor ATUAL): depois de uma troca de grupo, a
    # guarda comparava o grupo antigo contra a coluna nova e não encontrava
    # nada — o requeue passava por cima da exclusão mútua.
    queue_group = (
        str(db_exec.automation.queue_group) if db_exec.automation.queue_group else None
    )
    group_active = get_group_active_execution(db, queue_group)
    if group_active:
        raise RequeueValidationError(
            409,
            "Já existe uma execução ativa no mesmo grupo operacional "
            f"({group_active.id}, Grupo: {queue_group}).",
        )

    next_retry_count = int(db_exec.retry_count or 0) + 1
    max_retries = int(
        db_exec.max_retries
        or (db_exec.automation.max_retries if db_exec.automation else 0)
        or 0
    )
    if next_retry_count > max_retries and db_exec.status != "SUCCESS":
        # `max_retries=0` é decisão deliberada do operador para automações com
        # efeito colateral real (WhatsApp/e-mail) — falhas exigem investigação
        # manual antes de retry, automático (`auto_retry_transient_failures`,
        # que também passa por esta função) ou manual. Runbooks OBP-04/RE-03
        # documentam esse bloqueio como comportamento correto e testado em
        # drill. SUCCESS é reprocesso sob demanda, não retentativa de falha.
        raise RequeueValidationError(
            409,
            "Limite de retry excedido para esta execução: "
            f"{next_retry_count - 1}/{max_retries}.",
        )

    new_exec_id = generate_execution_id("REQ")
    requested_by = str(payload_requested_by or fallback_requested_by)
    priority = str(payload_priority or db_exec.priority or PRIORITY_NORMAL).upper()
    if priority not in EXECUTION_ALLOWED_PRIORITIES:
        raise RequeueValidationError(422, "Prioridade inválida para requeue.")

    reason = payload_reason or f"Requeue manual originado de {db_exec.id}."
    new_exec = build_queued_execution(
        automation=db_exec.automation,
        exec_id=new_exec_id,
        requested_by=requested_by,
        priority=priority,
        retry_count=int(next_retry_count),
        max_retries=int(max_retries),
        failure_reason=str(db_exec.failure_reason or db_exec.status),
        recovery_action=RECOVERY_ACTION_REQUEUE_MANUAL,
    )
    new_exec.queue_group = queue_group  # type: ignore[assignment]

    db_exec.status = EXECUTION_STATUS_REQUEUED  # type: ignore[assignment]
    # `finished_at` precisa ser preenchido aqui: `purge_old_executions` filtra
    # por `finished_at < cutoff`, e execuções REQUEUED nasciam com essa coluna
    # nula. Somado ao fato de REQUEUED não constar de EXECUTION_TERMINAL_STATUSES,
    # toda execução já reenfileirada — manual ou pelo auto-retry, que roda a cada
    # 3 minutos — ficava no banco PARA SEMPRE com seus logs comprimidos, imune à
    # retenção de 90 dias. Semanticamente correto: a execução de origem terminou,
    # foi substituída pela nova.
    if db_exec.finished_at is None:
        db_exec.finished_at = get_now_local()
    db_exec.recovery_action = RECOVERY_ACTION_REQUEUED_TO_NEW_EXECUTION  # type: ignore[assignment]
    db_exec.logs = str(db_exec.logs or "") + f"\n[REQUEUE] Nova execução criada: {new_exec_id}. Motivo: {reason}"  # type: ignore[assignment]

    audit_payload = {
        "source_exec_id": str(db_exec.id),
        "queued_exec_id": new_exec_id,
        "reason": reason,
        "retry_count": next_retry_count,
        "max_retries": max_retries,
        "priority": priority,
    }
    return new_exec, audit_payload

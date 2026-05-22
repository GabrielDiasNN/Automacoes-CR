# pylint: disable=all
# mypy: ignore-errors
"""
Router: Executions - Histórico de execuções com decorações operacionais (A2, A3), filtros avançados, logs, artefatos e controle de fila. v9.2.0
"""

import json
import logging
import math
import os
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_ALLOWED_PRIORITIES,
    EXECUTION_ALLOWED_STATUSES,
    EXECUTION_QUEUEABLE_SOURCE_STATUSES,
    EXECUTION_STATUS_REQUEUED,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_TERMINATED,
    RECOVERY_ACTION_REQUEUE_MANUAL,
    RECOVERY_ACTION_REQUEUED_TO_NEW_EXECUTION,
)
from ..database import get_db
from ..middleware import get_api_key
from ..runtime import get_project_root, trigger_worker_wakeup
from ..security import sanitize_log_payload
from ..services.execution_runtime import (
    build_queued_execution,
    generate_execution_id,
    get_group_active_execution,
)
from ..services.scoring import compute_attention_score
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/executions", tags=["Executions"])

# Raiz do projeto para resolver caminhos
PROJECT_ROOT = get_project_root()


# ---------------------------------------------------------------------------
# PIPELINE DE DECORAÇÃO OPERACIONAL (A2, A3)
# ---------------------------------------------------------------------------


def _build_active_execution_maps(
    db: Session,
) -> tuple[dict[int, models.Execution], dict[str, models.Execution]]:
    """Mapeia execuções ativas em memória para evitar N+1 queries na decoração."""
    active_execs = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .filter(models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)))
        .order_by(desc(models.Execution.started_at))
        .all()
    )
    by_automation: dict[int, models.Execution] = {}
    by_group: dict[str, models.Execution] = {}
    for item in active_execs:
        by_automation.setdefault(int(item.automation_id), item)
        queue_group = item.queue_group or getattr(
            item.automation, "queue_group", None
        )
        if queue_group:
            by_group.setdefault(str(queue_group), item)
    return by_automation, by_group


def _determine_operational_actions(
    summary: schemas.ExecutionSummary | schemas.ExecutionResponse,
    ex: models.Execution,
    active_by_automation: dict[int, models.Execution],
    active_by_group: dict[str, models.Execution],
    queue_group: Optional[str],
) -> None:
    """Determina as ações do operador disponíveis para a execução e condições de reenfileiramento (A2)."""
    queueable = ex.status in EXECUTION_QUEUEABLE_SOURCE_STATUSES
    max_retries = int(
        ex.max_retries
        or (ex.automation.max_retries if ex.automation else 0)
        or 0
    )
    retry_count = int(ex.retry_count or 0)
    active_for_automation = active_by_automation.get(int(ex.automation_id))
    active_for_group = active_by_group.get(queue_group) if queue_group else None

    # Inicializar campos padrão
    summary.requeue_allowed = False
    summary.requeue_block_reason = None
    summary.related_execution_id = None
    summary.related_execution_status = None
    summary.operator_action_code = "VIEW_LOGS"
    summary.operator_action_label = "Revisar logs"
    summary.operator_action_hint = (
        "Revise logs e contexto operacional antes de uma nova tentativa."
    )

    if queueable:
        if active_for_automation and active_for_automation.id != ex.id:
            summary.requeue_block_reason = f"Já existe execução ativa para esta automação ({active_for_automation.id})."
            summary.related_execution_id = str(active_for_automation.id)
            summary.related_execution_status = str(active_for_automation.status)
        elif active_for_group and active_for_group.id != ex.id:
            summary.requeue_block_reason = f"Grupo operacional '{queue_group}' já está em uso por {active_for_group.id}."
            summary.related_execution_id = str(active_for_group.id)
            summary.related_execution_status = str(active_for_group.status)
        elif retry_count >= max_retries:
            summary.requeue_block_reason = (
                f"Limite de retry já foi atingido ({retry_count}/{max_retries})."
            )
        else:
            summary.requeue_allowed = True
            summary.operator_action_code = "REQUEUE"
            summary.operator_action_label = "Reenfileirar"
            summary.operator_action_hint = "Execução pode ser enviada novamente para a fila de processamento."

    elif ex.status in EXECUTION_ACTIVE_STATUSES:
        summary.operator_action_code = "STOP"
        summary.operator_action_label = "Parar execução"
        summary.operator_action_hint = (
            "Solicita a interrupção imediata do processo."
        )

    # Sobrescrever ações para linhas de sucesso saudáveis
    if ex.status == "SUCCESS":
        summary.requeue_allowed = True
        summary.operator_action_code = "REQUEUE"
        summary.operator_action_label = None
        summary.operator_action_hint = None


def _set_operator_attention(
    summary: schemas.ExecutionSummary | schemas.ExecutionResponse,
    ex: models.Execution,
    score: int,
    reasons: list[str],
) -> None:
    """Calcula a gravidade da atenção e monta a resposta operacional consolidada (A2)."""
    summary.operator_score = score
    summary.operator_attention_required = score >= 20

    if score >= 80:
        summary.operator_severity = "CRITICAL"
    elif score >= 50:
        summary.operator_severity = "HIGH"
    elif score >= 20:
        summary.operator_severity = "MODERATE"
    else:
        summary.operator_severity = "NORMAL"

    if reasons:
        summary.operator_reason_summary = " | ".join(reasons)
    else:
        summary.operator_reason_summary = None

    # Sobrescrever campos para manter linhas de sucesso saudáveis compactas
    if ex.status == "SUCCESS" and score < 20:
        summary.operator_attention_required = False
        summary.operator_action_label = None
        summary.operator_reason_summary = None
        summary.operator_score = 0
        summary.operator_severity = "NORMAL"


def _decorate_execution_summary(
    summary: schemas.ExecutionSummary | schemas.ExecutionResponse,
    ex: models.Execution,
    active_by_automation: dict[int, models.Execution],
    active_by_group: dict[str, models.Execution],
) -> schemas.ExecutionSummary | schemas.ExecutionResponse:
    """Decora o resumo de execução em pipeline usando scoring centralizado (A2, A3)."""
    queue_group = ex.queue_group or getattr(ex.automation, "queue_group", None)
    now = get_now_local()

    summary.related_queue_group = (
        str(queue_group) if queue_group else None
    )  # type: ignore[assignment]
    summary.stop_allowed = ex.status in EXECUTION_ACTIVE_STATUSES
    summary.requeue_allowed = False
    summary.requeue_block_reason = None
    summary.related_execution_id = None
    summary.related_execution_status = None
    summary.operator_attention_required = False
    summary.operator_score = 0
    summary.operator_reason_summary = None
    summary.operator_severity = "NORMAL"

    # Pipeline de execução dos decoradores
    _determine_operational_actions(
        summary,
        ex,
        active_by_automation,
        active_by_group,
        str(queue_group) if queue_group else None,
    )
    score, reasons = compute_attention_score(
        ex, now, active_by_automation, active_by_group
    )
    _set_operator_attention(summary, ex, score, reasons)

    return summary


# ---------------------------------------------------------------------------
# LISTAGEM GLOBAL com filtros e paginação
# ---------------------------------------------------------------------------


@router.get("", response_model=schemas.PaginatedResponse[schemas.ExecutionSummary])
def list_executions(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    automation_id: Optional[int] = None,
    queue_group: Optional[str] = None,
    priority: Optional[str] = None,
    requested_by: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> schemas.PaginatedResponse[schemas.ExecutionSummary]:
    """Lista execuções com filtros avançados e paginação. Otimizado com joinedload."""
    if page < 1:
        raise HTTPException(status_code=422, detail="page deve ser >= 1.")
    if per_page < 1 or per_page > 200:
        raise HTTPException(
            status_code=422, detail="per_page deve estar entre 1 e 200."
        )

    query = db.query(models.Execution).options(joinedload(models.Execution.automation))

    if status:
        normalized_status = status.upper()
        if normalized_status not in EXECUTION_ALLOWED_STATUSES:
            allowed = ", ".join(sorted(EXECUTION_ALLOWED_STATUSES))
            raise HTTPException(
                status_code=422, detail=f"status inválido. Use: {allowed}."
            )
        query = query.filter(models.Execution.status == normalized_status)

    if priority:
        normalized_priority = priority.upper()
        if normalized_priority not in EXECUTION_ALLOWED_PRIORITIES:
            allowed = ", ".join(sorted(EXECUTION_ALLOWED_PRIORITIES))
            raise HTTPException(
                status_code=422, detail=f"priority inválida. Use: {allowed}."
            )
        query = query.filter(models.Execution.priority == normalized_priority)

    if automation_id:
        query = query.filter(models.Execution.automation_id == automation_id)
    if queue_group:
        query = query.filter(models.Execution.queue_group == queue_group)
    if requested_by:
        query = query.filter(models.Execution.requested_by.ilike(f"%{requested_by}%"))

    dt_from = None
    dt_to = None
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(models.Execution.started_at >= dt_from)
        except ValueError:
            raise HTTPException(
                status_code=422, detail="date_from inválido. Use formato ISO-8601."
            )
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(models.Execution.started_at <= dt_to)
        except ValueError:
            raise HTTPException(
                status_code=422, detail="date_to inválido. Use formato ISO-8601."
            )
    if dt_from and dt_to and dt_from > dt_to:
        raise HTTPException(
            status_code=422, detail="date_from não pode ser maior que date_to."
        )

    query = query.order_by(desc(models.Execution.started_at))

    total = query.count()
    pages = math.ceil(total / per_page) if per_page > 0 else 1
    items_raw = query.offset((page - 1) * per_page).limit(per_page).all()

    # Mapear execuções ativas em memória para evitar N+1 queries na decoração
    active_by_auto, active_by_group = _build_active_execution_maps(db)

    # Enriquecer com nome da automação e pipeline de decoração
    items = []
    for ex in items_raw:
        summary = schemas.ExecutionSummary.model_validate(ex)
        summary.automation_name = (
            ex.automation.name if ex.automation else "Desconhecido"
        )
        _decorate_execution_summary(summary, ex, active_by_auto, active_by_group)
        items.append(summary)

    return schemas.PaginatedResponse(
        items=items, total=total, page=page, per_page=per_page, pages=pages
    )


# ---------------------------------------------------------------------------
# EXECUÇÕES POR AUTOMAÇÃO (compatibilidade)
# ---------------------------------------------------------------------------


@router.get(
    "/by-automation/{automation_id}", response_model=list[schemas.ExecutionSummary]
)
def list_by_automation(
    automation_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> list[schemas.ExecutionSummary]:
    """Retorna execuções de uma automação específica com decoração."""
    execs = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .filter(models.Execution.automation_id == automation_id)
        .order_by(desc(models.Execution.started_at))
        .limit(limit)
        .all()
    )

    active_by_auto, active_by_group = _build_active_execution_maps(db)

    result = []
    for ex in execs:
        s = schemas.ExecutionSummary.model_validate(ex)
        s.automation_name = ex.automation.name if ex.automation else "Desconhecido"
        _decorate_execution_summary(s, ex, active_by_auto, active_by_group)
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# RECENTES (para dashboard overview)
# ---------------------------------------------------------------------------


@router.get("/recent", response_model=list[schemas.ExecutionSummary])
def list_recent(
    limit: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> list[schemas.ExecutionSummary]:
    """Retorna as execuções mais recentes de todas as automações com decoração."""
    execs = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .order_by(desc(models.Execution.started_at))
        .limit(limit)
        .all()
    )

    active_by_auto, active_by_group = _build_active_execution_maps(db)

    result = []
    for ex in execs:
        s = schemas.ExecutionSummary.model_validate(ex)
        s.automation_name = ex.automation.name if ex.automation else "Desconhecido"
        _decorate_execution_summary(s, ex, active_by_auto, active_by_group)
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# GET por ID (com logs completos e decoração)
# ---------------------------------------------------------------------------


@router.get("/{exec_id}", response_model=schemas.ExecutionResponse)
def get_execution(
    exec_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> schemas.ExecutionResponse:
    db_exec = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .filter(models.Execution.id == exec_id)
        .first()
    )
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    resp = schemas.ExecutionResponse.model_validate(db_exec)
    resp.automation_name = (
        db_exec.automation.name if db_exec.automation else "Desconhecido"
    )

    active_by_auto, active_by_group = _build_active_execution_maps(db)
    _decorate_execution_summary(resp, db_exec, active_by_auto, active_by_group)

    return resp


# ---------------------------------------------------------------------------
# LOGS de uma execução (paginados por linhas)
# ---------------------------------------------------------------------------


@router.get("/{exec_id}/logs")
def get_execution_logs(
    exec_id: str,
    offset: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Retorna logs de uma execução com paginação por linhas."""
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    all_lines = (db_exec.logs or "").split("\n")
    total_lines = len(all_lines)
    sliced = all_lines[offset : offset + limit]

    return {
        "exec_id": exec_id,
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "lines": sliced,
    }


# ---------------------------------------------------------------------------
# ARTEFATOS de uma execução
# ---------------------------------------------------------------------------


@router.get("/{exec_id}/artifacts")
def list_artifacts(
    exec_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Lista artefatos gerados por uma execução."""
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    artifacts = []
    if db_exec.artifacts:
        try:
            artifacts = json.loads(str(db_exec.artifacts))
        except (json.JSONDecodeError, TypeError):
            pass

    return {"exec_id": exec_id, "artifacts": artifacts}


@router.get("/{exec_id}/download")
def download_artifact(
    exec_id: str,
    filename: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> FileResponse:
    """Download de um artefato específico."""
    db_exec = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .filter(models.Execution.id == exec_id)
        .first()
    )
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    db_auto = db_exec.automation
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    # Anti-path-traversal no filename: permitir apenas nome puro do arquivo
    clean_filename = os.path.basename(filename)
    if clean_filename != filename:
        raise HTTPException(status_code=400, detail="Caminho de arquivo inválido.")

    script_path = db_auto.script_path
    if script_path.startswith("./") or script_path.startswith(".\\"):
        robot_dir = os.path.normpath(
            os.path.join(PROJECT_ROOT, os.path.dirname(script_path[2:]))
        )
    else:
        robot_dir = os.path.normpath(os.path.dirname(os.path.abspath(script_path)))

    file_path = os.path.normpath(os.path.join(robot_dir, filename))

    # Validar se o arquivo resolvido ainda reside dentro do diretório do robô ou do projeto
    if not file_path.startswith(robot_dir):
        raise HTTPException(status_code=403, detail="Acesso negado ao arquivo.")

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=404, detail=f"Arquivo '{filename}' não encontrado."
        )

    return FileResponse(path=file_path, filename=filename)


# ---------------------------------------------------------------------------
# STOP (Parar execução)
# ---------------------------------------------------------------------------


@router.post("/{exec_id}/stop")
def stop_execution(
    exec_id: str,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    if db_exec.status not in EXECUTION_ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="Execução já finalizada.")

    previous_status = db_exec.status
    db_exec.status = EXECUTION_STATUS_TERMINATED  # type: ignore[assignment]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    if db_exec.started_at and db_exec.finished_at:
        try:
            delta = db_exec.finished_at - db_exec.started_at
            db_exec.duration_seconds = round(delta.total_seconds(), 2)  # type: ignore[assignment]
        except Exception:
            pass
    db_exec.logs = (  # type: ignore[assignment]
        (db_exec.logs or "")
        + f"\n[STOP] Interrupcao solicitada via API enquanto status={previous_status}."
    )

    log_audit(db, "STOP", "EXECUTION", exec_id, get_client_ip(request))
    db.commit()

    logger.info(f"Execucao interrompida: {exec_id}")
    return {"message": "Sinal de parada registrado.", "exec_id": exec_id}


# ---------------------------------------------------------------------------
# REQUEUE (Reenfileirar execução com retry e concorrência)
# ---------------------------------------------------------------------------


@router.post("/{exec_id}/requeue", response_model=schemas.ExecutionQueueActionResponse)
def requeue_execution(
    exec_id: str,
    payload: schemas.ExecutionQueueActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> schemas.ExecutionQueueActionResponse:
    """Reenfileira uma execução terminal mantendo rastreabilidade de retry."""
    db_exec = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .filter(models.Execution.id == exec_id)
        .first()
    )
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    if db_exec.status not in EXECUTION_QUEUEABLE_SOURCE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Somente execuções terminais ou já reenfileiradas podem ser reabertas.",
        )
    if not db_exec.automation:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    active = (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == db_exec.automation_id,
            models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)),
        )
        .first()
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma execução ativa para esta automação ({active.id}).",
        )

    queue_group = (
        str(db_exec.queue_group or db_exec.automation.queue_group)
        if (
            db_exec.queue_group
            or (db_exec.automation and db_exec.automation.queue_group)
        )
        else None
    )
    group_active = get_group_active_execution(db, queue_group)
    if group_active:
        raise HTTPException(
            status_code=409,
            detail=(
                "Já existe uma execução ativa no mesmo grupo operacional "
                f"({group_active.id}, Grupo: {queue_group})."
            ),
        )

    next_retry_count = int(db_exec.retry_count or 0) + 1
    max_retries = int(
        db_exec.max_retries
        or (db_exec.automation.max_retries if db_exec.automation else 0)
        or 0
    )
    if next_retry_count > max_retries:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Limite de retry excedido para esta execução: "
                f"{next_retry_count - 1}/{max_retries}."
            ),
        )

    new_exec_id = generate_execution_id("REQ")
    requested_by = str(payload.requested_by or get_client_ip(request))
    priority = str(payload.priority or db_exec.priority or "NORMAL").upper()
    if priority not in EXECUTION_ALLOWED_PRIORITIES:
        raise HTTPException(status_code=422, detail="Prioridade inválida para requeue.")

    reason = payload.reason or f"Requeue manual originado de {exec_id}."
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
    db.add(new_exec)

    db_exec.status = EXECUTION_STATUS_REQUEUED  # type: ignore[assignment]
    db_exec.recovery_action = RECOVERY_ACTION_REQUEUED_TO_NEW_EXECUTION  # type: ignore[assignment]
    db_exec.logs = (  # type: ignore[assignment]
        (db_exec.logs or "")
        + f"\n[REQUEUE] Nova execução criada: {new_exec_id}. Motivo: {reason}"
    )

    log_audit(
        db,
        "REQUEUE",
        "EXECUTION",
        exec_id,
        get_client_ip(request),
        json.dumps(
            {
                "source_exec_id": exec_id,
                "queued_exec_id": new_exec_id,
                "reason": reason,
                "retry_count": next_retry_count,
                "max_retries": max_retries,
                "priority": priority,
            }
        ),
    )
    db.commit()

    trigger_worker_wakeup()

    return schemas.ExecutionQueueActionResponse(
        message="Execução reenfileirada com sucesso.",
        source_exec_id=exec_id,
        queued_exec_id=new_exec_id,
        automation_id=int(db_exec.automation_id),
        retry_count=int(next_retry_count),
        max_retries=int(max_retries),
        recovery_action="REQUEUE_MANUAL",
    )


# ---------------------------------------------------------------------------
# TELEMETRIA EXTERNA (Terminal / VS Code)
# ---------------------------------------------------------------------------


@router.post("/telemetry/start")
def telemetry_start(
    payload: schemas.ExecutionTelemetryStart,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Inicia o registro de uma execução disparada externamente (ex: terminal)."""
    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.name == payload.automation_name)
        .first()
    )
    if not db_auto:
        raise HTTPException(
            status_code=404,
            detail=f"Automação '{payload.automation_name}' não encontrada.",
        )

    # Gerar ID único
    exec_id = f"TEL_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    new_exec = models.Execution(
        id=exec_id,
        automation_id=db_auto.id,
        status=EXECUTION_STATUS_RUNNING,  # type: ignore[assignment]
        requested_by="TERMINAL",
        started_at=get_now_local(),  # type: ignore[assignment]
        max_retries=db_auto.max_retries or 0,
        queue_group=db_auto.queue_group,  # type: ignore[assignment]
    )
    db.add(new_exec)

    log_audit(db, "START_TELEMETRY", "EXECUTION", exec_id, get_client_ip(request))
    db.commit()

    logger.info(
        f"Telemetria iniciada: {exec_id} para automacao {payload.automation_name}"
    )
    return {"exec_id": exec_id}


@router.post("/telemetry/end/{exec_id}")
def telemetry_end(
    exec_id: str,
    payload: schemas.ExecutionTelemetryEnd,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Finaliza o registro de uma execução disparada externamente."""
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    db_exec.status = str(payload.status).upper()  # type: ignore[assignment]
    if payload.exit_code is not None:
        db_exec.exit_code = int(payload.exit_code)  # type: ignore[assignment]
    if payload.logs is not None:
        db_exec.logs = sanitize_log_payload(payload.logs)  # type: ignore[assignment]
    if payload.artifacts is not None:
        db_exec.artifacts = payload.artifacts  # type: ignore[assignment]

    db_exec.finished_at = get_now_local()  # type: ignore[assignment]

    # Calcular duração
    if db_exec.started_at and db_exec.finished_at:
        try:
            delta = db_exec.finished_at - db_exec.started_at
            db_exec.duration_seconds = round(delta.total_seconds(), 2)  # type: ignore[assignment]
        except Exception:
            pass

    log_audit(db, "END_TELEMETRY", "EXECUTION", exec_id, get_client_ip(request))
    db.commit()

    logger.info(f"Telemetria finalizada: {exec_id} com status {payload.status}")
    return {"message": "Telemetria registrada com sucesso.", "exec_id": exec_id}

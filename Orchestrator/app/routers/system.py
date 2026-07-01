"""

Router: System - Health check, metricas, backup, status do worker, audit log e endpoints enterprise v5.2.0

"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from .. import metrics as _metrics
from .. import models, schemas
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
)
from ..database import (
    get_db,
    get_wal_size_mb,
    purge_old_executions,
    run_wal_checkpoint,
)
from ..middleware import get_api_key
from ..runtime import (
    get_project_root,
    scheduler,
    trigger_worker_wakeup,
    wait_for_task_signal,
)
from ..services.env_admin import backup_env_file, read_env_content, write_env_content
from ..services.env_admin import validate_env_content as validate_env_payload
from ..services.metrics import get_global_execution_counts
from ..services.portfolio_catalog import build_portfolio_health_response
from ..services.scheduler_runtime import list_scheduled_jobs as build_scheduled_jobs
from ..services.scheduler_runtime import reload_scheduled_tasks
from ..services.system_diagnostics import build_diagnostics_payload
from ..services.system_history import build_system_history_response
from ..services.system_overview import build_system_overview_payload
from ..services.system_runtime import (
    build_health_payload,
    build_version_payload,
    launch_orchestrator_recovery,
    perform_manual_backup,
)
from ..services.system_runtime import get_worker_status as get_worker_status_service
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/system", tags=["System"])

PROJECT_ROOT = get_project_root()

# ---------------------------------------------------------------------------

# HEALTH CHECK COMPLETO

# ---------------------------------------------------------------------------


@router.get("/health", response_model=schemas.SystemHealth)
def health_check(db: Session = Depends(get_db)) -> schemas.SystemHealth:
    """Health check completo: DB, Scheduler, Worker, Disco."""
    return build_health_payload(db, _get_worker_status(db))


# ---------------------------------------------------------------------------

# WORKER STATUS

# ---------------------------------------------------------------------------


def _get_worker_status(db: Session) -> schemas.WorkerStatus:
    """Le o heartbeat do worker do banco."""
    return get_worker_status_service(db)


def _launch_orchestrator_recovery() -> str:
    """Dispara o fluxo canônico de recuperação do Orchestrator em background."""
    return launch_orchestrator_recovery(PROJECT_ROOT)


@router.get("/worker/status", response_model=schemas.WorkerStatus)
def get_worker_status(
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.WorkerStatus:
    """Retorna status detalhado do Worker."""

    return _get_worker_status(db)


# ---------------------------------------------------------------------------

# METRICAS ENRIQUECIDAS (N+1 Query Eliminada)

# ---------------------------------------------------------------------------


@router.get("/metrics", response_model=schemas.MetricsResponse)
def get_metrics(
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.MetricsResponse:
    """Metricas completas do sistema (Otimizado sem N+1)."""

    total_execs, success_count, error_count, pending_count = (
        get_global_execution_counts(db)
    )

    # Duracao media global

    avg_dur = (
        db.query(func.avg(models.Execution.duration_seconds))
        .filter(
            models.Execution.status == "SUCCESS",
            models.Execution.duration_seconds.isnot(None),
        )
        .scalar()
        or 0
    )

    success_rate = (
        round((success_count / total_execs * 100), 2) if total_execs > 0 else 0
    )

    # Agregacao de metricas por automacao em uma unica query
    stats_map = {
        row.automation_id: row
        for row in db.query(
            models.Execution.automation_id,
            func.count(  # pylint: disable=not-callable
                case((models.Execution.status.in_(["SUCCESS", "PARTIAL"]), 1))
            ).label("total_success"),
            func.count(case((models.Execution.status == "ERROR", 1))).label(  # pylint: disable=not-callable
                "total_errors"
            ),
            func.avg(
                case(
                    (
                        models.Execution.status == "SUCCESS",
                        models.Execution.duration_seconds,
                    )
                )
            ).label("avg_duration"),
        )
        .group_by(models.Execution.automation_id)
        .all()
    }

    # Subquery para ultima execucao
    subq = (
        db.query(
            models.Execution.automation_id,
            func.max(models.Execution.started_at).label("max_started_at"),
        )
        .group_by(models.Execution.automation_id)
        .subquery()
    )

    last_execs_map = {
        row.automation_id: row
        for row in db.query(
            models.Execution.automation_id,
            models.Execution.status,
            models.Execution.started_at,
        )
        .join(
            subq,
            (models.Execution.automation_id == subq.c.automation_id)
            & (models.Execution.started_at == subq.c.max_started_at),
        )
        .all()
    }

    automation_stats = []

    for auto in db.query(models.Automation).all():
        stat = stats_map.get(auto.id)
        last_ex = last_execs_map.get(auto.id)

        automation_stats.append(
            schemas.AutomationMetric(
                name=str(auto.name),
                total_success=stat.total_success if stat else 0,
                total_errors=stat.total_errors if stat else 0,
                avg_duration_sec=(
                    round(stat.avg_duration, 2) if stat and stat.avg_duration else 0
                ),
                last_status=last_ex.status if last_ex else None,
                last_run=last_ex.started_at if last_ex else None,
                test_mode=bool(auto.test_mode),
            )
        )

    return schemas.MetricsResponse(
        summary=schemas.MetricsSummary(
            total_executions=total_execs,
            success_count=success_count,
            error_count=error_count,
            success_rate=success_rate,
            pending_count=pending_count,
            avg_duration_sec=round(avg_dur, 2),
        ),
        automations=automation_stats,
    )


# ---------------------------------------------------------------------------

# BACKUP MANUAL

# ---------------------------------------------------------------------------


@router.post("/backup")
def manual_backup(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Realiza backup atomico do banco de dados SQLite."""
    try:
        result: dict[str, Any] = perform_manual_backup(db, PROJECT_ROOT)
        logger.info(
            "Backup manual concluido: %s (%sMB)", result["path"], result["size_mb"]
        )

        log_audit(
            db,
            "BACKUP",
            "SYSTEM",
            "GLOBAL",
            get_client_ip(request),
            json.dumps({"path": result["path"], "size_mb": result["size_mb"]}),
        )

        db.commit()
        return result

    except Exception as e:

        logger.error("Falha no backup manual: %s", e)

        raise HTTPException(
            status_code=500, detail=f"Falha no backup: {str(e)}"
        ) from e


@router.post("/scheduler/reload")
def reload_scheduler_jobs(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Forca sincronizacao do APScheduler com automacoes habilitadas."""
    reload_scheduled_tasks()
    jobs_loaded = len(scheduler.get_jobs())

    log_audit(
        db,
        "SCHEDULER_RELOAD",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        json.dumps({"jobs_loaded": jobs_loaded}),
    )
    db.commit()

    return {
        "message": "Scheduler sincronizado com sucesso.",
        "jobs_loaded": jobs_loaded,
    }


@router.post("/worker/wakeup")
def wakeup_worker(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Dispara wake-up para o worker verificar a fila imediatamente."""
    trigger_worker_wakeup()

    log_audit(
        db,
        "WORKER_WAKEUP",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        "Sinal manual de wake-up enviado para o worker.",
    )
    db.commit()

    return {"message": "Sinal de wake-up enviado ao worker."}


@router.post("/worker/recover")
def recover_worker(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Aciona a recuperação canônica do Orchestrator quando o worker está offline."""
    worker_status = _get_worker_status(db)
    active_count = (
        db.query(func.count(models.Execution.id))  # pylint: disable=not-callable
        .filter(models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES))
        .scalar()
        or 0
    )

    if worker_status.is_alive:
        raise HTTPException(
            status_code=409,
            detail="Worker já está online; use apenas wake-up para acelerar a fila.",
        )

    script_name = _launch_orchestrator_recovery()

    log_audit(
        db,
        "WORKER_RECOVER",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        json.dumps(
            {
                "script": script_name,
                "queue_active_count": active_count,
                "worker_alive": worker_status.is_alive,
            }
        ),
    )
    db.commit()

    return {
        "message": "Recuperação do Orchestrator acionada com sucesso.",
        "script": script_name,
        "queue_active_count": active_count,
    }


# ---------------------------------------------------------------------------

# AUDIT LOG

# ---------------------------------------------------------------------------


@router.get("/audit", response_model=list[schemas.AuditEntry])
def list_audit_log(
    limit: int = 50,
    action: str | None = None,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> list[models.AuditLog]:
    """Retorna as entradas mais recentes do log de auditoria."""

    query = db.query(models.AuditLog)

    if action:

        query = query.filter(models.AuditLog.action == action.upper())

    entries: list[models.AuditLog] = query.order_by(desc(models.AuditLog.timestamp)).limit(limit).all()

    return entries


# ---------------------------------------------------------------------------

# UPTIME

# ---------------------------------------------------------------------------


@router.get("/uptime")
def get_uptime(request: Request, _api_key: str = Depends(get_api_key)) -> dict[str, Any]:
    """Retorna o tempo de atividade do Orchestrator."""
    startup_time = request.app.state.startup_time
    uptime = get_now_local() - startup_time

    return {
        "started_at": schemas.format_dt_br(startup_time),
        "uptime_seconds": round(uptime.total_seconds(), 2),
        "uptime_human": str(uptime).split(".", maxsplit=1)[0],
    }


# ---------------------------------------------------------------------------

# AGENDAMENTO - Lista de tarefas programadas

# ---------------------------------------------------------------------------


@router.get("/scheduler/jobs", response_model=list[schemas.ScheduledJob])
def list_scheduled_jobs(
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> list[schemas.ScheduledJob]:
    """Retorna a lista de tarefas agendadas no APScheduler."""
    return build_scheduled_jobs(db)


@router.get("/overview", response_model=schemas.SystemOverviewResponse)
def get_system_overview(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Agrega métricas, saúde, jobs e eventos recentes para o dashboard operacional."""
    health_payload = health_check(db).model_dump()
    jobs = list_scheduled_jobs(db, _api_key)
    diagnostics = build_diagnostics_payload(
        db,
        scheduler,
        _get_worker_status,
        wal_size_fn=get_wal_size_mb,
    )
    diagnostics["trace"] = {
        "correlation_id": getattr(request.state, "request_id", "SYSTEM")
    }
    portfolio_health = build_portfolio_health_response(db, PROJECT_ROOT)
    return build_system_overview_payload(
        db=db,
        scheduler=scheduler,
        health_payload=health_payload,
        jobs=jobs,
        diagnostics_payload=diagnostics,
        portfolio_summary=portfolio_health.summary,
    )


# ---------------------------------------------------------------------------

# VERSION - Endpoint enterprise de versao e build

# ---------------------------------------------------------------------------


@router.get("/version", response_model=schemas.SystemVersion)
def get_version(request: Request) -> schemas.SystemVersion:
    """Retorna informacoes detalhadas de versao e build do Orchestrator."""
    return build_version_payload(request.app.state.startup_time)


@router.get("/diagnostics", response_model=schemas.DiagnosticsPayload)
def get_diagnostics(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Retorna diagnostico operacional consolidado do Orchestrator."""
    payload: dict[str, Any] = build_diagnostics_payload(
        db,
        scheduler,
        _get_worker_status,
        wal_size_fn=get_wal_size_mb,
    )
    payload["trace"] = {
        "correlation_id": getattr(request.state, "request_id", "SYSTEM")
    }
    return payload


@router.get("/baseline", response_model=schemas.OperationalBaselineSummary)
def get_operational_baseline(
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> Any:
    """Retorna o baseline operacional resumido para triagem rápida."""
    payload: dict[str, Any] = build_diagnostics_payload(
        db,
        scheduler,
        _get_worker_status,
        wal_size_fn=get_wal_size_mb,
    )
    return payload["operational_baseline"]


@router.get("/history", response_model=schemas.SystemHistoryResponse)
def get_system_history(
    hours: int = 24,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.SystemHistoryResponse:
    """Retorna histórico recente de snapshots operacionais do Orchestrator."""
    return build_system_history_response(db, hours)


@router.post("/schedule/validate", response_model=schemas.ScheduleValidationResponse)
def validate_schedule_payload(
    payload: schemas.ScheduleValidationRequest,
    _api_key: str = Depends(get_api_key),
) -> schemas.ScheduleValidationResponse:
    """Valida um schedule sem persistir alteracoes."""
    try:
        normalized = schemas._validate_schedule(  # pylint: disable=protected-access
            payload.schedule
        )
        parsed = schemas.parse_schedule(normalized) if normalized else None
        summary = schemas.describe_schedule_payload(parsed)
        return schemas.ScheduleValidationResponse(
            valid=True,
            normalized_schedule=normalized,
            summary=summary,
            errors=[],
        )
    except ValueError as exc:
        return schemas.ScheduleValidationResponse(
            valid=False,
            normalized_schedule=None,
            summary="Schedule inválido.",
            errors=[str(exc)],
        )


@router.post("/schedule/preview", response_model=schemas.SchedulePreviewResponse)
def preview_schedule_payload(
    payload: schemas.SchedulePreviewRequest,
    _api_key: str = Depends(get_api_key),
) -> schemas.SchedulePreviewResponse:
    """Simula próximas execuções para uma agenda sem persistir alteração."""
    try:
        normalized = schemas._validate_schedule(  # pylint: disable=protected-access
            payload.schedule
        )
        parsed = schemas.parse_schedule(normalized) if normalized else None
        return schemas.SchedulePreviewResponse(
            valid=True,
            normalized_schedule=normalized,
            schedule_type=parsed.get("schedule_type") if parsed else "manual",
            schedule_summary=schemas.describe_schedule_payload(parsed),
            next_runs_preview=schemas.preview_next_runs(parsed, payload.limit),
            errors=[],
        )
    except ValueError as exc:
        return schemas.SchedulePreviewResponse(
            valid=False,
            normalized_schedule=None,
            schedule_type=None,
            schedule_summary=None,
            next_runs_preview=[],
            errors=[str(exc)],
        )


# ---------------------------------------------------------------------------

# CHECKPOINT - WAL manual

# ---------------------------------------------------------------------------


@router.post("/checkpoint")
def manual_checkpoint(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Executa WAL checkpoint manual no banco SQLite."""

    result: dict[str, Any] = run_wal_checkpoint()

    logger.info("Checkpoint manual executado: %s", result)

    log_audit(
        db,
        "CHECKPOINT",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        json.dumps(result),
    )

    db.commit()

    return {"message": "WAL Checkpoint executado com sucesso.", "result": result}


# ---------------------------------------------------------------------------

# PURGE - Limpeza de execucoes antigas

# ---------------------------------------------------------------------------


@router.post("/purge")
def manual_purge(
    request: Request,
    retention_days: int = 90,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Remove execucoes finalizadas mais antigas que retention_days (default: 90)."""

    if retention_days < 7:

        raise HTTPException(status_code=400, detail="retention_days deve ser >= 7.")

    removed = purge_old_executions(retention_days)

    logger.info(
        "Purge manual: %s execucoes removidas (>%s dias).", removed, retention_days
    )

    log_audit(
        db,
        "PURGE",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        json.dumps({"retention_days": retention_days, "removed": removed}),
    )

    db.commit()

    return {
        "message": f"{removed} execução(ões) removida(s).",
        "retention_days": retention_days,
        "removed_count": removed,
    }


# ---------------------------------------------------------------------------
# ENV MANAGEMENT - Gestao global
# ---------------------------------------------------------------------------


@router.get("/wait-for-task")
async def wait_for_task(_api_key: str = Depends(get_api_key)) -> dict[str, Any]:
    """Endpoint de long-polling para wake-up do Worker (v6.2.0)."""
    return {"status": await wait_for_task_signal(timeout_seconds=30)}


@router.get("/env", response_model=schemas.EnvContent)
def get_env_content(_api_key: str = Depends(get_api_key)) -> schemas.EnvContent:
    """Lê o conteúdo do arquivo .env global."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    return schemas.EnvContent(content=read_env_content(env_path))


@router.post("/env/validate", response_model=schemas.EnvValidationResponse)
def validate_env_content(
    payload: schemas.EnvContent,
    _api_key: str = Depends(get_api_key),
) -> schemas.EnvValidationResponse:
    """Valida o conteúdo do .env sem persistir alterações."""
    return validate_env_payload(payload.content)


@router.put("/env", response_model=schemas.ManagedMutationResponse)
def update_env_content(
    payload: schemas.EnvContent,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Atualiza o arquivo .env global de forma segura."""
    env_path = os.path.join(PROJECT_ROOT, ".env")

    try:
        validation = validate_env_payload(payload.content)
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Conteúdo do .env inválido.",
                    "issues": [item.model_dump() for item in validation.issues],
                },
            )
        backup_relpath = backup_env_file(PROJECT_ROOT, env_path)
        write_env_content(env_path, payload.content)

        logger.info("Arquivo .env global atualizado via API.")

        audit_entry = log_audit(
            db,
            "UPDATE_ENV",
            "SYSTEM",
            "GLOBAL",
            "API_ADMIN",
            json.dumps(
                {
                    "message": "O arquivo .env foi modificado via Dashboard.",
                    "backup": backup_relpath,
                }
            ),
        )
        db.flush()
        db.commit()

        return {
            "message": "Arquivo .env salvo com sucesso. Reinicie o Orchestrator para aplicar certas mudanças.",
            "backup": backup_relpath,
            "backup_path": backup_relpath,
            "validated": True,
            "audit_id": audit_entry.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao salvar .env: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Erro ao salvar o arquivo: {str(e)}"
        ) from e


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    """Endpoint Prometheus — texto plain com todas as métricas do sistema (3.4/Fase 3)."""
    body, content_type = _metrics.get_metrics_response()
    if body is None:
        raise HTTPException(
            status_code=503,
            detail="prometheus_client não instalado. Adicione 'prometheus-client' ao requirements.in.",
        )
    return Response(content=body, media_type=content_type)

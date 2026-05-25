# pylint: disable=all
# mypy: ignore-errors
"""

Router: Automations - CRUD completo com paginacao, validacao e auditoria. v5.1.0

"""

import json
import logging
import math
import os
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models, schemas  # type: ignore
from ..constants import EXECUTION_ACTIVE_STATUSES, PRIORITY_NORMAL
from ..database import get_db
from ..middleware import get_api_key
from ..runtime import get_project_root, trigger_worker_wakeup
from ..services.automation_preflight import build_automation_preflight
from ..services.automation_snapshot import (
    build_automation_response as build_operational_automation_response,
    build_automation_response_batch,
    load_snapshot_dependencies,
)
from ..services.execution_runtime import (
    build_queued_execution,
    generate_execution_id,
    get_group_active_execution,
)
from ..services.scheduler_runtime import (
    extract_automation_id_from_job,
    reload_scheduled_tasks,
    scheduler,
)
from ..services.metrics import (
    get_automation_metrics_24h,
    get_latest_execution_snapshot_by_automation,
)
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/automations", tags=["Automations"])

PROJECT_ROOT = get_project_root()


def _reload_scheduler_safe() -> None:
    """Recarrega o APScheduler sem quebrar a operacao CRUD que ja foi persistida."""
    try:
        reload_scheduled_tasks()
    except Exception as e:
        logger.error(f"Falha ao recarregar agendador apos alteracao: {e}")


def _load_next_run_lookup():
    """Mapeia proxima execucao por automacao consultando o scheduler em memoria."""
    lookup = {}
    try:
        for job in scheduler.get_jobs():
            auto_id = extract_automation_id_from_job(job.id)
            if auto_id is None or not job.next_run_time:
                continue
            candidate = schemas.parse_dt_br(job.next_run_time)
            if candidate is None:
                continue
            current = lookup.get(auto_id)
            if current is None or candidate < current:
                lookup[auto_id] = candidate
    except Exception as e:
        logger.warning(f"Nao foi possivel carregar next_run do scheduler: {e}")
    return lookup


def _build_automation_response(
    db: Session,
    auto: models.Automation,
    next_run_lookup=None,
    latest_execution_lookup=None,
    metrics_24h_lookup=None,
):
    if next_run_lookup is None:
        next_run_lookup = _load_next_run_lookup()
    if latest_execution_lookup is None:
        latest_execution_lookup = get_latest_execution_snapshot_by_automation(
            db, [int(auto.id)]
        )
    if metrics_24h_lookup is None:
        metrics_24h_lookup = get_automation_metrics_24h(db, [int(auto.id)])
    return build_operational_automation_response(
        auto=auto,
        next_run_lookup=next_run_lookup,
        latest_execution_lookup=latest_execution_lookup,
        metrics_24h_lookup=metrics_24h_lookup,
    )


def _resolve_automation_dir(script_path: str) -> str:
    """Resolve a pasta da automacao garantindo permanencia no PROJECT_ROOT."""
    if script_path.startswith("./") or script_path.startswith(".\\"):
        resolved_script = os.path.join(PROJECT_ROOT, script_path[2:])
    elif not os.path.isabs(script_path):
        resolved_script = os.path.join(PROJECT_ROOT, script_path)
    else:
        resolved_script = script_path

    auto_dir = os.path.dirname(os.path.abspath(os.path.normpath(resolved_script)))
    project_root = os.path.abspath(os.path.normpath(PROJECT_ROOT))
    if os.path.commonpath([project_root, auto_dir]) != project_root:
        raise HTTPException(
            status_code=403, detail="Diretorio da automacao fora do projeto."
        )
    return auto_dir


def _resolve_managed_file(auto_dir: str, filename: str) -> str:
    """Resolve arquivo gerenciado impedindo path traversal por nome ou symlink."""
    if os.path.basename(filename) != filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    target_path = os.path.abspath(os.path.normpath(os.path.join(auto_dir, filename)))
    auto_dir_abs = os.path.abspath(os.path.normpath(auto_dir))
    if os.path.commonpath([auto_dir_abs, target_path]) != auto_dir_abs:
        raise HTTPException(status_code=403, detail="Acesso negado ao arquivo.")
    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return target_path


def _backup_file_before_write(target_path: str, auto_dir: str) -> str:
    """Cria backup local antes de sobrescrever arquivo gerenciado."""
    backup_dir = os.path.join(auto_dir, ".orchestrator_backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = get_now_local().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"{os.path.basename(target_path)}.{ts}.bak"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(target_path, backup_path)
    return os.path.relpath(backup_path, auto_dir)


def _build_mutation_response(
    db: Session,
    auto: models.Automation,
    audit_id: int | None = None,
) -> schemas.AutomationResponse:
    response = _build_automation_response(db, auto)
    response.validated = True
    response.audit_id = audit_id
    return response


def _preflight_payload_or_422(payload: dict) -> schemas.AutomationPreflightResponse:
    try:
        return build_automation_preflight(payload, PROJECT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------

# LISTAGEM com paginacao e ordenacao

# ---------------------------------------------------------------------------


@router.get("", response_model=schemas.PaginatedResponse[schemas.AutomationResponse])
def list_automations(
    page: int = 1,
    per_page: int = 20,
    sort: str = "name",
    order: str = "asc",
    search: str = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Lista automacoes com paginacao, ordenacao e busca."""

    query = db.query(models.Automation)

    # Filtro de busca por nome

    if search:

        query = query.filter(models.Automation.name.ilike(f"%{search}%"))

    # Ordenacao

    sort_column = getattr(models.Automation, sort, models.Automation.name)

    if order == "desc":

        query = query.order_by(sort_column.desc())

    else:

        query = query.order_by(sort_column.asc())

    total = query.count()

    pages = math.ceil(total / per_page) if per_page > 0 else 1

    items = query.offset((page - 1) * per_page).limit(per_page).all()

    next_run_lookup = _load_next_run_lookup()
    snapshot_dependencies = load_snapshot_dependencies(db, items)
    result = build_automation_response_batch(
        items,
        next_run_lookup=next_run_lookup,
        latest_execution_lookup=snapshot_dependencies["latest_execution"],
        metrics_24h_lookup=snapshot_dependencies["metrics_24h"],
    )

    return schemas.PaginatedResponse(
        items=result, total=total, page=page, per_page=per_page, pages=pages
    )


# ---------------------------------------------------------------------------

# LISTAGEM SIMPLES (compatibilidade com Dashboard legado)

# ---------------------------------------------------------------------------


@router.get("/all", response_model=list[schemas.AutomationResponse])
def list_all_automations(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna todas as automacoes sem paginacao (uso interno do Dashboard)."""

    automations = db.query(models.Automation).order_by(models.Automation.name).all()

    next_run_lookup = _load_next_run_lookup()
    snapshot_dependencies = load_snapshot_dependencies(db, automations)
    result = build_automation_response_batch(
        automations,
        next_run_lookup=next_run_lookup,
        latest_execution_lookup=snapshot_dependencies["latest_execution"],
        metrics_24h_lookup=snapshot_dependencies["metrics_24h"],
    )

    return result


@router.post("/preflight", response_model=schemas.AutomationPreflightResponse)
def preflight_automation(
    payload: schemas.AutomationPreflightRequest,
    api_key: str = Depends(get_api_key),
):
    """Valida uma automação sem persistir alteração."""
    return _preflight_payload_or_422(payload.model_dump())


# ---------------------------------------------------------------------------

# GET por ID

# ---------------------------------------------------------------------------


@router.get("/{automation_id}", response_model=schemas.AutomationResponse)
def get_automation(
    automation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    return _build_automation_response(db, db_auto)



# ---------------------------------------------------------------------------

# CREATE

# ---------------------------------------------------------------------------


@router.post("", response_model=schemas.AutomationResponse, status_code=201)
def create_automation(
    automation: schemas.AutomationCreate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    existing = (
        db.query(models.Automation)
        .filter(models.Automation.name == automation.name)
        .first()
    )

    if existing:

        raise HTTPException(
            status_code=409, detail="Automação com este nome já existe."
        )

    preflight = _preflight_payload_or_422(automation.model_dump())
    db_auto = models.Automation(**preflight.normalized_payload)

    db.add(db_auto)

    db.flush()

    audit_entry = log_audit(
        db,
        "CREATE",
        "AUTOMATION",
        db_auto.id,
        get_client_ip(request),
        json.dumps(
            {
                **preflight.normalized_payload,
                "preflight": {
                    "resolved_script_path": preflight.resolved_script_path,
                    "warnings": preflight.warnings,
                },
            }
        ),
    )
    db.flush()

    db.commit()

    db.refresh(db_auto)

    logger.info(f"Automacao criada: {db_auto.name} (ID: {db_auto.id})")
    _reload_scheduler_safe()

    return _build_mutation_response(db, db_auto, audit_entry.id)


# ---------------------------------------------------------------------------

# UPDATE

# ---------------------------------------------------------------------------


@router.put("/{automation_id}", response_model=schemas.AutomationResponse)
def update_automation(
    automation_id: int,
    automation_update: schemas.AutomationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    update_data = automation_update.model_dump(exclude_unset=True)
    merged_payload = {
        "name": db_auto.name,
        "description": db_auto.description,
        "script_path": db_auto.script_path,
        "schedule": db_auto.schedule,
        "max_runtime_minutes": db_auto.max_runtime_minutes,
        "max_retries": db_auto.max_retries,
        "cooldown_minutes": db_auto.cooldown_minutes,
        "queue_group": db_auto.queue_group,
        "sla_minutes": db_auto.sla_minutes,
        "enabled": db_auto.enabled,
        "test_mode": db_auto.test_mode,
        "notification_channels": db_auto.notification_channels,
    }
    merged_payload.update(update_data)
    preflight = _preflight_payload_or_422(merged_payload)

    for key, value in preflight.normalized_payload.items():
        setattr(db_auto, key, value)

    _log_data = json.dumps(
        {
            "changes": update_data,
            "normalized_payload": preflight.normalized_payload,
            "warnings": preflight.warnings,
        }
    )

    audit_entry = log_audit(
        db, "UPDATE", "AUTOMATION", automation_id, get_client_ip(request), _log_data
    )
    db.flush()

    db.commit()

    db.refresh(db_auto)

    logger.info(f"Automacao atualizada: {db_auto.name} (ID: {automation_id})")
    _reload_scheduler_safe()

    return _build_mutation_response(db, db_auto, audit_entry.id)


@router.get("/{automation_id}/overview")
def get_automation_overview(
    automation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna payload consolidado da automacao para telas operacionais."""
    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    latest_execution_lookup = get_latest_execution_snapshot_by_automation(
        db, [automation_id]
    )
    metrics_24h_lookup = get_automation_metrics_24h(db, [automation_id])
    auto_resp = _build_automation_response(
        db,
        db_auto,
        latest_execution_lookup=latest_execution_lookup,
        metrics_24h_lookup=metrics_24h_lookup,
    )

    recent_execs = (
        db.query(models.Execution)
        .filter(models.Execution.automation_id == automation_id)
        .order_by(models.Execution.started_at.desc())
        .limit(10)
        .all()
    )
    recent_payload = []
    for item in recent_execs:
        summary = schemas.ExecutionSummary.model_validate(item)
        summary.automation_name = db_auto.name
        recent_payload.append(summary)

    return {
        "automation": auto_resp,
        "metrics_24h": {
            "success_count": auto_resp.success_24h,
            "error_count": auto_resp.failures_24h,
            "pending_count": auto_resp.pending_count,
        },
        "recent_executions": recent_payload,
    }


# ---------------------------------------------------------------------------

# DELETE

# ---------------------------------------------------------------------------


@router.delete("/{automation_id}")
def delete_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_name = db_auto.name

    log_audit(
        db,
        "DELETE",
        "AUTOMATION",
        automation_id,
        get_client_ip(request),
        f"Removida: {auto_name}",
    )

    db.delete(db_auto)

    db.commit()

    logger.info(f"Automacao removida: {auto_name} (ID: {automation_id})")
    _reload_scheduler_safe()

    return {"message": f"Automacao '{auto_name}' removida com sucesso."}


# ---------------------------------------------------------------------------

# START (Enfileirar execucao)

# ---------------------------------------------------------------------------


@router.post("/{automation_id}/start")
async def start_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    # Protecao contra execucao duplicada

    running = (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == automation_id,
            models.Execution.status.in_(["PENDING", "RUNNING"]),
        )
        .first()
    )

    if running:

        raise HTTPException(
            status_code=409,
            detail=f"Automação já possui uma execução ativa (ID: {running.id}).",
        )

    group_running = get_group_active_execution(
        db,
        db_auto.queue_group,
        exclude_automation_id=automation_id,
    )
    if group_running:
        raise HTTPException(
            status_code=409,
            detail=(
                "Grupo operacional já possui execução ativa "
                f"(Execução: {group_running.id}, Grupo: {db_auto.queue_group})."
            ),
        )

    if db_auto.cooldown_minutes and db_auto.cooldown_minutes > 0:
        latest_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == automation_id)
            .order_by(desc(models.Execution.started_at))
            .first()
        )
        if latest_exec and latest_exec.started_at:
            elapsed_minutes = (
                get_now_local() - latest_exec.started_at
            ).total_seconds() / 60
            if elapsed_minutes < db_auto.cooldown_minutes:
                remaining = round(db_auto.cooldown_minutes - elapsed_minutes, 1)
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Cooldown operacional ativo para esta automação. "
                        f"Aguarde aproximadamente {remaining} minuto(s)."
                    ),
                )

    exec_id = generate_execution_id("EXEC")

    client_ip = get_client_ip(request)

    db_exec = build_queued_execution(
        automation=db_auto,
        exec_id=exec_id,
        requested_by=client_ip,
        priority=PRIORITY_NORMAL,
    )

    db.add(db_exec)

    log_audit(
        db, "START", "EXECUTION", exec_id, client_ip, f"Disparado: {db_auto.name}"
    )

    db.commit()

    trigger_worker_wakeup()

    return {"message": "Automação enfileirada com sucesso.", "exec_id": exec_id}


@router.post("/test-mode/global")
def set_global_test_mode(
    enabled: bool,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Ativa ou desativa o Modo Teste para TODAS as automacoes cadastradas."""

    db.query(models.Automation).update(
        {
            models.Automation.test_mode: enabled,
            models.Automation.updated_at: get_now_local(),
        }
    )

    # Sincroniza a variavel de ambiente do Windows
    ps_script = os.path.join(PROJECT_ROOT, "Tools", "ConfigurarEmailTeste.ps1")
    if os.path.exists(ps_script):
        try:
            if enabled:
                subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        ps_script,
                    ],
                    check=True,
                )
            else:
                subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        ps_script,
                        "-Remover",
                    ],
                    check=True,
                )
        except Exception as e:
            logger.error(f"Erro ao sincronizar variavel AUTOMACAO_TEST_EMAIL: {e}")

    log_audit(
        db,
        "TEST_MODE_GLOBAL",
        "SYSTEM",
        "ALL",
        get_client_ip(request),
        f"Modo Teste Global: {enabled}",
    )

    db.commit()

    return {
        "message": f"Modo Teste Global {'ativado' if enabled else 'desativado'} para todas as automações."
    }


@router.post("/{automation_id}/test-mode")
def set_automation_test_mode(
    automation_id: int,
    enabled: bool,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Ativa ou desativa o Modo Teste para uma automacao especifica."""

    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    db_auto.test_mode = enabled

    log_audit(
        db,
        "TEST_MODE",
        "AUTOMATION",
        str(automation_id),
        get_client_ip(request),
        f"Modo Teste: {enabled} ({db_auto.name})",
    )

    db.commit()

    return {
        "message": f"Modo Teste da automação {db_auto.name} definido para {enabled}."
    }


# ---------------------------------------------------------------------------

# CONTROLE EM MASSA

# ---------------------------------------------------------------------------


@router.post("/control/pause-all")
def pause_all(
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    db.query(models.Automation).update({models.Automation.enabled: False})

    log_audit(db, "PAUSE_ALL", "AUTOMATION", None, get_client_ip(request))

    db.commit()
    _reload_scheduler_safe()

    return {"message": "Todas as automações pausadas."}


@router.post("/control/resume-all")
def resume_all(
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):

    db.query(models.Automation).update({models.Automation.enabled: True})

    log_audit(db, "RESUME_ALL", "AUTOMATION", None, get_client_ip(request))

    db.commit()
    _reload_scheduler_safe()

    return {"message": "Todas as automações retomadas."}


@router.post("/{automation_id}/pause")
def pause_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    db_auto.enabled = False
    log_audit(
        db,
        "PAUSE",
        "AUTOMATION",
        str(automation_id),
        get_client_ip(request),
        db_auto.name,
    )
    db.commit()
    _reload_scheduler_safe()
    return {"message": f"Automação '{db_auto.name}' pausada."}


@router.post("/{automation_id}/resume")
def resume_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    db_auto.enabled = True
    log_audit(
        db,
        "RESUME",
        "AUTOMATION",
        str(automation_id),
        get_client_ip(request),
        db_auto.name,
    )
    db.commit()
    _reload_scheduler_safe()
    return {"message": f"Automação '{db_auto.name}' retomada."}


@router.post(
    "/{automation_id}/clone", response_model=schemas.AutomationResponse, status_code=201
)
def clone_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_auto = (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    base_name = f"{db_auto.name} (Clone)"
    candidate = base_name
    idx = 2
    while (
        db.query(models.Automation).filter(models.Automation.name == candidate).first()
    ):
        candidate = f"{base_name} {idx}"
        idx += 1

    clone = models.Automation(
        name=candidate,
        description=db_auto.description,
        script_path=db_auto.script_path,
        schedule=db_auto.schedule,
        max_runtime_minutes=db_auto.max_runtime_minutes,
        max_retries=db_auto.max_retries,
        cooldown_minutes=db_auto.cooldown_minutes,
        queue_group=db_auto.queue_group,
        enabled=False,
        test_mode=db_auto.test_mode,
        notification_channels=db_auto.notification_channels,
    )
    db.add(clone)
    db.flush()
    log_audit(
        db,
        "CLONE",
        "AUTOMATION",
        str(clone.id),
        get_client_ip(request),
        json.dumps({"source_automation_id": automation_id}),
    )
    db.commit()
    db.refresh(clone)
    _reload_scheduler_safe()
    return _build_mutation_response(db, clone)

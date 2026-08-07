"""

Router: Automations - CRUD completo com paginacao, validacao e auditoria. v1.0.0

"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import PRIORITY_NORMAL
from ..database import get_db
from ..middleware import get_api_key
from ..runtime import get_project_root, scheduler, trigger_worker_wakeup
from ..services import automation_repository as repo, env_admin
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
from ..services.metrics_queries import (
    get_automation_metrics_24h,
    get_latest_execution_snapshot_by_automation,
)
from ..services.scheduler_runtime import (
    extract_automation_id_from_job,
    reload_scheduled_tasks,
)
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/automations", tags=["Automations"])

PROJECT_ROOT = get_project_root()

# Cache TTL de 30s para next_run_lookup — evita re-iteração do scheduler a cada request
_NEXT_RUN_CACHE: dict[int, Any] | None = None
_NEXT_RUN_CACHE_AT: float = 0.0
_NEXT_RUN_CACHE_TTL = 30.0
_next_run_cache_lock = threading.Lock()


def _invalidate_next_run_cache() -> None:
    global _NEXT_RUN_CACHE, _NEXT_RUN_CACHE_AT  # pylint: disable=global-statement
    with _next_run_cache_lock:
        _NEXT_RUN_CACHE = None
        _NEXT_RUN_CACHE_AT = 0.0


def _reload_scheduler_safe() -> None:
    """Recarrega o APScheduler sem quebrar a operacao CRUD que ja foi persistida."""
    _invalidate_next_run_cache()
    try:
        reload_scheduled_tasks()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Falha ao recarregar agendador apos alteracao: %s", e)


def _load_next_run_lookup() -> dict[int, Any]:
    """Mapeia proxima execucao por automacao consultando o scheduler em memoria (com cache TTL)."""
    global _NEXT_RUN_CACHE, _NEXT_RUN_CACHE_AT  # pylint: disable=global-statement
    now = time.monotonic()
    with _next_run_cache_lock:
        if (
            _NEXT_RUN_CACHE is not None
            and (now - _NEXT_RUN_CACHE_AT) < _NEXT_RUN_CACHE_TTL
        ):
            return _NEXT_RUN_CACHE
    lookup: dict[int, Any] = {}
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
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Nao foi possivel carregar next_run do scheduler: %s", e)
    with _next_run_cache_lock:
        _NEXT_RUN_CACHE = lookup
        _NEXT_RUN_CACHE_AT = now
    return lookup


def _build_automation_response(
    db: Session,
    auto: models.Automation,
    next_run_lookup: dict[int, Any] | None = None,
    latest_execution_lookup: dict[int, dict[str, Any]] | None = None,
    metrics_24h_lookup: dict[int, dict[str, Any]] | None = None,
) -> schemas.AutomationResponse:
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


def _build_mutation_response(
    db: Session,
    auto: models.Automation,
    audit_id: int | None = None,
) -> schemas.AutomationResponse:
    response = _build_automation_response(db, auto)
    response.validated = True
    response.audit_id = audit_id
    return response


def _preflight_payload_or_422(
    payload: dict[str, Any],
) -> schemas.AutomationPreflightResponse:
    try:
        preflight = build_automation_preflight(payload, PROJECT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not preflight.valid:
        issue = next(iter(preflight.governance.blocking_issues), None)
        detail = issue.message if issue else "Pré-validação governada reprovada."
        raise HTTPException(status_code=422, detail=detail)
    return preflight


# ---------------------------------------------------------------------------

# LISTAGEM com paginacao e ordenacao

# ---------------------------------------------------------------------------


@router.get("", response_model=schemas.PaginatedResponse[schemas.AutomationResponse])
def list_automations(  # pylint: disable=R0913,R0917
    # `per_page` negativo virava `LIMIT -1` no SQLite (sem limite) e `page`
    # negativo produzia OFFSET negativo — ambos aceitos sem validação.
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    sort: str = "name",
    order: str = "asc",
    search: str | None = None,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.PaginatedResponse[schemas.AutomationResponse]:
    """Lista automacoes com paginacao, ordenacao e busca."""

    if sort not in repo.ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Campo de ordenação inválido: '{sort}'. "
                f"Opções válidas: {sorted(repo.ALLOWED_SORT_FIELDS)}"
            ),
        )

    items, total = repo.paginate(
        db,
        search=search,
        sort=sort,
        descending=order == "desc",
        page=page,
        per_page=per_page,
    )

    pages = math.ceil(total / per_page) if per_page > 0 else 1

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
    _api_key: str = Depends(get_api_key),
) -> list[schemas.AutomationResponse]:
    """Retorna todas as automacoes sem paginacao (uso interno do Dashboard)."""

    automations = repo.list_all_ordered(db)

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
    _api_key: str = Depends(get_api_key),
) -> schemas.AutomationPreflightResponse:
    """Valida uma automação sem persistir alteração."""
    try:
        return build_automation_preflight(payload.model_dump(), PROJECT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------

# GET por ID

# ---------------------------------------------------------------------------


@router.get("/{automation_id}", response_model=schemas.AutomationResponse)
def get_automation(
    automation_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.AutomationResponse:

    db_auto = repo.get_by_id(db, automation_id)

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
    _api_key: str = Depends(get_api_key),
) -> schemas.AutomationResponse:

    existing = repo.get_by_name(db, automation.name)

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

    logger.info("Automacao criada: %s (ID: %s)", db_auto.name, db_auto.id)
    _reload_scheduler_safe()

    return _build_mutation_response(db, db_auto, int(audit_entry.id))


# ---------------------------------------------------------------------------

# UPDATE

# ---------------------------------------------------------------------------


@router.put("/{automation_id}", response_model=schemas.AutomationResponse)
def update_automation(
    automation_id: int,
    automation_update: schemas.AutomationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.AutomationResponse:

    db_auto = repo.get_by_id(db, automation_id)

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

    logger.info("Automacao atualizada: %s (ID: %s)", db_auto.name, automation_id)
    _reload_scheduler_safe()

    return _build_mutation_response(db, db_auto, int(audit_entry.id))


@router.get(
    "/{automation_id}/overview", response_model=schemas.AutomationOverviewResponse
)
def get_automation_overview(
    automation_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.AutomationOverviewResponse:
    """Retorna payload consolidado da automacao para telas operacionais."""
    db_auto = repo.get_by_id(db, automation_id)
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

    recent_execs = repo.get_recent_executions(db, automation_id)
    recent_payload = []
    for item in recent_execs:
        summary = schemas.ExecutionSummary.model_validate(item)
        summary.automation_name = str(db_auto.name)
        recent_payload.append(summary)

    return schemas.AutomationOverviewResponse(
        automation=auto_resp,
        metrics_24h=schemas.AutomationOverviewMetrics24h(
            success_count=auto_resp.success_24h,
            error_count=auto_resp.failures_24h,
            pending_count=auto_resp.pending_count,
        ),
        recent_executions=recent_payload,
    )


# ---------------------------------------------------------------------------

# DELETE

# ---------------------------------------------------------------------------


@router.delete("/{automation_id}")
def delete_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:

    db_auto = repo.get_by_id(db, automation_id)

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_name = db_auto.name

    # Bloqueia a remoção enquanto houver execução ativa. `start_automation` já
    # validava isso; `delete_automation` não fazia checagem nenhuma — e com
    # `cascade="all, delete-orphan"` no ORM mais `ondelete="CASCADE"` na FK
    # (com PRAGMA foreign_keys=ON), apagar a automação removia a linha da
    # execução RUNNING enquanto o processo PowerShell continuava vivo. O worker
    # então chamava `complete_process_execution`, que faz `.first()` e devolve
    # None em silêncio: o processo terminava sem registro, sem artefato
    # catalogado e sem alerta.
    execucao_ativa = repo.get_active_execution(db, automation_id)
    if execucao_ativa:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Automação possui execução ativa ({execucao_ativa.id}, "
                f"status {execucao_ativa.status}). Aguarde o término ou pare a "
                "execução antes de remover."
            ),
        )

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

    logger.info("Automacao removida: %s (ID: %s)", auto_name, automation_id)
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
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:

    db_auto = repo.get_by_id(db, automation_id)

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    # Protecao contra execucao duplicada

    running = repo.get_active_execution(db, automation_id)

    if running:

        raise HTTPException(
            status_code=409,
            detail=f"Automação já possui uma execução ativa (ID: {running.id}).",
        )

    group_running = get_group_active_execution(
        db,
        str(db_auto.queue_group) if db_auto.queue_group else None,
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
        latest_exec = repo.get_latest_execution(db, automation_id)
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

    try:
        db.commit()
    except IntegrityError as exc:
        # O índice único parcial (migration 20260731_01) venceu a corrida entre
        # a checagem acima e este commit. Antes da constraint, as duas inserções
        # passavam e a automação rodava duas vezes.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe uma execução ativa para esta automação.",
        ) from exc

    trigger_worker_wakeup()

    return {"message": "Automação enfileirada com sucesso.", "exec_id": exec_id}


@router.post("/test-mode/global")
def set_global_test_mode(
    enabled: bool,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:
    """Ativa ou desativa o Modo Teste para TODAS as automacoes cadastradas."""

    repo.set_test_mode_for_all(db, enabled)

    # Sincroniza a variavel de ambiente do Windows (orquestracao no service, #12)
    env_admin.sync_global_test_mode_env(enabled, PROJECT_ROOT)

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
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:
    """Ativa ou desativa o Modo Teste para uma automacao especifica."""

    db_auto = repo.get_by_id(db, automation_id)

    if not db_auto:

        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    db_auto.test_mode = enabled  # type: ignore[assignment]

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
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:

    repo.set_enabled_for_all(db, False)

    log_audit(db, "PAUSE_ALL", "AUTOMATION", None, get_client_ip(request))

    db.commit()
    _reload_scheduler_safe()

    return {"message": "Todas as automações pausadas."}


@router.post("/control/resume-all")
def resume_all(
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:

    repo.set_enabled_for_all(db, True)

    log_audit(db, "RESUME_ALL", "AUTOMATION", None, get_client_ip(request))

    db.commit()
    _reload_scheduler_safe()

    return {"message": "Todas as automações retomadas."}


@router.post("/{automation_id}/pause")
def pause_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:
    db_auto = repo.get_by_id(db, automation_id)
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    db_auto.enabled = False  # type: ignore[assignment]
    log_audit(
        db,
        "PAUSE",
        "AUTOMATION",
        str(automation_id),
        get_client_ip(request),
        str(db_auto.name),
    )
    db.commit()
    _reload_scheduler_safe()
    return {"message": f"Automação '{db_auto.name}' pausada."}


@router.post("/{automation_id}/resume")
def resume_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, str]:
    db_auto = repo.get_by_id(db, automation_id)
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    db_auto.enabled = True  # type: ignore[assignment]
    log_audit(
        db,
        "RESUME",
        "AUTOMATION",
        str(automation_id),
        get_client_ip(request),
        str(db_auto.name),
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
    _api_key: str = Depends(get_api_key),
) -> schemas.AutomationResponse:
    db_auto = repo.get_by_id(db, automation_id)
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    candidate = repo.next_available_clone_name(db, f"{db_auto.name} (Clone)")

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
        # `sla_minutes` era omitido até 31/07/2026: o clone nascia com SLA nulo
        # e `collect_sla_breaches` simplesmente não o avaliava — a automação
        # desaparecia do painel de violação sem erro nem warning. Como o clone
        # nasce desabilitado, o defeito só se manifestava depois que alguém
        # habilitasse a cópia, longe do momento da criação.
        # O teste `test_clone_copia_todos_os_campos_operacionais` reprova quando
        # uma coluna nova de `Automation` fica de fora desta lista.
        sla_minutes=db_auto.sla_minutes,
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

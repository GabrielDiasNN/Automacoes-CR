"""
Router: Automations - CRUD completo com paginacao, validacao e auditoria. v5.0
"""

import json
import logging
import math
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..middleware import get_api_key
from ..utils import log_audit, get_client_ip, validate_script_path

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/automations", tags=["Automations"])



PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


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

    # Enriquecer com last_status
    result = []
    for auto in items:
        auto_dict = schemas.AutomationResponse.model_validate(auto)
        last_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto.id)
            .order_by(models.Execution.started_at.desc())
            .first()
        )
        if last_exec:
            auto_dict.last_status = last_exec.status
        result.append(auto_dict)

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
    result = []
    for auto in automations:
        auto_resp = schemas.AutomationResponse.model_validate(auto)
        last_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto.id)
            .order_by(models.Execution.started_at.desc())
            .first()
        )
        if last_exec:
            auto_resp.last_status = last_exec.status
        result.append(auto_resp)
    return result


# ---------------------------------------------------------------------------
# GET por ID
# ---------------------------------------------------------------------------

@router.get("/{automation_id}", response_model=schemas.AutomationResponse)
def get_automation(
    automation_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada.")
    return db_auto


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
    existing = db.query(models.Automation).filter(models.Automation.name == automation.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Automacao com este nome ja existe.")

    # --- Pilar V: Pre-flight de existencia do script ---
    ok, result = validate_script_path(automation.script_path, PROJECT_ROOT)
    if not ok:
        raise HTTPException(status_code=422, detail=f"Validacao do script: {result}")

    db_auto = models.Automation(**automation.model_dump())
    db.add(db_auto)
    db.flush()

    log_audit(db, "CREATE", "AUTOMATION", db_auto.id, get_client_ip(request), json.dumps(automation.model_dump()))
    db.commit()
    db.refresh(db_auto)
    logger.info(f"Automacao criada: {db_auto.name} (ID: {db_auto.id})")
    return db_auto


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
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada.")

    update_data = automation_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_auto, key, value)

    _log_data = json.dumps(update_data)
    log_audit(db, "UPDATE", "AUTOMATION", automation_id, get_client_ip(request), _log_data)
    db.commit()
    db.refresh(db_auto)
    logger.info(f"Automacao atualizada: {db_auto.name} (ID: {automation_id})")
    return db_auto


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
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada.")

    auto_name = db_auto.name
    log_audit(db, "DELETE", "AUTOMATION", automation_id, get_client_ip(request), f"Removida: {auto_name}")

    db.delete(db_auto)
    db.commit()
    logger.info(f"Automacao removida: {auto_name} (ID: {automation_id})")
    return {"message": f"Automacao '{auto_name}' removida com sucesso."}


# ---------------------------------------------------------------------------
# START (Enfileirar execucao)
# ---------------------------------------------------------------------------

@router.post("/{automation_id}/start")
def start_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    import time as _time

    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada.")

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
            detail=f"Automacao ja possui uma execucao ativa (ID: {running.id})."
        )

    exec_id = f"EXEC_{int(_time.time())}"
    client_ip = get_client_ip(request)

    db_exec = models.Execution(
        id=exec_id,
        automation_id=db_auto.id,
        status="PENDING",
        requested_by=client_ip,
    )
    db.add(db_exec)

    log_audit(db, "START", "EXECUTION", exec_id, client_ip, f"Disparado: {db_auto.name}")
    db.commit()

    return {"message": "Automacao enfileirada com sucesso.", "exec_id": exec_id}
    

# --- MODO TESTE (GLOBAL) ---

@router.post("/test-mode/global")
def set_global_test_mode(
    enabled: bool,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Ativa ou desativa o Modo Teste para TODAS as automacoes cadastradas."""
    db.query(models.Automation).update({models.Automation.test_mode: enabled})
    log_audit(db, "TEST_MODE_GLOBAL", "SYSTEM", "ALL", get_client_ip(request), f"Modo Teste Global: {enabled}")
    db.commit()
    return {"message": f"Modo Teste Global {'ativado' if enabled else 'desativado'} para todas as automacoes."}








@router.post("/{automation_id}/test-mode")
def set_automation_test_mode(
    automation_id: int,
    enabled: bool,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Ativa ou desativa o Modo Teste para uma automacao especifica."""
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada.")
    
    db_auto.test_mode = enabled
    log_audit(db, "TEST_MODE", "AUTOMATION", str(automation_id), get_client_ip(request), f"Modo Teste: {enabled} ({db_auto.name})")
    db.commit()
    return {"message": f"Modo Teste da automacao {db_auto.name} definido para {enabled}."}


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
    return {"message": "Todas as automacoes pausadas."}


@router.post("/control/resume-all")
def resume_all(
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db.query(models.Automation).update({models.Automation.enabled: True})
    log_audit(db, "RESUME_ALL", "AUTOMATION", None, get_client_ip(request))
    db.commit()
    return {"message": "Todas as automacoes retomadas."}

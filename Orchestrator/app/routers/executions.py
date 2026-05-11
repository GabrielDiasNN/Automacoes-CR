"""
Router: Executions - Historico de execucoes com filtros, logs, artefatos e controle. v5.0
"""

import logging
import math

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..middleware import get_api_key
from ..utils import log_audit, get_client_ip

import os

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/executions", tags=["Executions"])

# Raiz do projeto para resolver caminhos
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# LISTAGEM GLOBAL com filtros e paginacao
# ---------------------------------------------------------------------------

@router.get("", response_model=schemas.PaginatedResponse[schemas.ExecutionSummary])
def list_executions(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    automation_id: Optional[int] = None,
    requested_by: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Lista execucoes com filtros avancados e paginacao."""
    query = db.query(models.Execution)

    if status:
        query = query.filter(models.Execution.status == status.upper())
    if automation_id:
        query = query.filter(models.Execution.automation_id == automation_id)
    if requested_by:
        query = query.filter(models.Execution.requested_by.ilike(f"%{requested_by}%"))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(models.Execution.started_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(models.Execution.started_at <= dt_to)
        except ValueError:
            pass

    query = query.order_by(desc(models.Execution.started_at))

    total = query.count()
    pages = math.ceil(total / per_page) if per_page > 0 else 1
    items_raw = query.offset((page - 1) * per_page).limit(per_page).all()

    # Enriquecer com nome da automacao
    items = []
    for ex in items_raw:
        summary = schemas.ExecutionSummary.model_validate(ex)
        auto = db.query(models.Automation.name).filter(models.Automation.id == ex.automation_id).scalar()
        summary.automation_name = auto
        items.append(summary)

    return schemas.PaginatedResponse(
        items=items, total=total, page=page, per_page=per_page, pages=pages
    )


# ---------------------------------------------------------------------------
# EXECUCOES POR AUTOMACAO (compatibilidade)
# ---------------------------------------------------------------------------

@router.get("/by-automation/{automation_id}", response_model=list[schemas.ExecutionSummary])
def list_by_automation(
    automation_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna execucoes de uma automacao especifica."""
    execs = (
        db.query(models.Execution)
        .filter(models.Execution.automation_id == automation_id)
        .order_by(desc(models.Execution.started_at))
        .limit(limit)
        .all()
    )
    auto_name = db.query(models.Automation.name).filter(models.Automation.id == automation_id).scalar()
    result = []
    for ex in execs:
        s = schemas.ExecutionSummary.model_validate(ex)
        s.automation_name = auto_name
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
):
    """Retorna as execucoes mais recentes de todas as automacoes."""
    execs = (
        db.query(models.Execution)
        .order_by(desc(models.Execution.started_at))
        .limit(limit)
        .all()
    )
    result = []
    for ex in execs:
        s = schemas.ExecutionSummary.model_validate(ex)
        auto_name = db.query(models.Automation.name).filter(models.Automation.id == ex.automation_id).scalar()
        s.automation_name = auto_name
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# GET por ID (com logs completos)
# ---------------------------------------------------------------------------

@router.get("/{exec_id}", response_model=schemas.ExecutionResponse)
def get_execution(
    exec_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada.")

    resp = schemas.ExecutionResponse.model_validate(db_exec)
    auto_name = db.query(models.Automation.name).filter(models.Automation.id == db_exec.automation_id).scalar()
    resp.automation_name = auto_name
    return resp


# ---------------------------------------------------------------------------
# LOGS de uma execucao (paginados por linhas)
# ---------------------------------------------------------------------------

@router.get("/{exec_id}/logs")
def get_execution_logs(
    exec_id: str,
    offset: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna logs de uma execucao com paginacao por linhas."""
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada.")

    all_lines = (db_exec.logs or "").split("\n")
    total_lines = len(all_lines)
    sliced = all_lines[offset: offset + limit]

    return {
        "exec_id": exec_id,
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "lines": sliced,
    }


# ---------------------------------------------------------------------------
# ARTEFATOS de uma execucao
# ---------------------------------------------------------------------------

@router.get("/{exec_id}/artifacts")
def list_artifacts(
    exec_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Lista artefatos gerados por uma execucao."""
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada.")

    import json
    artifacts = []
    if db_exec.artifacts:
        try:
            artifacts = json.loads(db_exec.artifacts)
        except (json.JSONDecodeError, TypeError):
            pass

    return {"exec_id": exec_id, "artifacts": artifacts}


@router.get("/{exec_id}/download")
def download_artifact(
    exec_id: str,
    filename: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Download de um artefato especifico."""
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada.")

    db_auto = db.query(models.Automation).filter(models.Automation.id == db_exec.automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada.")

    # Anti-path-traversal no filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo invalido.")

    script_path = db_auto.script_path
    if script_path.startswith("./") or script_path.startswith(".\\"):
        robot_dir = os.path.join(PROJECT_ROOT, os.path.dirname(script_path[2:]))
    else:
        robot_dir = os.path.dirname(os.path.abspath(script_path))

    file_path = os.path.join(robot_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Arquivo '{filename}' nao encontrado.")

    return FileResponse(path=file_path, filename=filename)


# ---------------------------------------------------------------------------
# STOP (Parar execucao)
# ---------------------------------------------------------------------------

@router.post("/{exec_id}/stop")
def stop_execution(
    exec_id: str,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada.")

    if db_exec.status not in ["PENDING", "RUNNING"]:
        raise HTTPException(status_code=400, detail="Execucao ja finalizada.")

    db_exec.status = "TERMINATED"
    db_exec.finished_at = datetime.now()

    log_audit(db, "STOP", "EXECUTION", exec_id, get_client_ip(request))
    db.commit()

    logger.info(f"Execucao interrompida: {exec_id}")
    return {"message": "Sinal de parada registrado.", "exec_id": exec_id}

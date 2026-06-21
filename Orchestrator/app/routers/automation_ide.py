# pylint: disable=all
# mypy: ignore-errors
"""
Router: Automation IDE - Gestão de scripts e código-fonte via Web IDE das automações.
"""

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..middleware import get_api_key
from ..utils import get_client_ip, log_audit
from .automations import (
    _backup_file_before_write,
    _resolve_automation_dir,
    _resolve_managed_file,
)

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/automations", tags=["Automation IDE"])


@router.get("/{auto_id}/scripts")
def get_automation_scripts(
    auto_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Busca arquivos de script (.ps1, .py, .sql, .bat) na pasta da automação."""
    auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = _resolve_automation_dir(auto.script_path)

    allowed_exts = (".ps1", ".py", ".sql", ".bat", ".md", ".js")
    scripts = []

    for filename in os.listdir(auto_dir):
        if not filename.endswith(allowed_exts) or filename.startswith("."):
            continue

        jf = os.path.join(auto_dir, filename)
        if not os.path.isfile(jf):
            continue

        try:
            with open(jf, encoding="utf-8") as f:
                content = f.read()
            scripts.append({"filename": filename, "content": content})
        except Exception:
            pass

    return scripts


@router.put(
    "/{auto_id}/scripts/{filename}",
    response_model=schemas.ManagedMutationResponse,
)
def update_automation_script(
    auto_id: int,
    filename: str,
    payload: schemas.FileContent,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Atualiza um arquivo de script garantindo o encoding correto."""
    auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = _resolve_automation_dir(auto.script_path)
    allowed_exts = (".ps1", ".py", ".sql", ".bat", ".md", ".js")
    if not filename.endswith(allowed_exts):
        raise HTTPException(status_code=400, detail="Extensão de script não permitida.")
    target_path = _resolve_managed_file(auto_dir, filename)

    try:
        backup_relpath = _backup_file_before_write(target_path, auto_dir)
        # Forçar UTF-8 with BOM para .ps1 e .psm1 (Soberania PT-BR)
        if filename.endswith(".ps1") or filename.endswith(".psm1"):
            with open(target_path, "w", encoding="utf-8-sig") as f:
                f.write(payload.content)
        else:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(payload.content)

        audit_entry = log_audit(
            db,
            "UPDATE_SCRIPT",
            "AUTOMATION",
            str(auto_id),
            get_client_ip(request),
            json.dumps({"filename": filename, "backup": backup_relpath}),
        )
        db.flush()
        db.commit()
        return {
            "message": "Código-fonte salvo com sucesso!",
            "validated": True,
            "backup": backup_relpath,
            "backup_path": backup_relpath,
            "audit_id": audit_entry.id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

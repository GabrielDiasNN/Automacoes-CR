"""
Router: Automation IDE - Gestão de scripts e código-fonte via Web IDE das automações.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..middleware import get_api_key
from ..runtime import get_project_root
from ..services.managed_file_access import (
    backup_file_before_write,
    resolve_automation_dir,
    resolve_managed_file,
)
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

PROJECT_ROOT = get_project_root()

router = APIRouter(prefix="/api/automations", tags=["Automation IDE"])


@router.get("/{auto_id}/scripts")
def get_automation_scripts(
    auto_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> list[dict[str, Any]]:
    auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = resolve_automation_dir(str(auto.script_path), PROJECT_ROOT)

    allowed_exts = (".ps1", ".py", ".sql", ".bat", ".md", ".js")
    scripts: list[dict[str, Any]] = []

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
        except OSError:
            pass

    return scripts


@router.put(
    "/{auto_id}/scripts/{filename}",
    response_model=schemas.ManagedMutationResponse,
)
def update_automation_script(  # pylint: disable=R0913,R0917
    auto_id: int,
    filename: str,
    payload: schemas.FileContent,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = resolve_automation_dir(str(auto.script_path), PROJECT_ROOT)
    allowed_exts = (".ps1", ".py", ".sql", ".bat", ".md", ".js")
    if not filename.endswith(allowed_exts):
        raise HTTPException(status_code=400, detail="Extensão de script não permitida.")
    target_path = resolve_managed_file(auto_dir, filename)

    try:
        backup_relpath = backup_file_before_write(target_path, auto_dir)
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
            details=json.dumps({"filename": filename, "backup": backup_relpath}),
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
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

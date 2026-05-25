# pylint: disable=all
# mypy: ignore-errors
"""
Router: Automation Config - Gestão de arquivos JSON de configuração das automações.
"""

import json
import logging
import os
import glob
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..middleware import get_api_key
from ..utils import get_client_ip, log_audit
from .automations import (
    _resolve_automation_dir,
    _resolve_managed_file,
    _backup_file_before_write,
)

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/automations", tags=["Automation Config"])


@router.get("/{auto_id}/configs")
def get_automation_configs(
    auto_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Busca arquivos JSON na pasta da automação."""
    auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = _resolve_automation_dir(auto.script_path)

    json_files = glob.glob(os.path.join(auto_dir, "*.json"))
    configs = []

    for jf in json_files:
        filename = os.path.basename(jf)
        # Ignora arquivos de lock e estado
        if (
            "wwebjs" in filename
            or filename.startswith(".")
            or "state" in filename.lower()
        ):
            continue
        try:
            with open(jf, "r", encoding="utf-8") as f:
                content = f.read()
            configs.append({"filename": filename, "content": content})
        except Exception as e:
            pass

    return configs


@router.put(
    "/{auto_id}/configs/{filename}",
    response_model=schemas.ManagedMutationResponse,
)
def update_automation_config(
    auto_id: int,
    filename: str,
    payload: schemas.FileContent,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Atualiza um arquivo JSON específico da automação."""
    auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = _resolve_automation_dir(auto.script_path)
    target_path = _resolve_managed_file(auto_dir, filename)
    if not filename.endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos JSON podem ser editados por esta rota.",
        )

    try:
        json.loads(payload.content)
        backup_relpath = _backup_file_before_write(target_path, auto_dir)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(payload.content)

        audit_entry = log_audit(
            db,
            "UPDATE_CONFIG",
            "AUTOMATION",
            str(auto_id),
            get_client_ip(request),
            json.dumps({"filename": filename, "backup": backup_relpath}),
        )
        db.flush()
        db.commit()
        return {
            "message": "Configuração salva com sucesso!",
            "validated": True,
            "backup": backup_relpath,
            "backup_path": backup_relpath,
            "audit_id": audit_entry.id,
        }
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400, detail="O conteúdo fornecido não é um JSON válido."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

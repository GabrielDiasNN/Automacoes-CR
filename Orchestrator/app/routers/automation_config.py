"""
Router: Automation Config - Gestão de arquivos JSON de configuração das automações.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..middleware import get_api_key
from ..runtime import get_project_root
from ..services import automation_repository as repo
from ..services.managed_file_access import (
    backup_file_before_write,
    resolve_automation_dir,
    resolve_managed_file,
)
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

PROJECT_ROOT = get_project_root()

router = APIRouter(prefix="/api/automations", tags=["Automation Config"])


@router.get("/{auto_id}/configs", response_model=list[schemas.ManagedFileEntry])
def get_automation_configs(
    auto_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> list[schemas.ManagedFileEntry]:
    auto = repo.get_by_id(db, auto_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = resolve_automation_dir(str(auto.script_path), PROJECT_ROOT)

    json_files = glob.glob(os.path.join(auto_dir, "*.json"))
    configs: list[schemas.ManagedFileEntry] = []

    for jf in json_files:
        filename = os.path.basename(jf)
        if (
            "wwebjs" in filename
            or filename.startswith(".")
            or "state" in filename.lower()
        ):
            continue
        try:
            with open(jf, encoding="utf-8") as f:
                content = f.read()
            configs.append(schemas.ManagedFileEntry(filename=filename, content=content))
        except OSError as exc:
            logger.warning("Falha ao ler config '%s': %s", filename, exc)

    return configs


@router.put(
    "/{auto_id}/configs/{filename}",
    response_model=schemas.ManagedMutationResponse,
)
def update_automation_config(  # pylint: disable=R0913,R0917
    auto_id: int,
    filename: str,
    payload: schemas.FileContent,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    auto = repo.get_by_id(db, auto_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    auto_dir = resolve_automation_dir(str(auto.script_path), PROJECT_ROOT)
    target_path = resolve_managed_file(auto_dir, filename)
    if not filename.endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Apenas arquivos JSON podem ser editados por esta rota.",
        )

    try:
        json.loads(payload.content)
        backup_relpath = backup_file_before_write(target_path, auto_dir)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(payload.content)

        audit_entry = log_audit(
            db,
            "UPDATE_CONFIG",
            "AUTOMATION",
            str(auto_id),
            get_client_ip(request),
            details=json.dumps({"filename": filename, "backup": backup_relpath}),
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
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="O conteúdo fornecido não é um JSON válido."
        ) from exc
    except OSError as e:
        # `str(e)` de OSError expõe o caminho absoluto — detalhe só no logger.
        logger.error("Falha de I/O ao salvar config %s/%s: %s", auto_id, filename, e)
        raise HTTPException(status_code=500, detail="Falha ao salvar o arquivo.") from e

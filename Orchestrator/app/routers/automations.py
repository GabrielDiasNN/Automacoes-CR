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
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit, validate_script_path

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/automations", tags=["Automations"])

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

def _reload_scheduler_safe() -> None:
    """Recarrega o APScheduler sem quebrar a operacao CRUD que ja foi persistida."""
    try:
        from ..main import reload_scheduled_tasks

        reload_scheduled_tasks()
    except Exception as e:
        logger.error(f"Falha ao recarregar agendador apos alteracao: {e}")

def _extract_automation_id_from_job(job_id: str):
    """Extrai automation_id de IDs de job no formato job_<id> ou job_<id>_<idx>."""
    if not job_id.startswith("job_"):
        return None
    parts = job_id.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None

def _load_next_run_lookup():
    """Mapeia proxima execucao por automacao consultando o scheduler em memoria."""
    lookup = {}
    try:
        from ..main import scheduler
        for job in scheduler.get_jobs():
            auto_id = _extract_automation_id_from_job(job.id)
            if auto_id is None or not job.next_run_time:
                continue
            current = lookup.get(auto_id)
            if current is None or job.next_run_time < current:
                lookup[auto_id] = job.next_run_time
    except Exception as e:
        logger.warning(f"Nao foi possivel carregar next_run do scheduler: {e}")
    return lookup

def _build_automation_response(db: Session, auto: models.Automation, next_run_lookup=None):
    if next_run_lookup is None:
        next_run_lookup = _load_next_run_lookup()
    auto_resp = schemas.AutomationResponse.model_validate(auto)
    last_exec = (
        db.query(models.Execution)
        .filter(models.Execution.automation_id == auto.id)
        .order_by(models.Execution.started_at.desc())
        .first()
    )
    if last_exec:
        auto_resp.last_status = last_exec.status
    auto_resp.next_run = schemas.format_dt_br(next_run_lookup.get(auto.id))
    try:
        parsed_schedule = schemas.parse_schedule(auto_resp.schedule)
    except Exception:
        parsed_schedule = None
    auto_resp.schedule_type = parsed_schedule.get("schedule_type") if parsed_schedule else "manual"
    auto_resp.schedule_summary = schemas.describe_schedule_payload(parsed_schedule)
    auto_resp.next_runs_preview = schemas.preview_next_runs(parsed_schedule, 3)
    return auto_resp

def _get_group_active_execution(
    db: Session,
    queue_group: str,
    exclude_automation_id: int,
):
    """Bloqueia concorrencia entre automacoes do mesmo grupo operacional."""
    if not queue_group:
        return None
    return (
        db.query(models.Execution)
        .join(models.Automation, models.Automation.id == models.Execution.automation_id)
        .filter(
            models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)),
            models.Automation.queue_group == queue_group,
            models.Automation.id != exclude_automation_id,
        )
        .order_by(models.Execution.started_at.desc())
        .first()
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
        raise HTTPException(status_code=403, detail="Diretorio da automacao fora do projeto.")
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

    next_run_lookup = _load_next_run_lookup()
    result = []

    for auto in items:

        result.append(_build_automation_response(db, auto, next_run_lookup))

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
    result = []

    for auto in automations:

        result.append(_build_automation_response(db, auto, next_run_lookup))

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

    # --- Pilar V: Pre-flight de existencia do script ---

    ok, result = validate_script_path(automation.script_path, PROJECT_ROOT)

    if not ok:

        raise HTTPException(status_code=422, detail=f"Validação do script: {result}")

    db_auto = models.Automation(**automation.model_dump())

    db.add(db_auto)

    db.flush()

    log_audit(
        db,
        "CREATE",
        "AUTOMATION",
        db_auto.id,
        get_client_ip(request),
        json.dumps(automation.model_dump()),
    )

    db.commit()

    db.refresh(db_auto)

    logger.info(f"Automacao criada: {db_auto.name} (ID: {db_auto.id})")
    _reload_scheduler_safe()

    return _build_automation_response(db, db_auto)

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

    for key, value in update_data.items():
        if key == "script_path":
            ok, result = validate_script_path(value, PROJECT_ROOT)
            if not ok:
                raise HTTPException(status_code=422, detail=f"Validação do script: {result}")

        setattr(db_auto, key, value)

    _log_data = json.dumps(update_data)

    log_audit(
        db, "UPDATE", "AUTOMATION", automation_id, get_client_ip(request), _log_data
    )

    db.commit()

    db.refresh(db_auto)

    logger.info(f"Automacao atualizada: {db_auto.name} (ID: {automation_id})")
    _reload_scheduler_safe()

    return _build_automation_response(db, db_auto)

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

    auto_resp = _build_automation_response(db, db_auto)

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

    if recent_execs:
        auto_resp.last_status = recent_execs[0].status

    from datetime import timedelta
    from ..timezone import get_now_local
    window_start = get_now_local() - timedelta(hours=24)
    success_24h = (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == automation_id,
            models.Execution.status == "SUCCESS",
            models.Execution.started_at >= window_start,
        )
        .count()
    )
    errors_24h = (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == automation_id,
            models.Execution.status.in_(["ERROR", "TIMEOUT", "TERMINATED"]),
            models.Execution.started_at >= window_start,
        )
        .count()
    )
    pending_now = (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == automation_id,
            models.Execution.status.in_(["PENDING", "RUNNING"]),
        )
        .count()
    )

    return {
        "automation": auto_resp,
        "metrics_24h": {
            "success_count": success_24h,
            "error_count": errors_24h,
            "pending_count": pending_now,
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

    import time as _time
    import uuid as _uuid

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

    group_running = _get_group_active_execution(db, db_auto.queue_group, automation_id)
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
                (get_now_local() - latest_exec.started_at).total_seconds() / 60
            )
            if elapsed_minutes < db_auto.cooldown_minutes:
                remaining = round(db_auto.cooldown_minutes - elapsed_minutes, 1)
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Cooldown operacional ativo para esta automação. "
                        f"Aguarde aproximadamente {remaining} minuto(s)."
                    ),
                )

    # exec_id com precisão de microsegundos + sufixo aleatório para evitar colisões (ADR-016)
    exec_id = f"EXEC_{int(_time.time())}_{_uuid.uuid4().hex[:4].upper()}"

    client_ip = get_client_ip(request)

    db_exec = models.Execution(
        id=exec_id,
        automation_id=db_auto.id,
        status="PENDING",
        priority=PRIORITY_NORMAL,
        retry_count=0,
        max_retries=db_auto.max_retries or 0,
        queue_group=db_auto.queue_group,
        requested_by=client_ip,
    )

    db.add(db_exec)

    log_audit(
        db, "START", "EXECUTION", exec_id, client_ip, f"Disparado: {db_auto.name}"
    )

    db.commit()

    # Sinaliza o Worker (Instant Wakeup v6.2.0)
    from ..main import task_queued_event
    task_queued_event.set()

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
                subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script], check=True)
            else:
                subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script, "-Remover"], check=True)
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
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    db_auto.enabled = False
    log_audit(db, "PAUSE", "AUTOMATION", str(automation_id), get_client_ip(request), db_auto.name)
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
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    db_auto.enabled = True
    log_audit(db, "RESUME", "AUTOMATION", str(automation_id), get_client_ip(request), db_auto.name)
    db.commit()
    _reload_scheduler_safe()
    return {"message": f"Automação '{db_auto.name}' retomada."}

@router.post("/{automation_id}/clone", response_model=schemas.AutomationResponse, status_code=201)
def clone_automation(
    automation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    db_auto = db.query(models.Automation).filter(models.Automation.id == automation_id).first()
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    base_name = f"{db_auto.name} (Clone)"
    candidate = base_name
    idx = 2
    while db.query(models.Automation).filter(models.Automation.name == candidate).first():
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
    return _build_automation_response(db, clone)

# ---------------------------------------------------------------------------
# CONFIG MANAGER (JSON) - Fase 3
# ---------------------------------------------------------------------------
import glob

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
        if "wwebjs" in filename or filename.startswith(".") or "state" in filename.lower():
            continue
        try:
            with open(jf, "r", encoding="utf-8") as f:
                content = f.read()
            configs.append({"filename": filename, "content": content})
        except Exception as e:
            pass

    return configs

@router.put("/{auto_id}/configs/{filename}")
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
        raise HTTPException(status_code=400, detail="Apenas arquivos JSON podem ser editados por esta rota.")

    try:
        json.loads(payload.content)
        backup_relpath = _backup_file_before_write(target_path, auto_dir)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(payload.content)

        log_audit(
            db,
            "UPDATE_CONFIG",
            "AUTOMATION",
            str(auto_id),
            get_client_ip(request),
            json.dumps({"filename": filename, "backup": backup_relpath}),
        )
        db.commit()
        return {"message": "Configuração salva com sucesso!", "backup": backup_relpath}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="O conteúdo fornecido não é um JSON válido.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# WEB IDE MANAGER (Scripts) - Fase 4
# ---------------------------------------------------------------------------

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
            with open(jf, "r", encoding="utf-8") as f:
                content = f.read()
            scripts.append({"filename": filename, "content": content})
        except Exception:
            pass

    return scripts

@router.put("/{auto_id}/scripts/{filename}")
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

        log_audit(
            db,
            "UPDATE_SCRIPT",
            "AUTOMATION",
            str(auto_id),
            get_client_ip(request),
            json.dumps({"filename": filename, "backup": backup_relpath}),
        )
        db.commit()
        return {"message": "Código-fonte salvo com sucesso!", "backup": backup_relpath}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

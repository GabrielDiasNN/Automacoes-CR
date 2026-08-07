"""
Router: Executions - Histórico de execuções com decorações operacionais (A2, A3), filtros avançados, logs, artefatos e controle de fila. v1.0.0
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query as SAQuery, Session

from .. import models, schemas
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_ALLOWED_PRIORITIES,
    EXECUTION_ALLOWED_STATUSES,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_TERMINATED,
    EXECUTION_TERMINAL_STATUSES,
)
from ..database import get_db
from ..middleware import get_api_key
from ..path_safety import is_contained
from ..runtime import get_project_root, trigger_worker_wakeup
from ..security import sanitize_log_payload, truncate_log_payload
from ..services import execution_repository as exec_repo
from ..services.execution_decoration import (
    build_active_execution_maps,
    decorate_execution_summary,
)
from ..services.execution_runtime import (
    RequeueValidationError,
    prepare_requeue,
)
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit

# `SAQuery` é o `sqlalchemy.orm.Query` sob alias, usado só como anotação de tipo.
# Sem o alias ele sombreava o `fastapi.Query`, e `Query(0, ge=0)` resolvia para o
# construtor do SQLAlchemy — TypeError na coleta dos testes.
logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/executions", tags=["Executions"])

# Raiz do projeto para resolver caminhos
PROJECT_ROOT = get_project_root()


# ---------------------------------------------------------------------------
# LISTAGEM GLOBAL com filtros e paginação
# ---------------------------------------------------------------------------


def _apply_execution_filters(  # pylint: disable=R0913,R0914,R0917
    query: SAQuery[models.Execution],
    status: str | None,
    automation_id: int | None,
    queue_group: str | None,
    priority: str | None,
    requested_by: str | None,
    date_from: str | None,
    date_to: str | None,
) -> SAQuery[models.Execution]:
    """Aplica filtros opcionais à query de execuções e valida entradas."""
    if status:
        normalized_status = status.upper()
        if normalized_status not in EXECUTION_ALLOWED_STATUSES:
            allowed = ", ".join(sorted(EXECUTION_ALLOWED_STATUSES))
            raise HTTPException(
                status_code=422, detail=f"status inválido. Use: {allowed}."
            )
        query = query.filter(models.Execution.status == normalized_status)
    if priority:
        normalized_priority = priority.upper()
        if normalized_priority not in EXECUTION_ALLOWED_PRIORITIES:
            allowed = ", ".join(sorted(EXECUTION_ALLOWED_PRIORITIES))
            raise HTTPException(
                status_code=422, detail=f"priority inválida. Use: {allowed}."
            )
        query = query.filter(models.Execution.priority == normalized_priority)
    if automation_id:
        query = query.filter(models.Execution.automation_id == automation_id)
    if queue_group:
        query = query.filter(models.Execution.queue_group == queue_group)
    if requested_by:
        query = query.filter(models.Execution.requested_by.ilike(f"%{requested_by}%"))
    dt_from: datetime | None = None
    dt_to: datetime | None = None
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(models.Execution.started_at >= dt_from)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="date_from inválido. Use formato ISO-8601."
            ) from exc
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(models.Execution.started_at <= dt_to)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="date_to inválido. Use formato ISO-8601."
            ) from exc
    if dt_from and dt_to and dt_from > dt_to:
        raise HTTPException(
            status_code=422, detail="date_from não pode ser maior que date_to."
        )
    return query


@router.get("", response_model=schemas.PaginatedResponse[schemas.ExecutionSummary])
def list_executions(  # pylint: disable=R0913,R0914,R0917
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
    automation_id: int | None = None,
    queue_group: str | None = None,
    priority: str | None = None,
    requested_by: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.PaginatedResponse[schemas.ExecutionSummary]:
    """Lista execuções com filtros avançados e paginação. Otimizado com joinedload."""
    if page < 1:
        raise HTTPException(status_code=422, detail="page deve ser >= 1.")
    if per_page < 1 or per_page > 200:
        raise HTTPException(
            status_code=422, detail="per_page deve estar entre 1 e 200."
        )

    query = exec_repo.base_query_with_automation(db)
    query = _apply_execution_filters(
        query,
        status,
        automation_id,
        queue_group,
        priority,
        requested_by,
        date_from,
        date_to,
    )
    query = query.order_by(desc(models.Execution.started_at))

    total = query.count()
    pages = math.ceil(total / per_page) if per_page > 0 else 1
    items_raw = query.offset((page - 1) * per_page).limit(per_page).all()

    active_by_auto, active_by_group = build_active_execution_maps(db)

    items = []
    for ex in items_raw:
        summary = schemas.ExecutionSummary.model_validate(ex)
        summary.automation_name = (
            ex.automation.name if ex.automation else "Desconhecido"
        )
        decorate_execution_summary(summary, ex, active_by_auto, active_by_group)
        items.append(summary)

    return schemas.PaginatedResponse(
        items=items, total=total, page=page, per_page=per_page, pages=pages
    )


# ---------------------------------------------------------------------------
# EXECUÇÕES POR AUTOMAÇÃO (compatibilidade)
# ---------------------------------------------------------------------------


@router.get(
    "/by-automation/{automation_id}", response_model=list[schemas.ExecutionSummary]
)
def list_by_automation(
    automation_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> list[schemas.ExecutionSummary]:
    """Retorna execuções de uma automação específica com decoração."""
    execs = exec_repo.get_recent_by_automation(db, automation_id, limit)

    active_by_auto, active_by_group = build_active_execution_maps(db)

    result = []
    for ex in execs:
        s = schemas.ExecutionSummary.model_validate(ex)
        s.automation_name = ex.automation.name if ex.automation else "Desconhecido"
        decorate_execution_summary(s, ex, active_by_auto, active_by_group)
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# RECENTES (para dashboard overview)
# ---------------------------------------------------------------------------


@router.get("/recent", response_model=list[schemas.ExecutionSummary])
def list_recent(
    limit: int = 10,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> list[schemas.ExecutionSummary]:
    """Retorna as execuções mais recentes de todas as automações com decoração."""
    execs = exec_repo.get_recent(db, limit)

    active_by_auto, active_by_group = build_active_execution_maps(db)

    result = []
    for ex in execs:
        s = schemas.ExecutionSummary.model_validate(ex)
        s.automation_name = ex.automation.name if ex.automation else "Desconhecido"
        decorate_execution_summary(s, ex, active_by_auto, active_by_group)
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# GET por ID (com logs completos e decoração)
# ---------------------------------------------------------------------------


@router.get("/{exec_id}", response_model=schemas.ExecutionResponse)
def get_execution(
    exec_id: str,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.ExecutionResponse:
    db_exec = exec_repo.get_by_id_with_automation(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    resp = schemas.ExecutionResponse.model_validate(db_exec)
    resp.automation_name = (
        db_exec.automation.name if db_exec.automation else "Desconhecido"
    )

    active_by_auto, active_by_group = build_active_execution_maps(db)
    decorate_execution_summary(resp, db_exec, active_by_auto, active_by_group)

    return resp


# ---------------------------------------------------------------------------
# LOGS de uma execução (paginados por linhas)
# ---------------------------------------------------------------------------


@router.get("/{exec_id}/logs", response_model=schemas.ExecutionLogsResponse)
def get_execution_logs(
    exec_id: str,
    # `offset` negativo fatiava a lista pelo fim silenciosamente; `limit` sem
    # teto materializava o log inteiro (até MAX_LOG_CHARS = 5 MB).
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.ExecutionLogsResponse:
    """Retorna logs de uma execução com paginação por linhas."""
    db_exec = exec_repo.get_by_id(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    all_lines = (db_exec.logs or "").split("\n")
    total_lines = len(all_lines)
    sliced = all_lines[offset : offset + limit]

    return schemas.ExecutionLogsResponse(
        exec_id=exec_id,
        total_lines=total_lines,
        offset=offset,
        limit=limit,
        lines=sliced,
    )


# ---------------------------------------------------------------------------
# ARTEFATOS de uma execução
# ---------------------------------------------------------------------------


@router.get("/{exec_id}/artifacts", response_model=schemas.ExecutionArtifactsResponse)
def list_artifacts(
    exec_id: str,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.ExecutionArtifactsResponse:
    """Lista artefatos gerados por uma execução."""
    db_exec = exec_repo.get_by_id(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    artifacts: list[str] = []
    if db_exec.artifacts:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            parsed = json.loads(str(db_exec.artifacts))
            # Precisa ser list[str] para bater com o response_model. A coluna
            # também é escrita por POST /telemetry/end/{exec_id} (telemetria
            # externa), que aceita `artifacts` como string livre sem validar a
            # forma — um JSON válido mas fora do formato (dict, lista com
            # não-string) antes era servido cru; com response_model declarado
            # o FastAPI falharia a validação e devolveria 500. Formato
            # inesperado cai no mesmo fallback de lista vazia do parse falho.
            if isinstance(parsed, list) and all(
                isinstance(item, str) for item in parsed
            ):
                artifacts = parsed

    return schemas.ExecutionArtifactsResponse(exec_id=exec_id, artifacts=artifacts)


# Extensões que `scan_for_artifacts` (worker.py) reconhece como entregável.
# Usadas como allowlist de compatibilidade para execuções cujo campo
# `artifacts` está nulo — anteriores ao campo, ou cuja varredura não capturou o
# arquivo (ela filtra por mtime). Sem esse fallback, corrigir o endpoint
# quebraria o download de todo o histórico; com ele, o que fica de fora são
# exatamente os arquivos que nunca deveriam ser servidos (`.json` de config e
# de estado, `.bak`, logs).
_ARTIFACT_EXTENSIONS = frozenset({".xlsx", ".html", ".pdf", ".csv"})


def _artifact_is_downloadable(db_exec: models.Execution, clean_filename: str) -> bool:
    """O arquivo pedido é um artefato desta execução?"""
    raw = db_exec.artifacts
    if raw:
        try:
            declarados = json.loads(str(raw))
        except (ValueError, TypeError):
            declarados = None
        if isinstance(declarados, list) and declarados:
            return clean_filename in {str(nome) for nome in declarados}

    return os.path.splitext(clean_filename)[1].lower() in _ARTIFACT_EXTENSIONS


@router.get("/{exec_id}/download")
def download_artifact(
    exec_id: str,
    filename: str,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> FileResponse:
    """Download de um artefato específico."""
    db_exec = exec_repo.get_by_id_with_automation(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    db_auto = db_exec.automation
    if not db_auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")

    # Anti-path-traversal no filename: permitir apenas nome puro do arquivo
    clean_filename = os.path.basename(filename)
    if clean_filename != filename:
        raise HTTPException(status_code=400, detail="Caminho de arquivo inválido.")

    script_path = db_auto.script_path
    if script_path.startswith("./") or script_path.startswith(".\\"):
        robot_dir = os.path.normpath(
            os.path.join(PROJECT_ROOT, os.path.dirname(script_path[2:]))
        )
    else:
        robot_dir = os.path.normpath(os.path.dirname(os.path.abspath(script_path)))

    # ALLOWLIST: o endpoint servia qualquer arquivo do diretório do robô, sem
    # nunca conferir `db_exec.artifacts` — `?filename=whatsapp-config.json`
    # devolvia o contactId do destinatário, e `delivery_state.json` o estado
    # operacional. O `exec_id` só era usado para descobrir o diretório.
    if not _artifact_is_downloadable(db_exec, clean_filename):
        raise HTTPException(status_code=403, detail="Acesso negado ao arquivo.")

    # `clean_filename`, não `filename`: o valor cru era o que entrava no join,
    # tornando a sanitização da linha acima inócua para a montagem do caminho.
    file_path = os.path.normpath(os.path.join(robot_dir, clean_filename))

    # Contenção por componentes de caminho, com symlink resolvido (era
    # `startswith`, que não respeita fronteira de diretório).
    if not is_contained(robot_dir, file_path):
        raise HTTPException(status_code=403, detail="Acesso negado ao arquivo.")

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=404, detail=f"Arquivo '{filename}' não encontrado."
        )

    return FileResponse(path=file_path, filename=filename)


# ---------------------------------------------------------------------------
# STOP (Parar execução)
# ---------------------------------------------------------------------------


@router.post("/{exec_id}/stop")
def stop_execution(
    exec_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    db_exec = exec_repo.get_by_id(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    if db_exec.status not in EXECUTION_ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="Execução já finalizada.")

    previous_status = db_exec.status
    db_exec.status = EXECUTION_STATUS_TERMINATED  # type: ignore[assignment]
    db_exec.finished_at = get_now_local()  # type: ignore[assignment]
    if db_exec.started_at and db_exec.finished_at:
        try:
            delta = db_exec.finished_at - db_exec.started_at
            delta_seconds = round(delta.total_seconds(), 2)
            db_exec.duration_seconds = max(0.0, delta_seconds)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    _stop_log: str = (
        str(db_exec.logs or "")
        + f"\n[STOP] Interrupcao solicitada via API enquanto status={previous_status}."
    )
    db_exec.logs = _stop_log  # type: ignore[assignment]

    log_audit(db, "STOP", "EXECUTION", exec_id, get_client_ip(request))
    db.commit()

    logger.info("Execucao interrompida: %s", exec_id)
    return {"message": "Sinal de parada registrado.", "exec_id": exec_id}


# ---------------------------------------------------------------------------
# REQUEUE (Reenfileirar execução com retry e concorrência)
# ---------------------------------------------------------------------------


@router.post("/{exec_id}/requeue", response_model=schemas.ExecutionQueueActionResponse)
def requeue_execution(
    exec_id: str,
    payload: schemas.ExecutionQueueActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> schemas.ExecutionQueueActionResponse:
    """Reenfileira uma execução terminal mantendo rastreabilidade de retry."""
    db_exec = exec_repo.get_by_id_with_automation(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    try:
        new_exec, audit_payload = prepare_requeue(
            db,
            db_exec,
            payload_reason=payload.reason,
            payload_requested_by=payload.requested_by,
            payload_priority=payload.priority,
            fallback_requested_by=get_client_ip(request),
        )
    except RequeueValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    db.add(new_exec)
    log_audit(
        db,
        "REQUEUE",
        "EXECUTION",
        exec_id,
        get_client_ip(request),
        json.dumps(audit_payload),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe uma execução ativa para esta automação.",
        ) from exc

    trigger_worker_wakeup()

    return schemas.ExecutionQueueActionResponse(
        message="Execução reenfileirada com sucesso.",
        source_exec_id=exec_id,
        queued_exec_id=str(new_exec.id),
        automation_id=int(db_exec.automation_id),
        retry_count=int(audit_payload["retry_count"]),
        max_retries=int(audit_payload["max_retries"]),
        recovery_action="REQUEUE_MANUAL",
    )


# ---------------------------------------------------------------------------
# TELEMETRIA EXTERNA (Terminal / VS Code)
# ---------------------------------------------------------------------------


@router.post("/telemetry/start")
def telemetry_start(
    payload: schemas.ExecutionTelemetryStart,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Inicia o registro de uma execução disparada externamente (ex: terminal)."""
    db_auto = exec_repo.get_automation_by_name(db, payload.automation_name)
    if not db_auto:
        raise HTTPException(
            status_code=404,
            detail=f"Automação '{payload.automation_name}' não encontrada.",
        )

    # Gerar ID único
    exec_id = f"TEL_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    new_exec = models.Execution(
        id=exec_id,
        automation_id=db_auto.id,
        status=EXECUTION_STATUS_RUNNING,
        requested_by="TERMINAL",
        started_at=get_now_local(),
        max_retries=db_auto.max_retries or 0,
        queue_group=db_auto.queue_group,
    )
    db.add(new_exec)

    log_audit(db, "START_TELEMETRY", "EXECUTION", exec_id, get_client_ip(request))
    try:
        db.commit()
    except IntegrityError as exc:
        # Este endpoint não checava execução ativa nenhuma — inseria direto em
        # RUNNING. O índice único parcial (migration 20260731_01) passa a
        # aplicar aqui a mesma invariante dos demais produtores.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Já existe uma execução ativa para esta automação. "
                "Finalize-a antes de registrar telemetria."
            ),
        ) from exc

    logger.info(
        "Telemetria iniciada: %s para automacao %s", exec_id, payload.automation_name
    )
    return {"exec_id": exec_id}


@router.post("/telemetry/end/{exec_id}")
def telemetry_end(
    exec_id: str,
    payload: schemas.ExecutionTelemetryEnd,
    request: Request,
    db: Session = Depends(get_db),
    _api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """Finaliza o registro de uma execução disparada externamente."""
    db_exec = exec_repo.get_by_id(db, exec_id)
    if not db_exec:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")

    # Somente status TERMINAIS: o endpoint é o "/end" da telemetria. Validar
    # contra EXECUTION_ALLOWED_STATUSES (que inclui PENDING e RUNNING) abria um
    # caminho de reexecução fora da fila — `status: "PENDING"` gravava
    # `finished_at`/`duration_seconds` e devolvia a execução ao pool, onde o
    # worker a reivindicava e rodava a automação de novo, ignorando cooldown,
    # `max_retries`, `queue_group` e a checagem de execução ativa.
    status_upper = str(payload.status).upper()
    if status_upper not in EXECUTION_TERMINAL_STATUSES:
        permitidos = ", ".join(sorted(EXECUTION_TERMINAL_STATUSES))
        raise HTTPException(
            status_code=422,
            detail=(
                f"Status de encerramento inválido: {payload.status}. "
                f"Use um status terminal: {permitidos}."
            ),
        )

    db_exec.status = status_upper  # type: ignore[assignment]
    if payload.exit_code is not None:
        db_exec.exit_code = int(payload.exit_code)  # type: ignore[assignment]
    if payload.logs is not None:
        # `truncate_log_payload` também aqui: era o ÚNICO caminho de escrita de
        # log que ignorava MAX_DB_LOGS_CHARS (todo o worker o respeita). Como
        # `logs` é CompressedText, cada leitura descomprime a coluna inteira em
        # memória — um payload de dezenas de MB vindo de um cliente externo
        # ficava permanentemente no SQLite e inflava toda listagem que tocasse
        # aquela execução.
        db_exec.logs = truncate_log_payload(  # type: ignore[assignment]
            sanitize_log_payload(payload.logs)
        )
    if payload.artifacts is not None:
        db_exec.artifacts = payload.artifacts  # type: ignore[assignment]

    db_exec.finished_at = get_now_local()  # type: ignore[assignment]

    # Calcular duração
    if db_exec.started_at and db_exec.finished_at:
        try:
            delta = db_exec.finished_at - db_exec.started_at
            delta_seconds = round(delta.total_seconds(), 2)
            db_exec.duration_seconds = max(0.0, delta_seconds)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass

    log_audit(db, "END_TELEMETRY", "EXECUTION", exec_id, get_client_ip(request))
    db.commit()

    logger.info("Telemetria finalizada: %s com status %s", exec_id, payload.status)
    return {"message": "Telemetria registrada com sucesso.", "exec_id": exec_id}

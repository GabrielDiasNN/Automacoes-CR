"""Pipeline de decoração operacional de execuções (ações do operador, atenção) (A2, A3)."""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..constants import EXECUTION_ACTIVE_STATUSES, EXECUTION_QUEUEABLE_SOURCE_STATUSES
from ..timezone import get_now_local
from .scoring import compute_attention_score


def build_active_execution_maps(
    db: Session,
) -> tuple[dict[int, models.Execution], dict[str, models.Execution]]:
    """Mapeia execuções ativas em memória para evitar N+1 queries na decoração."""
    active_execs = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .filter(models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)))
        .order_by(desc(models.Execution.started_at))
        .all()
    )
    by_automation: dict[int, models.Execution] = {}
    by_group: dict[str, models.Execution] = {}
    for item in active_execs:
        by_automation.setdefault(int(item.automation_id), item)
        queue_group = item.queue_group or getattr(item.automation, "queue_group", None)
        if queue_group:
            by_group.setdefault(str(queue_group), item)
    return by_automation, by_group


def _determine_operational_actions(
    summary: schemas.ExecutionSummary | schemas.ExecutionResponse,
    ex: models.Execution,
    active_by_automation: dict[int, models.Execution],
    active_by_group: dict[str, models.Execution],
    queue_group: str | None,
) -> None:
    """Determina as ações do operador disponíveis para a execução e condições de reenfileiramento (A2)."""
    queueable = ex.status in EXECUTION_QUEUEABLE_SOURCE_STATUSES
    active_for_automation = active_by_automation.get(int(ex.automation_id))
    active_for_group = active_by_group.get(queue_group) if queue_group else None

    # Inicializar campos padrão
    summary.requeue_allowed = False
    summary.requeue_block_reason = None
    summary.related_execution_id = None
    summary.related_execution_status = None
    summary.operator_action_code = "VIEW_LOGS"
    summary.operator_action_label = "Revisar logs"
    summary.operator_action_hint = (
        "Revise logs e contexto operacional antes de uma nova tentativa."
    )

    if queueable:
        # `max_retries` não é um limite de reenfileiramento manual — não existe
        # retry automático no worker que o consuma, é só o histórico de quantas
        # vezes o operador já reenfileirou. Reenfileirar manualmente só é
        # bloqueado por conflito real (execução ativa na mesma automação/fila).
        if active_for_automation and active_for_automation.id != ex.id:
            summary.requeue_block_reason = f"Já existe execução ativa para esta automação ({active_for_automation.id})."
            summary.related_execution_id = str(active_for_automation.id)
            summary.related_execution_status = str(active_for_automation.status)
        elif active_for_group and active_for_group.id != ex.id:
            summary.requeue_block_reason = f"Grupo operacional '{queue_group}' já está em uso por {active_for_group.id}."
            summary.related_execution_id = str(active_for_group.id)
            summary.related_execution_status = str(active_for_group.status)
        else:
            summary.requeue_allowed = True
            summary.operator_action_code = "REQUEUE"
            summary.operator_action_label = "Reenfileirar"
            summary.operator_action_hint = (
                "Execução pode ser enviada novamente para a fila de processamento."
            )

    elif ex.status in EXECUTION_ACTIVE_STATUSES:
        summary.operator_action_code = "STOP"
        summary.operator_action_label = "Parar execução"
        summary.operator_action_hint = "Solicita a interrupção imediata do processo."

    # Linhas de sucesso saudáveis mantêm o botão de reenfileirar (reprocesso
    # manual sob demanda), mas sem rótulo/hint de alerta — desde que a checagem
    # de conflito acima não tenha bloqueado.
    if ex.status == "SUCCESS" and summary.requeue_allowed:
        summary.operator_action_label = None
        summary.operator_action_hint = None


def _set_operator_attention(
    summary: schemas.ExecutionSummary | schemas.ExecutionResponse,
    ex: models.Execution,
    score: int,
    reasons: list[str],
) -> None:
    """Calcula a gravidade da atenção e monta a resposta operacional consolidada (A2)."""
    summary.operator_score = score
    summary.operator_attention_required = score >= 20

    if score >= 80:
        summary.operator_severity = "CRITICAL"
    elif score >= 50:
        summary.operator_severity = "HIGH"
    elif score >= 20:
        summary.operator_severity = "MODERATE"
    else:
        summary.operator_severity = "NORMAL"

    if reasons:
        summary.operator_reason_summary = " | ".join(reasons)
    else:
        summary.operator_reason_summary = None

    # Sobrescrever campos para manter linhas de sucesso saudáveis compactas
    if ex.status == "SUCCESS" and score < 20:
        summary.operator_attention_required = False
        summary.operator_action_label = None
        summary.operator_reason_summary = None
        summary.operator_score = 0
        summary.operator_severity = "NORMAL"


def decorate_execution_summary(
    summary: schemas.ExecutionSummary | schemas.ExecutionResponse,
    ex: models.Execution,
    active_by_automation: dict[int, models.Execution],
    active_by_group: dict[str, models.Execution],
) -> schemas.ExecutionSummary | schemas.ExecutionResponse:
    """Decora o resumo de execução em pipeline usando scoring centralizado (A2, A3)."""
    queue_group = ex.queue_group or getattr(ex.automation, "queue_group", None)
    now = get_now_local()

    summary.related_queue_group = str(queue_group) if queue_group else None
    summary.stop_allowed = ex.status in EXECUTION_ACTIVE_STATUSES
    summary.requeue_allowed = False
    summary.requeue_block_reason = None
    summary.related_execution_id = None
    summary.related_execution_status = None
    summary.operator_attention_required = False
    summary.operator_score = 0
    summary.operator_reason_summary = None
    summary.operator_severity = "NORMAL"

    # Pipeline de execução dos decoradores
    _determine_operational_actions(
        summary,
        ex,
        active_by_automation,
        active_by_group,
        str(queue_group) if queue_group else None,
    )
    score, reasons = compute_attention_score(
        ex, now, active_by_automation, active_by_group
    )
    _set_operator_attention(summary, ex, score, reasons)

    return summary

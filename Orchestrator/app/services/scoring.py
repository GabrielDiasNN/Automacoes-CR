"""Serviço de cálculo de pontuação de atenção (Scoring System) do Orchestrator (A3)."""

# pylint: disable=relative-beyond-top-level,too-many-locals,too-many-branches,too-many-statements

from datetime import datetime

from .. import models
from ..constants import EXECUTION_ACTIVE_STATUSES


def compute_attention_score(
    ex: models.Execution,
    now: datetime,
    active_by_automation: dict[int, models.Execution],
    active_by_group: dict[str, models.Execution],
) -> tuple[int, list[str]]:
    """
    Calcula a pontuação de atenção (attention score) e gera os motivos correspondentes.
    Regras parametrizáveis baseadas em severidade e estado (A3).
    """
    score = 0
    reasons: list[str] = []

    queue_group = ex.queue_group or getattr(ex.automation, "queue_group", None)

    # 1. Regras de Estado de Execução Ativa
    stop_allowed = ex.status in EXECUTION_ACTIVE_STATUSES
    if stop_allowed:
        score += 45
        reasons.append("Execução ativa exige acompanhamento direto")
        if ex.started_at and getattr(ex, "automation", None):
            max_runtime_minutes = getattr(ex.automation, "max_runtime_minutes", 0) or 0
            if max_runtime_minutes > 0:
                elapsed_seconds = (now - ex.started_at).total_seconds()
                if elapsed_seconds > max_runtime_minutes * 60:
                    score += 35
                    reasons.append("Execução ativa acima do tempo máximo cadastrado")

    # 2. Regras de Estado Terminal com erro ou PENDING
    elif ex.status in {"ERROR", "TIMEOUT", "TERMINATED"}:
        score += 30
        reasons.append("Execução terminal com necessidade de triagem")
    elif ex.status == "PENDING":
        score += 18
        reasons.append("Execução aguardando processamento na fila")
        if ex.started_at:
            pending_age = (now - ex.started_at).total_seconds()
            if pending_age >= 900:
                score += 22
                reasons.append("Fila envelhecida para esta execução")

    # 3. Regras de Concorrência e Conflitos de Requeue
    automation_id = int(ex.automation_id)
    group_str = str(queue_group) if queue_group else None
    active_for_automation = active_by_automation.get(automation_id)
    active_for_group = active_by_group.get(group_str) if group_str else None

    max_retries = int(
        ex.max_retries
        or (ex.automation.max_retries if ex.automation else 0)
        or 0
    )
    retry_count = int(ex.retry_count or 0)

    queueable = ex.status in {
        "SUCCESS",
        "ERROR",
        "TIMEOUT",
        "TERMINATED",
        "FAILED_BY_REBOOT",
        "REQUEUED",
    }

    if queueable:
        if active_for_automation and active_for_automation.id != ex.id:
            score += 15
            reasons.append("Existe outra execução ativa para a automação")
        elif active_for_group and active_for_group.id != ex.id:
            score += 18
            reasons.append("Grupo operacional já está ocupado")
        elif retry_count >= max_retries:
            score += 12
            reasons.append("Limite de retry já foi atingido")

    # 4. Regras de Prioridade
    priority_str = str(ex.priority or "NORMAL").upper()
    if priority_str == "HIGH":
        score += 20
        reasons.append("Execução marcada como prioridade alta")
    elif priority_str == "LOW":
        score = max(score - 5, 0)

    # 5. Regras baseadas em Retries
    if retry_count > 0:
        score += min(retry_count * 8, 24)
        reasons.append(f"Execução já passou por {retry_count} retry(s)")

    # 6. Regra baseada em Motivo de Falha
    if ex.failure_reason:
        score += 8
        reasons.append("Há motivo de falha registrado")

    return score, reasons

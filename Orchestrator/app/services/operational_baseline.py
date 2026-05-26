"""Baseline operacional reutilizável entre diagnóstico, histórico e validação."""

from __future__ import annotations

from datetime import datetime

from app import schemas  # pylint: disable=import-error
from app.constants import (  # pylint: disable=import-error
    ACTION_CODE_CHECKPOINT,
    ACTION_CODE_WORKER_RECOVER,
    ACTION_CODE_WORKER_WAKEUP,
    BASELINE_STATUS_ATTENTION,
    BASELINE_STATUS_HEALTHY,
    BASELINE_STATUS_INCIDENT,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_WAL_CRITICAL_MB,
    DIAGNOSTIC_WAL_ELEVATED_MB,
    DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
)


# O contrato do baseline exige um resumo sintético de várias métricas operacionais
# ao mesmo tempo; por isso os builders recebem mais argumentos do que o limite
# genérico do lint.
# pylint: disable=too-many-arguments,too-many-locals

def _format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "n/d"
    return f"{round(float(seconds), 1)} s"


def _metric(
    code: str,
    label: str,
    status: str,
    current_value: str,
    detail: str,
    *,
    attention_threshold: str | None = None,
    incident_threshold: str | None = None,
    action_code: str | None = None,
) -> schemas.OperationalBaselineMetric:
    return schemas.OperationalBaselineMetric(
        code=code,
        label=label,
        status=status,
        current_value=current_value,
        attention_threshold=attention_threshold,
        incident_threshold=incident_threshold,
        detail=detail,
        action_code=action_code,
    )


def build_operational_baseline_summary(
    *,
    evaluated_at: datetime | None,
    worker_is_alive: bool,
    worker_last_ping_age_seconds: float | None,
    active_count: int,
    pending_age_seconds: float,
    running_age_seconds: float,
    running_over_runtime_count: int,
    orphaned_running_count: int,
    wal_size_mb: float,
) -> schemas.OperationalBaselineSummary:
    metrics: list[schemas.OperationalBaselineMetric] = []

    worker_status = BASELINE_STATUS_HEALTHY
    worker_detail = "Processador com heartbeat compatível com a operação."
    if not worker_is_alive:
        worker_status = (
            BASELINE_STATUS_INCIDENT if active_count > 0 else BASELINE_STATUS_ATTENTION
        )
        worker_detail = (
            "Processador offline com fila ativa; recuperação forte é recomendada."
            if active_count > 0
            else "Processador offline sem fila ativa; a operação está vulnerável a novo acúmulo."
        )
    elif (
        worker_last_ping_age_seconds is not None
        and worker_last_ping_age_seconds >= DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS
    ):
        worker_status = BASELINE_STATUS_ATTENTION
        worker_detail = (
            "Heartbeat envelhecido; monitore antes de o processador entrar em "
            "estado offline."
        )
    metrics.append(
        _metric(
            "worker_heartbeat",
            "Heartbeat do processador",
            worker_status,
            (
                "offline"
                if not worker_is_alive
                else _format_seconds(worker_last_ping_age_seconds)
            ),
            worker_detail,
            attention_threshold=f">= {DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS}s",
            incident_threshold="offline com fila ativa",
            action_code=(
                ACTION_CODE_WORKER_RECOVER
                if worker_status == BASELINE_STATUS_INCIDENT
                else ACTION_CODE_WORKER_WAKEUP
            ),
        )
    )

    pending_status = BASELINE_STATUS_HEALTHY
    if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS * 2:
        pending_status = BASELINE_STATUS_INCIDENT
    elif pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS:
        pending_status = BASELINE_STATUS_ATTENTION
    metrics.append(
        _metric(
            "pending_queue_age",
            "Idade da fila pendente",
            pending_status,
            _format_seconds(pending_age_seconds),
            (
                "Execuções pendentes dentro da faixa operacional."
                if pending_status == BASELINE_STATUS_HEALTHY
                else (
                    "Fila pendente envelhecida; revisar processador, "
                    "concorrência e bloqueios antes de reenfileirar."
                )
            ),
            attention_threshold=f">= {DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS}s",
            incident_threshold=f">= {DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS * 2}s",
            action_code=ACTION_CODE_WORKER_WAKEUP,
        )
    )

    running_status = BASELINE_STATUS_HEALTHY
    if running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS * 2:
        running_status = BASELINE_STATUS_INCIDENT
    elif running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS:
        running_status = BASELINE_STATUS_ATTENTION
    metrics.append(
        _metric(
            "running_queue_age",
            "Idade da execução mais antiga",
            running_status,
            _format_seconds(running_age_seconds),
            (
                "Execuções em andamento dentro da faixa operacional."
                if running_status == BASELINE_STATUS_HEALTHY
                else (
                    "Há execução antiga em andamento; validar progresso real "
                    "e considerar parada controlada."
                )
            ),
            attention_threshold=f">= {DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS}s",
            incident_threshold=f">= {DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS * 2}s",
            action_code="show_running",
        )
    )

    over_runtime_status = BASELINE_STATUS_HEALTHY
    if running_over_runtime_count >= 3:
        over_runtime_status = BASELINE_STATUS_INCIDENT
    elif running_over_runtime_count >= 1:
        over_runtime_status = BASELINE_STATUS_ATTENTION
    metrics.append(
        _metric(
            "running_over_runtime",
            "Execuções acima do tempo máximo",
            over_runtime_status,
            str(int(running_over_runtime_count or 0)),
            (
                "Nenhuma execução ativa acima do limite cadastrado."
                if over_runtime_status == BASELINE_STATUS_HEALTHY
                else (
                    "Há execução acima do tempo máximo; revisar logs e "
                    "heartbeat operacional da automação."
                )
            ),
            attention_threshold=">= 1 execução",
            incident_threshold=">= 3 execuções",
            action_code="show_running",
        )
    )

    orphaned_status = (
        BASELINE_STATUS_INCIDENT
        if int(orphaned_running_count or 0) > 0
        else BASELINE_STATUS_HEALTHY
    )
    metrics.append(
        _metric(
            "orphaned_running",
            "Responsável por execuções em andamento",
            orphaned_status,
            str(int(orphaned_running_count or 0)),
            (
                "Sem execuções órfãs detectadas."
                if orphaned_status == BASELINE_STATUS_HEALTHY
                else (
                    "Há execução em andamento sem responsável válido; tratar como "
                    "incidente operacional."
                )
            ),
            incident_threshold=">= 1 execução órfã",
            action_code=ACTION_CODE_WORKER_RECOVER,
        )
    )

    wal_status = BASELINE_STATUS_HEALTHY
    if wal_size_mb >= DIAGNOSTIC_WAL_CRITICAL_MB:
        wal_status = BASELINE_STATUS_INCIDENT
    elif wal_size_mb >= DIAGNOSTIC_WAL_ELEVATED_MB:
        wal_status = BASELINE_STATUS_ATTENTION
    metrics.append(
        _metric(
            "wal_size",
            "Pressão do WAL",
            wal_status,
            f"{round(float(wal_size_mb or 0.0), 2)} MB",
            (
                "WAL dentro da faixa operacional."
                if wal_status == BASELINE_STATUS_HEALTHY
                else (
                    "WAL pressionado; checkpoint e investigação de contenção "
                    "de escrita são recomendados."
                )
            ),
            attention_threshold=f">= {DIAGNOSTIC_WAL_ELEVATED_MB} MB",
            incident_threshold=f">= {DIAGNOSTIC_WAL_CRITICAL_MB} MB",
            action_code=ACTION_CODE_CHECKPOINT,
        )
    )

    incident_count = sum(1 for item in metrics if item.status == BASELINE_STATUS_INCIDENT)
    attention_count = sum(1 for item in metrics if item.status == BASELINE_STATUS_ATTENTION)
    status = BASELINE_STATUS_HEALTHY
    if incident_count:
        status = BASELINE_STATUS_INCIDENT
    elif attention_count:
        status = BASELINE_STATUS_ATTENTION

    recommended_action = next(
        (
            item.action_code
            for item in metrics
            if item.status == BASELINE_STATUS_INCIDENT and item.action_code
        ),
        None,
    ) or next(
        (
            item.action_code
            for item in metrics
            if item.status == BASELINE_STATUS_ATTENTION and item.action_code
        ),
        None,
    )

    return schemas.OperationalBaselineSummary(
        evaluated_at=evaluated_at,
        status=status,
        attention_count=attention_count,
        incident_count=incident_count,
        recommended_action=recommended_action,
        metrics=metrics,
    )


def build_snapshot_operational_baseline(
    *,
    evaluated_at: datetime | None,
    pending_count: int,
    running_count: int,
    pending_age_seconds: float,
    running_age_seconds: float,
    running_over_runtime_count: int,
    orphaned_running_count: int,
    wal_size_mb: float,
    worker_last_ping_age_seconds: float | None,
) -> schemas.OperationalBaselineSummary:
    worker_is_alive = (
        worker_last_ping_age_seconds is not None
        and worker_last_ping_age_seconds < DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS
    )
    return build_operational_baseline_summary(
        evaluated_at=evaluated_at,
        worker_is_alive=worker_is_alive,
        worker_last_ping_age_seconds=worker_last_ping_age_seconds,
        active_count=int(pending_count or 0) + int(running_count or 0),
        pending_age_seconds=float(pending_age_seconds or 0.0),
        running_age_seconds=float(running_age_seconds or 0.0),
        running_over_runtime_count=int(running_over_runtime_count or 0),
        orphaned_running_count=int(orphaned_running_count or 0),
        wal_size_mb=float(wal_size_mb or 0.0),
    )

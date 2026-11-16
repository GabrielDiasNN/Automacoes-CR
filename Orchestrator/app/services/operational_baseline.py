"""Baseline operacional reutilizável entre diagnóstico, histórico e validação."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app import schemas
from app.constants import (
    ACTION_CODE_CHECKPOINT,
    ACTION_CODE_WORKER_RECOVER,
    ACTION_CODE_WORKER_WAKEUP,
    BASELINE_STATUS_ATTENTION,
    BASELINE_STATUS_HEALTHY,
    BASELINE_STATUS_INCIDENT,
    DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_WAL_CRITICAL_MB,
    DIAGNOSTIC_WAL_ELEVATED_MB,
    DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
)


@dataclass(frozen=True)
class SinaisWorker:
    """Sinais do processador usados pelo baseline."""

    is_alive: bool
    last_ping_age_seconds: float | None
    active_count: int


@dataclass(frozen=True)
class SinaisFila:
    """Sinais da fila e das execuções usados pelo baseline."""

    pending_age_seconds: float
    running_age_seconds: float
    running_over_runtime_count: int
    orphaned_running_count: int


def _format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "n/d"
    return f"{round(float(seconds), 1)} s"


def _metrica_heartbeat(
    worker: SinaisWorker,
) -> schemas.OperationalBaselineMetric:
    worker_status = BASELINE_STATUS_HEALTHY
    worker_detail = "Processador com heartbeat compatível com a operação."
    if not worker.is_alive:
        worker_status = (
            BASELINE_STATUS_INCIDENT
            if worker.active_count > 0
            else BASELINE_STATUS_ATTENTION
        )
        worker_detail = (
            "Processador offline com fila ativa; recuperação forte é recomendada."
            if worker.active_count > 0
            else "Processador offline sem fila ativa; a operação está vulnerável a novo acúmulo."
        )
    elif (
        worker.last_ping_age_seconds is not None
        and worker.last_ping_age_seconds >= DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS
    ):
        worker_status = BASELINE_STATUS_ATTENTION
        worker_detail = (
            "Heartbeat envelhecido; monitore antes de o processador entrar em "
            "estado offline."
        )
    return schemas.OperationalBaselineMetric(
        code="worker_heartbeat",
        label="Heartbeat do processador",
        status=worker_status,
        current_value=(
            "offline"
            if not worker.is_alive
            else _format_seconds(worker.last_ping_age_seconds)
        ),
        attention_threshold=f">= {DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS}s",
        incident_threshold="offline com fila ativa",
        detail=worker_detail,
        action_code=(
            ACTION_CODE_WORKER_RECOVER
            if worker_status == BASELINE_STATUS_INCIDENT
            else ACTION_CODE_WORKER_WAKEUP
        ),
    )


def _metrica_pending(fila: SinaisFila) -> schemas.OperationalBaselineMetric:
    pending_status = BASELINE_STATUS_HEALTHY
    if fila.pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS:
        pending_status = BASELINE_STATUS_INCIDENT
    elif fila.pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS:
        pending_status = BASELINE_STATUS_ATTENTION
    return schemas.OperationalBaselineMetric(
        code="pending_queue_age",
        label="Idade da fila pendente",
        status=pending_status,
        current_value=_format_seconds(fila.pending_age_seconds),
        detail=(
            "Execuções pendentes dentro da faixa operacional."
            if pending_status == BASELINE_STATUS_HEALTHY
            else (
                "Fila pendente envelhecida; revisar processador, "
                "concorrência e bloqueios antes de reenfileirar."
            )
        ),
        attention_threshold=f">= {DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS}s",
        incident_threshold=f">= {DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS}s",
        action_code=ACTION_CODE_WORKER_WAKEUP,
    )


def _metrica_running(fila: SinaisFila) -> schemas.OperationalBaselineMetric:
    running_status = BASELINE_STATUS_HEALTHY
    if fila.running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS * 2:
        running_status = BASELINE_STATUS_INCIDENT
    elif fila.running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS:
        running_status = BASELINE_STATUS_ATTENTION
    return schemas.OperationalBaselineMetric(
        code="running_queue_age",
        label="Idade da execução mais antiga",
        status=running_status,
        current_value=_format_seconds(fila.running_age_seconds),
        detail=(
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


def _metrica_over_runtime(fila: SinaisFila) -> schemas.OperationalBaselineMetric:
    over_runtime_status = BASELINE_STATUS_HEALTHY
    if fila.running_over_runtime_count >= 3:
        over_runtime_status = BASELINE_STATUS_INCIDENT
    elif fila.running_over_runtime_count >= 1:
        over_runtime_status = BASELINE_STATUS_ATTENTION
    return schemas.OperationalBaselineMetric(
        code="running_over_runtime",
        label="Execuções acima do tempo máximo",
        status=over_runtime_status,
        current_value=str(int(fila.running_over_runtime_count or 0)),
        detail=(
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


def _metrica_orphaned(fila: SinaisFila) -> schemas.OperationalBaselineMetric:
    orphaned_status = (
        BASELINE_STATUS_INCIDENT
        if int(fila.orphaned_running_count or 0) > 0
        else BASELINE_STATUS_HEALTHY
    )
    return schemas.OperationalBaselineMetric(
        code="orphaned_running",
        label="Responsável por execuções em andamento",
        status=orphaned_status,
        current_value=str(int(fila.orphaned_running_count or 0)),
        detail=(
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


def _metrica_wal(wal_size_mb: float) -> schemas.OperationalBaselineMetric:
    wal_status = BASELINE_STATUS_HEALTHY
    if wal_size_mb >= DIAGNOSTIC_WAL_CRITICAL_MB:
        wal_status = BASELINE_STATUS_INCIDENT
    elif wal_size_mb >= DIAGNOSTIC_WAL_ELEVATED_MB:
        wal_status = BASELINE_STATUS_ATTENTION
    return schemas.OperationalBaselineMetric(
        code="wal_size",
        label="Pressão do WAL",
        status=wal_status,
        current_value=f"{round(float(wal_size_mb or 0.0), 2)} MB",
        detail=(
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


def _recomendar_acao(
    metrics: list[schemas.OperationalBaselineMetric],
) -> str | None:
    return next(
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


def build_operational_baseline_summary(
    *,
    evaluated_at: datetime | None,
    worker: SinaisWorker,
    fila: SinaisFila,
    wal_size_mb: float,
) -> schemas.OperationalBaselineSummary:
    metrics: list[schemas.OperationalBaselineMetric] = [
        _metrica_heartbeat(worker),
        _metrica_pending(fila),
        _metrica_running(fila),
        _metrica_over_runtime(fila),
        _metrica_orphaned(fila),
        _metrica_wal(wal_size_mb),
    ]

    incident_count = sum(
        1 for item in metrics if item.status == BASELINE_STATUS_INCIDENT
    )
    attention_count = sum(
        1 for item in metrics if item.status == BASELINE_STATUS_ATTENTION
    )
    status = BASELINE_STATUS_HEALTHY
    if incident_count:
        status = BASELINE_STATUS_INCIDENT
    elif attention_count:
        status = BASELINE_STATUS_ATTENTION

    return schemas.OperationalBaselineSummary(
        evaluated_at=evaluated_at,
        status=status,
        attention_count=attention_count,
        incident_count=incident_count,
        recommended_action=_recomendar_acao(metrics),
        metrics=metrics,
    )


# Assinatura consumida por `services/system_history.py` (fora desta partição):
# recebe nove argumentos nomeados, espelho do contrato do snapshot persistido.
def build_snapshot_operational_baseline(  # pylint: disable=too-many-arguments
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
        worker=SinaisWorker(
            is_alive=worker_is_alive,
            last_ping_age_seconds=worker_last_ping_age_seconds,
            active_count=int(pending_count or 0) + int(running_count or 0),
        ),
        fila=SinaisFila(
            pending_age_seconds=float(pending_age_seconds or 0.0),
            running_age_seconds=float(running_age_seconds or 0.0),
            running_over_runtime_count=int(running_over_runtime_count or 0),
            orphaned_running_count=int(orphaned_running_count or 0),
        ),
        wal_size_mb=float(wal_size_mb or 0.0),
    )

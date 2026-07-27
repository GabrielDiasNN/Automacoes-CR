"""Módulo de métricas e consultas SQL centralizadas para o Orchestrator (C4)."""

# pylint: disable=relative-beyond-top-level,not-callable

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import EXECUTION_ACTIVE_STATUSES, EXECUTION_FAILED_STATUSES
from ..timezone import get_now_local

# Ordenado para gerar SQL determinístico no IN (...).
_FAILED_STATUS_LIST = sorted(EXECUTION_FAILED_STATUSES)


def get_success_errors_count_24h(db: Session) -> tuple[int, int]:
    """Retorna a contagem de sucessos e erros nas últimas 24 horas (query única)."""
    window_start = get_now_local() - timedelta(hours=24)
    row = (
        db.query(
            func.sum(
                case((models.Execution.status.in_(["SUCCESS", "PARTIAL"]), 1), else_=0)
            ).label("success"),
            func.sum(
                case(
                    (
                        models.Execution.status.in_(_FAILED_STATUS_LIST),
                        1,
                    ),
                    else_=0,
                )
            ).label("errors"),
        )
        .filter(models.Execution.started_at >= window_start)
        .one()
    )
    return (int(row.success or 0), int(row.errors or 0))


def get_global_execution_counts(db: Session) -> tuple[int, int, int, int]:
    """Retorna (total, success, errors, pending) de execuções em uma única query."""
    row = db.query(
        func.count(models.Execution.id).label("total"),
        func.sum(
            case((models.Execution.status.in_(["SUCCESS", "PARTIAL"]), 1), else_=0)
        ).label("success"),
        func.sum(
            case((models.Execution.status.in_(_FAILED_STATUS_LIST), 1), else_=0)
        ).label("errors"),
        func.sum(case((models.Execution.status == "PENDING", 1), else_=0)).label(
            "pending"
        ),
    ).one()
    return (
        int(row.total or 0),
        int(row.success or 0),
        int(row.errors or 0),
        int(row.pending or 0),
    )


def build_global_metrics_response(db: Session) -> schemas.MetricsResponse:
    """Monta o payload completo de GET /api/system/metrics.

    Extraído do router (achado #11): a agregação pertence a esta camada, junto
    das demais queries de métrica, não ao handler HTTP. Mantém o padrão sem N+1
    (uma query agregada por automação + uma para a última execução).
    """
    total_execs, success_count, error_count, pending_count = (
        get_global_execution_counts(db)
    )

    # Duração média global (apenas execuções SUCCESS com duração registrada)
    avg_dur = (
        db.query(func.avg(models.Execution.duration_seconds))
        .filter(
            models.Execution.status == "SUCCESS",
            models.Execution.duration_seconds.isnot(None),
        )
        .scalar()
        or 0
    )

    success_rate = (
        round((success_count / total_execs * 100), 2) if total_execs > 0 else 0
    )

    # Agregação de métricas por automação em uma única query
    stats_map = {
        row.automation_id: row
        for row in db.query(
            models.Execution.automation_id,
            func.count(
                case((models.Execution.status.in_(["SUCCESS", "PARTIAL"]), 1))
            ).label("total_success"),
            func.count(
                case((models.Execution.status.in_(_FAILED_STATUS_LIST), 1))
            ).label("total_errors"),
            func.avg(
                case(
                    (
                        models.Execution.status == "SUCCESS",
                        models.Execution.duration_seconds,
                    )
                )
            ).label("avg_duration"),
        )
        .group_by(models.Execution.automation_id)
        .all()
    }

    # Subquery para a última execução de cada automação
    subq = (
        db.query(
            models.Execution.automation_id,
            func.max(models.Execution.started_at).label("max_started_at"),
        )
        .group_by(models.Execution.automation_id)
        .subquery()
    )

    last_execs_map = {
        row.automation_id: row
        for row in db.query(
            models.Execution.automation_id,
            models.Execution.status,
            models.Execution.started_at,
        )
        .join(
            subq,
            (models.Execution.automation_id == subq.c.automation_id)
            & (models.Execution.started_at == subq.c.max_started_at),
        )
        .all()
    }

    automation_stats = []
    for auto in db.query(models.Automation).all():
        stat = stats_map.get(auto.id)
        last_ex = last_execs_map.get(auto.id)
        automation_stats.append(
            schemas.AutomationMetric(
                name=str(auto.name),
                total_success=stat.total_success if stat else 0,
                total_errors=stat.total_errors if stat else 0,
                avg_duration_sec=(
                    round(stat.avg_duration, 2) if stat and stat.avg_duration else 0
                ),
                last_status=last_ex.status if last_ex else None,
                last_run=last_ex.started_at if last_ex else None,
                test_mode=bool(auto.test_mode),
            )
        )

    return schemas.MetricsResponse(
        summary=schemas.MetricsSummary(
            total_executions=total_execs,
            success_count=success_count,
            error_count=error_count,
            success_rate=success_rate,
            pending_count=pending_count,
            avg_duration_sec=round(avg_dur, 2),
        ),
        automations=automation_stats,
    )


def get_status_breakdown(db: Session) -> dict[str, int]:
    """Retorna o breakdown de execuções agrupado por status."""
    status_rows = (
        db.query(models.Execution.status, func.count(models.Execution.id))
        .group_by(models.Execution.status)
        .all()
    )
    return {str(status): int(count) for status, count in status_rows}


def get_active_by_priority(db: Session) -> dict[str, int]:
    """Retorna contagem de execuções ativas agrupadas por prioridade."""
    priority_rows = (
        db.query(models.Execution.priority, func.count(models.Execution.id))
        .filter(models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES))
        .group_by(models.Execution.priority)
        .all()
    )
    return {str(priority or "NORMAL"): int(count) for priority, count in priority_rows}


def get_active_by_group(db: Session) -> dict[str, int]:
    """Retorna contagem de execuções ativas agrupadas por queue_group."""
    group_rows = (
        db.query(models.Execution.queue_group, func.count(models.Execution.id))
        .filter(models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES))
        .group_by(models.Execution.queue_group)
        .all()
    )
    return {str(group or "default"): int(count) for group, count in group_rows}


def get_failure_hotspots_24h(db: Session, limit: int = 5) -> list[dict[str, Any]]:
    """Identifica automações com falhas recorrentes nas últimas 24h."""
    window_start = get_now_local() - timedelta(hours=24)
    rows = (
        db.query(
            models.Automation.id.label("automation_id"),
            models.Automation.name.label("automation_name"),
            models.Automation.notification_channels.label("notification_channels"),
            func.count(models.Execution.id).label("failures"),
            func.max(models.Execution.started_at).label("last_failure_at"),
        )
        .join(models.Execution, models.Execution.automation_id == models.Automation.id)
        .filter(
            models.Execution.status.in_(_FAILED_STATUS_LIST),
            models.Execution.started_at >= window_start,
        )
        .group_by(
            models.Automation.id,
            models.Automation.name,
            models.Automation.notification_channels,
        )
        .order_by(desc(func.count(models.Execution.id)))
        .limit(limit)
        .all()
    )
    return [
        {
            "automation_id": row.automation_id,
            "automation_name": row.automation_name,
            "failures_24h": int(row.failures),
            "last_failure_at": schemas.format_dt_br(row.last_failure_at),
            "notification_channels": row.notification_channels,
        }
        for row in rows
    ]


def get_sla_metrics_by_automation_24h(db: Session) -> dict[int, dict[str, Any]]:
    """
    Busca métricas de duração média de execuções SUCCESS nas últimas 24h por automação.
    Evita queries N+1 (C3) ao buscar tudo em um único comando agrupado (group_by).
    """
    window_start = get_now_local() - timedelta(hours=24)

    # Query única para tirar a média de duração das automações
    avg_rows = (
        db.query(
            models.Execution.automation_id,
            func.avg(models.Execution.duration_seconds).label("avg_duration_seconds"),
        )
        .filter(
            models.Execution.status == "SUCCESS",
            models.Execution.started_at >= window_start,
            models.Execution.duration_seconds.isnot(None),
        )
        .group_by(models.Execution.automation_id)
        .all()
    )

    metrics: dict[int, dict[str, Any]] = {}
    for row in avg_rows:
        if row.automation_id is None:
            continue
        avg_min = float(row.avg_duration_seconds) / 60.0
        metrics[int(row.automation_id)] = {
            "avg_duration_minutes": round(avg_min, 2),
            "avg_duration_seconds": round(float(row.avg_duration_seconds), 2),
        }
    return metrics


def _success_rate_pct(success: int, errors: int) -> float | None:
    """Calcula a taxa de sucesso percentual; None quando não há amostra terminal."""
    total = success + errors
    if total == 0:
        return None
    return round(success / total * 100.0, 2)


def _average(values: list[float]) -> float | None:
    """Média simples; None para lista vazia."""
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Percentil por posição sobre uma lista já ordenada; None para lista vazia."""
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return round(sorted_values[idx], 2)


def _aggregate_daily_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Agrupa linhas (dia, status, duração) em métricas diárias ordenadas."""
    grouped: dict[str, dict[str, Any]] = {}
    for day, status, duration in rows:
        key = str(day)
        bucket = grouped.setdefault(
            key, {"total": 0, "success": 0, "errors": 0, "durations": []}
        )
        bucket["total"] += 1
        if status in ("SUCCESS", "PARTIAL"):
            bucket["success"] += 1
        elif status in EXECUTION_FAILED_STATUSES:
            bucket["errors"] += 1
        if duration is not None:
            bucket["durations"].append(float(duration))

    result: list[dict[str, Any]] = []
    for day in sorted(grouped):
        bucket = grouped[day]
        durations = sorted(bucket["durations"])
        result.append(
            {
                "date": day,
                "total": bucket["total"],
                "success": bucket["success"],
                "errors": bucket["errors"],
                "success_rate_pct": _success_rate_pct(
                    bucket["success"], bucket["errors"]
                ),
                "avg_duration_seconds": _average(durations),
                "p95_duration_seconds": _percentile(durations, 0.95),
            }
        )
    return result


def get_daily_execution_metrics(db: Session, days: int = 14) -> list[dict[str, Any]]:
    """Agrega execuções por dia: total, sucesso, erros, duração média e p95.

    Usa o índice ix_exec_status_started (status, started_at). Cálculo de p95
    é feito em Python (SQLite não tem percentil nativo); volume é limitado
    pela retenção de purge_old_executions (90 dias)."""
    window_start = get_now_local() - timedelta(days=days)
    rows = (
        db.query(
            func.date(models.Execution.started_at).label("day"),
            models.Execution.status,
            models.Execution.duration_seconds,
        )
        .filter(models.Execution.started_at >= window_start)
        .order_by(func.date(models.Execution.started_at))
        .all()
    )
    return _aggregate_daily_rows(rows)


def _normalize_automation_ids(
    automation_ids: Iterable[int] | None = None,
) -> list[int]:
    """Remove nulos, duplicidades e normaliza IDs antes de aplicar filtros SQL."""
    if automation_ids is None:
        return []
    return sorted({int(item) for item in automation_ids if item is not None})


def get_automation_metrics_24h(
    db: Session, automation_ids: Iterable[int] | None = None
) -> dict[int, dict[str, Any]]:
    """Retorna métricas operacionais das últimas 24h agrupadas por automação."""
    window_start = get_now_local() - timedelta(hours=24)
    ids = _normalize_automation_ids(automation_ids)

    query = (
        db.query(
            models.Execution.automation_id.label("automation_id"),
            func.sum(
                case((models.Execution.status.in_(["SUCCESS", "PARTIAL"]), 1), else_=0)
            ).label("success_24h"),
            func.sum(
                case(
                    (
                        models.Execution.status.in_(_FAILED_STATUS_LIST),
                        1,
                    ),
                    else_=0,
                )
            ).label("failures_24h"),
            func.sum(case((models.Execution.status == "TIMEOUT", 1), else_=0)).label(
                "timeouts_24h"
            ),
            func.avg(models.Execution.duration_seconds).label(
                "avg_duration_24h_seconds"
            ),
        )
        .filter(models.Execution.started_at >= window_start)
        .group_by(models.Execution.automation_id)
    )

    if ids:
        query = query.filter(models.Execution.automation_id.in_(ids))

    rows = query.all()
    return {
        int(row.automation_id): {
            "success_24h": int(row.success_24h or 0),
            "failures_24h": int(row.failures_24h or 0),
            "timeouts_24h": int(row.timeouts_24h or 0),
            "avg_duration_24h_seconds": (
                round(float(row.avg_duration_24h_seconds), 2)
                if row.avg_duration_24h_seconds is not None
                else None
            ),
        }
        for row in rows
        if row.automation_id is not None
    }


def get_latest_execution_snapshot_by_automation(
    db: Session, automation_ids: Iterable[int] | None = None
) -> dict[int, dict[str, Any]]:
    """Retorna o snapshot da execução mais recente por automação sem N+1."""
    ids = _normalize_automation_ids(automation_ids)
    query = db.query(
        models.Execution.automation_id.label("automation_id"),
        models.Execution.id.label("execution_id"),
        models.Execution.status.label("status"),
        models.Execution.started_at.label("started_at"),
        models.Execution.finished_at.label("finished_at"),
        models.Execution.duration_seconds.label("duration_seconds"),
        models.Execution.failure_reason.label("failure_reason"),
        models.Execution.recovery_action.label("recovery_action"),
        models.Execution.requested_by.label("requested_by"),
        func.row_number()
        .over(
            partition_by=models.Execution.automation_id,
            order_by=(
                models.Execution.started_at.desc(),
                models.Execution.id.desc(),
            ),
        )
        .label("rn"),
    )

    if ids:
        query = query.filter(models.Execution.automation_id.in_(ids))

    subq = query.subquery()
    rows = (
        db.query(
            subq.c.automation_id,
            subq.c.execution_id,
            subq.c.status,
            subq.c.started_at,
            subq.c.finished_at,
            subq.c.duration_seconds,
            subq.c.failure_reason,
            subq.c.recovery_action,
            subq.c.requested_by,
        )
        .filter(subq.c.rn == 1)
        .all()
    )

    return {
        int(row.automation_id): {
            "id": str(row.execution_id),
            "status": str(row.status) if row.status else None,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "duration_seconds": (
                round(float(row.duration_seconds), 2)
                if row.duration_seconds is not None
                else None
            ),
            "failure_reason": row.failure_reason,
            "recovery_action": row.recovery_action,
            "requested_by": row.requested_by,
        }
        for row in rows
        if row.automation_id is not None
    }


def get_last_execution_status_by_automation(db: Session) -> dict[int, str]:
    """
    Retorna o status da última execução de cada automação.
    Evita queries N+1 (A1) ao buscar tudo de uma vez.
    """
    return {
        automation_id: str(snapshot["status"])
        for automation_id, snapshot in get_latest_execution_snapshot_by_automation(
            db
        ).items()
        if snapshot.get("status") is not None
    }

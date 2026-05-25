# pylint: disable=all
"""Histórico operacional leve para tendência, triagem e SLOs."""

import json
from datetime import timedelta
from typing import Any, cast

from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS
from ..timezone import get_now_local


def _loads_json_array(raw_value: str | None) -> list[Any]:
    if not raw_value:
        return []
    try:
        value = json.loads(raw_value)
    except Exception:
        return []
    return value if isinstance(value, list) else []


def _loads_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def capture_system_health_snapshot(
    db: Session,
    diagnostics_payload: dict[str, Any],
    retention_days: int = 30,
) -> models.SystemHealthSnapshot:
    queue = diagnostics_payload.get("queue", {})
    heartbeat = diagnostics_payload.get("heartbeat", {})
    failure_hotspots = diagnostics_payload.get("failure_hotspots", [])
    active_by_group = queue.get("active_by_group", {})
    snapshot = models.SystemHealthSnapshot(
        timestamp=get_now_local(),
        overall_status=str(diagnostics_payload.get("overall_status", "unknown")),
        pending_count=int(queue.get("by_status", {}).get("PENDING", 0)),
        running_count=int(queue.get("by_status", {}).get("RUNNING", 0)),
        oldest_pending_age_seconds=float(
            queue.get("oldest_pending", {}).get("age_seconds", 0.0) or 0.0
        ),
        oldest_running_age_seconds=float(
            queue.get("oldest_running", {}).get("age_seconds", 0.0) or 0.0
        ),
        wal_size_mb=float(diagnostics_payload.get("database", {}).get("wal_size_mb", 0.0) or 0.0),
        worker_last_ping_age_seconds=heartbeat.get("last_ping_age_seconds"),
        running_over_runtime_count=len(queue.get("running_over_runtime", [])),
        orphaned_running_count=len(queue.get("orphaned_running", [])),
        failure_hotspots=json.dumps(
            [item.get("automation_name") for item in failure_hotspots if item.get("automation_name")],
            ensure_ascii=False,
        ),
        active_queue_groups=json.dumps(
            sorted([str(key) for key, value in active_by_group.items() if int(value or 0) > 0]),
            ensure_ascii=False,
        ),
        slo_breaches=json.dumps(
            diagnostics_payload.get("slo", {}).get("breaches", {}),
            ensure_ascii=False,
        ),
    )
    db.add(snapshot)

    cutoff = get_now_local() - timedelta(days=retention_days)
    (
        db.query(models.SystemHealthSnapshot)
        .filter(models.SystemHealthSnapshot.timestamp < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def build_trend_summary(
    db: Session,
    hours: int = 24,
) -> dict[str, Any]:
    since = get_now_local() - timedelta(hours=hours)
    rows = (
        db.query(models.SystemHealthSnapshot)
        .filter(models.SystemHealthSnapshot.timestamp >= since)
        .order_by(models.SystemHealthSnapshot.timestamp.asc())
        .all()
    )

    status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0}
    worker_offline_events = 0
    stale_pending_events = 0
    orphaned_running_events = 0

    for row in rows:
        status = str(row.overall_status or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if row.worker_last_ping_age_seconds and row.worker_last_ping_age_seconds >= 120:
            worker_offline_events += 1
        if row.oldest_pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS:
            stale_pending_events += 1
        if int(row.orphaned_running_count or 0) > 0:
            orphaned_running_events += 1

    latest = rows[-1] if rows else None
    return schemas.DiagnosticsTrendSummary(
        window_hours=hours,
        points=len(rows),
        latest_status=(str(latest.overall_status) if latest else None),
        status_counts=status_counts,
        max_pending_age_seconds=max(
            (float(row.oldest_pending_age_seconds or 0.0) for row in rows),
            default=0.0,
        ),
        max_running_age_seconds=max(
            (float(row.oldest_running_age_seconds or 0.0) for row in rows),
            default=0.0,
        ),
        max_wal_size_mb=max(
            (float(row.wal_size_mb or 0.0) for row in rows),
            default=0.0,
        ),
        worker_offline_events=worker_offline_events,
        stale_pending_events=stale_pending_events,
        orphaned_running_events=orphaned_running_events,
        last_snapshot_at=(latest.timestamp if latest else None),
    ).model_dump()


def build_system_history_response(
    db: Session,
    hours: int = 24,
) -> schemas.SystemHistoryResponse:
    hours = max(1, min(int(hours), 24 * 14))
    since = get_now_local() - timedelta(hours=hours)
    rows = (
        db.query(models.SystemHealthSnapshot)
        .filter(models.SystemHealthSnapshot.timestamp >= since)
        .order_by(models.SystemHealthSnapshot.timestamp.asc())
        .all()
    )
    items = [
        schemas.SystemHistoryPoint(
            timestamp=row.timestamp,
            overall_status=str(row.overall_status),
            pending_count=int(row.pending_count or 0),
            running_count=int(row.running_count or 0),
            oldest_pending_age_seconds=float(row.oldest_pending_age_seconds or 0.0),
            oldest_running_age_seconds=float(row.oldest_running_age_seconds or 0.0),
            wal_size_mb=float(row.wal_size_mb or 0.0),
            worker_last_ping_age_seconds=cast(
                float | None, row.worker_last_ping_age_seconds
            ),
            running_over_runtime_count=int(row.running_over_runtime_count or 0),
            orphaned_running_count=int(row.orphaned_running_count or 0),
            active_queue_groups=[
                str(item)
                for item in _loads_json_array(
                    cast(str | None, row.active_queue_groups)
                )
            ],
            failure_hotspots=[
                str(item)
                for item in _loads_json_array(
                    cast(str | None, row.failure_hotspots)
                )
            ],
            slo_breaches=_loads_json_object(cast(str | None, row.slo_breaches)),
        )
        for row in rows
    ]
    return schemas.SystemHistoryResponse(
        generated_at=schemas.format_dt_br(get_now_local()),
        hours=hours,
        points=len(items),
        trend_summary=schemas.DiagnosticsTrendSummary.model_validate(
            build_trend_summary(db, hours)
        ),
        items=items,
    )

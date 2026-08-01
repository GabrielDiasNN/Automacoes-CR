"""Máquina de estado agregada da saúde dos snapshots do Beneficiamento."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any


class HealthStatus(StrEnum):
    """Estados agregados expostos pelo health do Beneficiamento."""

    HEALTHY = "healthy"
    ATTENTION = "attention"
    MISSING = "missing"
    NO_DATA = "no_data"


def compute_health_status(
    periods: dict[str, dict[str, Any]],
    primary_issue_resolver: Callable[
        [dict[str, dict[str, Any]]], dict[str, Any] | None
    ],
) -> tuple[HealthStatus, str, str | None]:
    """Calcula status, causa e ação com precedência explícita."""
    statuses = {item.get("status") for item in periods.values()}
    if statuses == {"missing"}:
        return HealthStatus.MISSING, "snapshot_missing", None
    if "attention" in statuses or "missing" in statuses:
        primary_issue = primary_issue_resolver(periods)
        reason_code = (
            str(primary_issue.get("code"))
            if primary_issue and primary_issue.get("code")
            else "snapshot_attention"
        )
        action = (
            str(primary_issue.get("action_hint"))
            if primary_issue and primary_issue.get("action_hint")
            else None
        )
        return HealthStatus.ATTENTION, reason_code, action
    if statuses == {"no_data"}:
        return HealthStatus.NO_DATA, "snapshot_no_data", None
    return HealthStatus.HEALTHY, "healthy", None

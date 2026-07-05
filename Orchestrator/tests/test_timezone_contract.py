"""Regressoes de fuso horario e formato de datas do Orchestrator."""

import re
from datetime import datetime, timezone
from typing import Any

from conftest import AUTH_HEADERS

from app import models
from app import timezone as tz_module
from app.schemas import format_dt_br, parse_dt_br
from app.schemas.common import preview_next_runs
from app.timezone import get_now_local


def test_parse_and_format_dt_br_handles_iso_and_brazil_strings() -> None:
    utc_dt = datetime(2026, 5, 21, 14, 0, 0, tzinfo=timezone.utc)
    parsed_utc = parse_dt_br(utc_dt)
    assert parsed_utc is not None
    assert parsed_utc.tzinfo is None
    assert format_dt_br(utc_dt) == "21/05/2026 11:00:00"

    parsed_iso_naive = parse_dt_br("2026-05-21T11:05:42")
    assert parsed_iso_naive is not None
    assert parsed_iso_naive.year == 2026
    assert parsed_iso_naive.hour == 11
    assert format_dt_br("2026-05-21T11:05:42") == "21/05/2026 11:05:42"

    parsed_br = parse_dt_br("21/05/2026 11:05:42")
    assert parsed_br is not None
    assert parsed_br.year == 2026
    assert parsed_br.month == 5
    assert parsed_br.day == 21
    assert format_dt_br("21/05/2026 11:05:42") == "21/05/2026 11:05:42"


def test_preview_next_runs_keeps_once_schedule_in_brazil_time(monkeypatch: Any) -> None:
    fixed_now = datetime(2026, 5, 21, 10, 0, 0)
    monkeypatch.setattr(tz_module, "get_now_local", lambda: fixed_now)

    preview = preview_next_runs(
        {
            "schedule_type": "once",
            "run_at": "2026-05-21T11:30:00",
            "timezone": "America/Sao_Paulo",
        },
        count=1,
    )

    assert preview == ["21/05/2026 11:30:00"]


def test_system_endpoints_return_brazilian_date_contract(client: Any) -> None:
    overview = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert overview.status_code == 200
    overview_data = overview.json()
    assert re.match(
        r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", overview_data["generated_at"]
    )
    assert re.match(
        r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", overview_data["kpis"]["next_window"]
    )
    for item in overview_data["recent"]:
        assert re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", item["started_at"])

    uptime = client.get("/api/system/uptime", headers=AUTH_HEADERS)
    assert uptime.status_code == 200
    uptime_data = uptime.json()
    assert re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", uptime_data["started_at"])

    version = client.get("/api/system/version", headers=AUTH_HEADERS)
    assert version.status_code == 200
    version_data = version.json()
    assert re.match(
        r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", version_data["started_at"]
    )


def test_system_scheduler_jobs_and_automation_overview_are_br_formatted(client: Any, db_session: Any) -> None:
    auto = models.Automation(name="Timezone Auto", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_TZ_001",
            automation_id=auto.id,
            status="SUCCESS",
            requested_by="TEST",
            started_at=get_now_local(),
            finished_at=get_now_local(),
        )
    )
    db_session.commit()

    overview = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert overview.status_code == 200
    data = overview.json()

    target = next(
        item for item in data["automations"] if item["name"] == "Timezone Auto"
    )
    assert target["next_run"] is None or re.match(
        r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$", target["next_run"]
    )

    jobs = client.get("/api/system/scheduler/jobs", headers=AUTH_HEADERS)
    assert jobs.status_code == 200
    for job in jobs.json():
        if job["next_run_time"]:
            assert re.match(
                r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$",
                job["next_run_time"],
            )

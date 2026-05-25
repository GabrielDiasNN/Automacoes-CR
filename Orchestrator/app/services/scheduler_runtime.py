# pylint: disable=all
# mypy: ignore-errors
"""Serviços compartilhados de agendamento e jobs do Orchestrator."""

import logging
import os
import subprocess
from datetime import datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import ACTION_CODE_SCHEDULER_RELOAD, EXECUTION_ACTIVE_STATUSES
from ..database import SessionLocal, purge_old_executions, run_wal_checkpoint
from ..runtime import scheduler
from ..schemas.schedule_rules import first_interval_candidate, ui_day_to_python_weekday
from ..timezone import get_now_local
from .execution_runtime import build_queued_execution, get_group_active_execution

logger = logging.getLogger("orchestrator")


def _get_reserved_cleanup_script_path() -> str:
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../../../Tools/AplicarPoliticaRetencao.ps1",
        )
    )


def _is_reserved_cleanup_automation(script_path: str | None) -> bool:
    if not script_path:
        return False

    resolved = script_path
    if script_path.startswith("./") or script_path.startswith(".\\"):
        resolved = os.path.join(
            os.path.dirname(__file__),
            "../../../",
            script_path[2:],
        )
    elif not os.path.isabs(script_path):
        resolved = os.path.join(os.path.dirname(__file__), "../../../", script_path)

    return os.path.normcase(os.path.abspath(resolved)) == os.path.normcase(
        _get_reserved_cleanup_script_path()
    )


def extract_automation_id_from_job(job_id: str) -> int | None:
    if not job_id.startswith("job_"):
        return None
    parts = job_id.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None


def scheduled_task_wrapper(automation_id: int) -> None:
    db = SessionLocal()
    try:
        db_auto = (
            db.query(models.Automation)
            .filter(models.Automation.id == automation_id)
            .first()
        )
        if not db_auto or not db_auto.enabled:
            return
        if _is_reserved_cleanup_automation(db_auto.script_path):
            logger.warning(
                "Agendamento ignorado para rotina reservada do sistema: %s.",
                db_auto.name,
            )
            return

        # Validação de janela operacional restrita para cadência de intervalo
        if db_auto.schedule:
            try:
                sched_data = schemas.parse_schedule(db_auto.schedule)
                if sched_data and sched_data.get("schedule_type") == "interval":
                    start_t = sched_data.get("start_time")
                    end_t = sched_data.get("end_time")
                    days = sched_data.get("days_of_week")
                    
                    if start_t or end_t or days:
                        now = get_now_local()
                        
                        if days is not None:
                            py_days = {ui_day_to_python_weekday(d) for d in days}
                            if now.weekday() not in py_days:
                                logger.info("Disparo de intervalo ignorado para %s: fora do dia operacional permitido.", db_auto.name)
                                return
                        
                        if start_t:
                            sh, sm = map(int, start_t.split(":"))
                            if now.hour < sh or (now.hour == sh and now.minute < sm):
                                logger.info("Disparo de intervalo ignorado para %s: antes do horário operacional permitido (%s).", db_auto.name, start_t)
                                return
                        if end_t:
                            eh, em = map(int, end_t.split(":"))
                            if now.hour > eh or (now.hour == eh and now.minute > em):
                                logger.info("Disparo de intervalo ignorado para %s: após o horário operacional permitido (%s).", db_auto.name, end_t)
                                return
            except Exception as e:
                logger.warning("Falha ao validar janela operacional do disparo de %s: %s", db_auto.name, str(e))

        existing = (
            db.query(models.Execution)
            .filter(
                models.Execution.automation_id == automation_id,
                models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)),
            )
            .first()
        )
        if existing:
            logger.info("Agendamento ignorado: %s já tem execução ativa.", db_auto.name)
            return

        group_active = get_group_active_execution(
            db,
            db_auto.queue_group,
            exclude_automation_id=automation_id,
        )
        if group_active:
            logger.info(
                "Agendamento ignorado: %s bloqueada por queue_group=%s em uso por %s.",
                db_auto.name,
                db_auto.queue_group,
                group_active.id,
            )
            return

        exec_id = f"CRON_{automation_id}_{int(get_now_local().timestamp())}"
        db.add(
            build_queued_execution(
                automation=db_auto,
                exec_id=exec_id,
                requested_by="CRON",
            )
        )
        db.commit()
        logger.info("Disparo agendado: %s -> %s", db_auto.name, exec_id)
    except Exception as exc:
        logger.error("Erro no disparo agendado id=%s: %s", automation_id, exc)
    finally:
        db.close()


def reload_scheduled_tasks() -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith("job_"):
            scheduler.remove_job(job.id)

    db = SessionLocal()
    try:
        automations_db = (
            db.query(models.Automation).filter(models.Automation.enabled == True).all()
        )
        logger.info(
            "Recarregando agendamentos para %d automações habilitadas.",
            len(automations_db),
        )
        for auto in automations_db:
            if _is_reserved_cleanup_automation(auto.script_path):
                auto.enabled = False
                auto.schedule = None
                auto.updated_at = get_now_local()
                db.commit()
                logger.warning(
                    "Automação legada neutralizada por duplicar a rotina reservada de limpeza: %s (ID: %s).",
                    auto.name,
                    auto.id,
                )
                continue
            if not auto.schedule:
                continue
            try:
                sched_data = schemas.parse_schedule(auto.schedule)
                if not sched_data:
                    continue
                _register_schedule(auto.id, sched_data)
            except Exception as exc:
                logger.error("Erro ao agendar %s: %s", auto.name, exc)
        logger.info(
            "Agendador sincronizado: %d jobs ativos no total.",
            len(scheduler.get_jobs()),
        )
    finally:
        db.close()


def _register_schedule(automation_id: int, sched_data: dict[str, Any]) -> None:
    schedule_type = sched_data.get("schedule_type")
    if schedule_type == "manual":
        return
    if schedule_type == "cron":
        scheduler.add_job(
            scheduled_task_wrapper,
            CronTrigger.from_crontab(
                sched_data["cron_expression"],
                timezone=sched_data.get("timezone", "America/Sao_Paulo")
            ),
            args=[automation_id],
            id=f"job_{automation_id}_cron",
            misfire_grace_time=60,
        )
        return
    if schedule_type == "interval":
        step_minutes = int(sched_data["interval_minutes"])
        anchor_time = sched_data.get("anchor_time")
        start_date = None
        if anchor_time:
            now = get_now_local().replace(second=0, microsecond=0)
            start_date = first_interval_candidate(now, step_minutes, anchor_time)

        scheduler.add_job(
            scheduled_task_wrapper,
            IntervalTrigger(
                minutes=step_minutes,
                start_date=start_date,
                timezone=scheduler.timezone
            ),
            args=[automation_id],
            id=f"job_{automation_id}_interval",
            misfire_grace_time=60,
        )
        return
    if schedule_type == "once":
        run_at = datetime.fromisoformat(str(sched_data["run_at"]).replace("Z", ""))
        if run_at >= get_now_local():
            scheduler.add_job(
                scheduled_task_wrapper,
                DateTrigger(run_date=run_at),
                args=[automation_id],
                id=f"job_{automation_id}_once",
                misfire_grace_time=60,
            )
        return

    times = sched_data.get("times", [])
    for idx, item in enumerate(times):
        if schedule_type == "daily":
            trigger = CronTrigger(hour=item.get("h", 0), minute=item.get("m", 0))
        elif schedule_type == "weekly":
            mapped_days = [
                str(ui_day_to_python_weekday(day)) for day in sched_data.get("days_of_week", [])
            ]
            trigger = CronTrigger(
                day_of_week=",".join(mapped_days) if mapped_days else "*",
                hour=item.get("h", 0),
                minute=item.get("m", 0),
            )
        elif schedule_type == "monthly":
            trigger = CronTrigger(
                day=",".join(map(str, sched_data.get("days_of_month", []))),
                hour=item.get("h", 0),
                minute=item.get("m", 0),
            )
        else:
            continue
        scheduler.add_job(
            scheduled_task_wrapper,
            trigger,
            args=[automation_id],
            id=f"job_{automation_id}_{schedule_type}_{idx}",
            misfire_grace_time=60,
        )


def register_enterprise_jobs(retention_days: int) -> None:
    scheduler.add_job(
        run_wal_checkpoint,
        "interval",
        minutes=30,
        id="enterprise_wal_checkpoint",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        lambda: purge_old_executions(retention_days),
        CronTrigger(hour=3, minute=0),
        id="enterprise_daily_purge",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        safe_scheduler_heartbeat,
        "interval",
        minutes=15,
        id="enterprise_scheduler_heartbeat",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        capture_system_history_snapshot_job,
        "interval",
        minutes=5,
        id="enterprise_system_health_snapshot",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.add_job(
        run_file_cleanup,
        CronTrigger(hour=2, minute=0),
        id="enterprise_file_cleanup",
        replace_existing=True,
        misfire_grace_time=3600,
    )


def run_file_cleanup() -> None:
    script_path = _get_reserved_cleanup_script_path()
    try:
        logger.info("Iniciando limpeza de arquivos (Self-Cleaning)...")
        subprocess.run(["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path], check=True)
        logger.info("Limpeza de arquivos concluída com sucesso.")
    except Exception as e:
        logger.error("Erro ao executar limpeza de arquivos: %s", e)


def safe_scheduler_heartbeat() -> None:
    try:
        logger.info("Heartbeat do Agendador: OK", extra={"request_id": "SYSTEM"})
    except Exception:
        pass


def capture_system_history_snapshot_job() -> None:
    db = SessionLocal()
    try:
        from .system_diagnostics import build_diagnostics_payload
        from .system_history import capture_system_health_snapshot
        from .system_runtime import get_worker_status

        payload = build_diagnostics_payload(
            db,
            scheduler,
            get_worker_status,
            include_history=False,
        )
        capture_system_health_snapshot(db, payload, retention_days=30)
    except Exception as exc:
        logger.error("Falha ao capturar snapshot operacional: %s", exc)
    finally:
        db.close()


def list_scheduled_jobs(db: Session) -> list[schemas.ScheduledJob]:
    jobs = []
    for job in scheduler.get_jobs():
        auto_id = extract_automation_id_from_job(job.id)
        auto_name = None
        if auto_id is not None:
            auto = (
                db.query(models.Automation)
                .filter(models.Automation.id == auto_id)
                .first()
            )
            auto_name = auto.name if auto else None
        elif job.id.startswith("enterprise_"):
            auto_name = (
                f"System: {job.id.replace('enterprise_', '').replace('_', ' ').title()}"
            )
        jobs.append(
            schemas.ScheduledJob(
                id=job.id,
                automation_id=auto_id,
                automation_name=auto_name,
                next_run_time=job.next_run_time,
                trigger=str(job.trigger),
            )
        )
    return sorted(
        jobs,
        key=lambda item: item.next_run_time if item.next_run_time else datetime.max,
    )

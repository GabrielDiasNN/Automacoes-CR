"""Serviços compartilhados de agendamento e jobs do Orchestrator."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
from datetime import datetime
from typing import Any, cast

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from .. import models, notifications, schemas
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_TIMEOUT,
)
from ..database import (
    SessionLocal,
    purge_old_executions,
    purge_old_snapshots,
    run_wal_checkpoint,
    session_scope,
)
from ..runtime import scheduler, trigger_worker_wakeup
from ..schemas.schedule_rules import first_interval_candidate, ui_day_to_python_weekday
from ..timezone import get_now_local
from .beneficiamento_refresh import run_beneficiamento_refresh
from .execution_runtime import (
    RequeueValidationError,
    build_queued_execution,
    get_group_active_execution,
    prepare_requeue,
)

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


def _interval_window_blocks_trigger(  # pylint: disable=too-many-return-statements
    db_auto: models.Automation,
) -> bool:
    if not db_auto.schedule:
        return False
    try:
        sched_data = schemas.parse_schedule(cast(str | None, db_auto.schedule))
        if not sched_data or sched_data.get("schedule_type") != "interval":
            return False

        start_t = sched_data.get("start_time")
        end_t = sched_data.get("end_time")
        days = sched_data.get("days_of_week")
        if not (start_t or end_t or days):
            return False

        now = get_now_local()

        if days is not None:
            py_days = {ui_day_to_python_weekday(d) for d in days}
            if now.weekday() not in py_days:
                logger.info(
                    "Disparo de intervalo ignorado para %s: fora do dia operacional permitido.",
                    db_auto.name,
                )
                return True

        if start_t:
            sh, sm = map(int, start_t.split(":"))
            if now.hour < sh or (now.hour == sh and now.minute < sm):
                logger.info(
                    "Disparo de intervalo ignorado para %s: antes do horário operacional permitido (%s).",
                    db_auto.name,
                    start_t,
                )
                return True
        if end_t:
            eh, em = map(int, end_t.split(":"))
            if now.hour > eh or (now.hour == eh and now.minute > em):
                logger.info(
                    "Disparo de intervalo ignorado para %s: após o horário operacional permitido (%s).",
                    db_auto.name,
                    end_t,
                )
                return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Falha ao validar janela operacional do disparo de %s: %s",
            db_auto.name,
            exc,
        )
    return False


def scheduled_task_wrapper(automation_id: int) -> None:
    try:
        with session_scope(SessionLocal) as db:
            db_auto = (
                db.query(models.Automation)
                .filter(models.Automation.id == automation_id)
                .first()
            )
            if not db_auto or not db_auto.enabled:
                return
            if _is_reserved_cleanup_automation(cast(str | None, db_auto.script_path)):
                logger.warning(
                    "Agendamento ignorado para rotina reservada do sistema: %s.",
                    db_auto.name,
                )
                return

            if _interval_window_blocks_trigger(db_auto):
                return

            existing = (
                db.query(models.Execution)
                .filter(
                    models.Execution.automation_id == automation_id,
                    models.Execution.status.in_(list(EXECUTION_ACTIVE_STATUSES)),
                )
                .first()
            )
            if existing:
                logger.info(
                    "Agendamento ignorado: %s já tem execução ativa.", db_auto.name
                )
                return

            group_active = get_group_active_execution(
                db,
                cast(str | None, db_auto.queue_group),
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
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Erro no disparo agendado id=%s: %s", automation_id, exc)


def reload_scheduled_tasks() -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith("job_"):
            scheduler.remove_job(job.id)

    with session_scope(SessionLocal) as db:
        automations_db = (
            db.query(models.Automation)
            .filter(models.Automation.enabled.is_(True))
            .all()
        )
        logger.info(
            "Recarregando agendamentos para %d automações habilitadas.",
            len(automations_db),
        )
        for auto in automations_db:
            if _is_reserved_cleanup_automation(cast(str | None, auto.script_path)):
                auto.enabled = False  # type: ignore[assignment]
                auto.schedule = None  # type: ignore[assignment]
                auto.updated_at = get_now_local()  # type: ignore[assignment]
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
                sched_data = schemas.parse_schedule(cast(str | None, auto.schedule))
                if not sched_data:
                    continue
                _register_schedule(cast(int, auto.id), sched_data)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.error("Erro ao agendar %s: %s", auto.name, exc)
        logger.info(
            "Agendador sincronizado: %d jobs ativos no total.",
            len(scheduler.get_jobs()),
        )


def _register_cron_schedule(automation_id: int, sched_data: dict[str, Any]) -> None:
    exprs = sched_data["cron_expression"]
    expr_list = exprs if isinstance(exprs, list) else [exprs]
    single = len(expr_list) == 1
    for idx, expr in enumerate(expr_list):
        job_id = (
            f"job_{automation_id}_cron" if single else f"job_{automation_id}_cron_{idx}"
        )
        scheduler.add_job(
            scheduled_task_wrapper,
            CronTrigger.from_crontab(
                expr,
                timezone=sched_data.get("timezone", "America/Sao_Paulo"),
            ),
            args=[automation_id],
            id=job_id,
            misfire_grace_time=60,
        )


def _register_schedule(automation_id: int, sched_data: dict[str, Any]) -> None:
    schedule_type = sched_data.get("schedule_type")
    if schedule_type == "manual":
        return
    if schedule_type == "cron":
        _register_cron_schedule(automation_id, sched_data)
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
                minutes=step_minutes, start_date=start_date, timezone=scheduler.timezone
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
                str(ui_day_to_python_weekday(day))
                for day in sched_data.get("days_of_week", [])
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


def auto_retry_transient_failures() -> None:
    """Reenfileira automaticamente ERROR/TIMEOUT dentro do limite de retry cadastrado.

    Reusa ``prepare_requeue`` (mesma validacao de concorrencia/queue_group do
    requeue manual). Respeita ``cooldown_minutes`` da automacao como backoff
    antes de tentar de novo, e so age em execucoes cujo ``max_retries`` > 0
    (config explicita do operador, ver ``models.Automation``).
    """
    try:
        with session_scope(SessionLocal) as db:
            candidates = (
                db.query(models.Execution)
                .filter(
                    models.Execution.status.in_(
                        [EXECUTION_STATUS_ERROR, EXECUTION_STATUS_TIMEOUT]
                    ),
                    models.Execution.retry_count < models.Execution.max_retries,
                )
                .order_by(models.Execution.finished_at.asc())
                .limit(20)
                .all()
            )
            for db_exec in candidates:
                automation = db_exec.automation
                if not automation or not automation.enabled or not db_exec.finished_at:
                    continue
                elapsed_minutes = (
                    get_now_local() - db_exec.finished_at
                ).total_seconds() / 60
                if elapsed_minutes < (automation.cooldown_minutes or 0):
                    continue

                attempt = int(db_exec.retry_count or 0) + 1
                try:
                    new_exec, _audit_payload = prepare_requeue(
                        db,
                        db_exec,
                        payload_reason=(
                            "Retry automatico apos falha transitoria "
                            f"(tentativa {attempt}/{db_exec.max_retries})."
                        ),
                        payload_requested_by="AUTO_RETRY",
                        payload_priority=None,
                        fallback_requested_by="AUTO_RETRY",
                    )
                except RequeueValidationError as exc:
                    logger.info(
                        "Auto-retry ignorado para %s: %s", db_exec.id, exc.detail
                    )
                    continue

                db.add(new_exec)
                db.commit()
                logger.info(
                    "Auto-retry disparado: %s -> %s (tentativa %d/%s)",
                    db_exec.id,
                    new_exec.id,
                    attempt,
                    db_exec.max_retries,
                )
                trigger_worker_wakeup()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Falha no job de auto-retry: %s", exc)


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
        purge_old_snapshots,
        CronTrigger(hour=3, minute=30),
        id="enterprise_snapshot_purge",
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
        auto_retry_transient_failures,
        "interval",
        minutes=3,
        id="enterprise_auto_retry",
        replace_existing=True,
        misfire_grace_time=120,
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
    register_beneficiamento_live_jobs()


def _live_interval_seconds(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def register_beneficiamento_live_jobs() -> None:
    """Refresh ao vivo do Beneficiamento (substitui o batch espaçado).

    O diário é reprocessado em loop curto (mantém o SQLite/snapshot frescos, o que
    torna o dashboard "ao vivo" já que /overview lê do SQLite). O mensal é
    reprocessado em cadência mais lenta. Cada ciclo roda em subprocesso isolado,
    respeitando o orçamento de ~20s do Oracle. ``max_instances=1`` + ``coalesce``
    evitam refreshes sobrepostos do mesmo período.
    """
    diario_interval = _live_interval_seconds("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", 90)
    mensal_interval = _live_interval_seconds(
        "BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS", 600
    )

    scheduler.add_job(
        lambda: run_beneficiamento_refresh("diario"),
        IntervalTrigger(seconds=diario_interval),
        id="beneficiamento_live_diario",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        lambda: run_beneficiamento_refresh("mensal"),
        IntervalTrigger(seconds=mensal_interval),
        id="beneficiamento_mensal_rollup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )


def run_file_cleanup() -> None:
    script_path = _get_reserved_cleanup_script_path()
    try:
        logger.info("Iniciando limpeza de arquivos (Self-Cleaning)...")
        subprocess.run(
            [
                "pwsh.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ],
            check=True,
        )
        logger.info("Limpeza de arquivos concluída com sucesso.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Erro ao executar limpeza de arquivos: %s", e)


def safe_scheduler_heartbeat() -> None:
    with contextlib.suppress(Exception):
        logger.info("Heartbeat do Agendador: OK", extra={"request_id": "SYSTEM"})


# Mapeamento de slo_breaches para alerta de infraestrutura (fora do dashboard):
# so os breaches que indicam risco de a fila inteira parar de ser processada,
# nao qualquer degradacao (evita alerta para coisas ja cobertas por
# dispatch_alerts em cada falha de automacao).
_INFRA_BREACH_LABELS = {
    "worker_offline": "Processador (worker) sem heartbeat recente.",
    "wal_critical": "WAL do banco de dados em nivel critico.",
    "orphaned_running": "Execucao em andamento sem responsavel valido (worker orfao).",
}


def _dispatch_infra_alerts_from_payload(payload: dict[str, Any]) -> None:
    """Dispara alerta de infraestrutura para os slo_breaches criticos do payload."""
    breaches = payload.get("slo_breaches") or {}
    for code, label in _INFRA_BREACH_LABELS.items():
        if breaches.get(code):
            notifications.send_infra_alert(code, label)


def capture_system_history_snapshot_job() -> None:
    try:
        with session_scope(SessionLocal) as db:
            # pylint: disable=import-outside-toplevel,cyclic-import
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
            _dispatch_infra_alerts_from_payload(payload)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Falha ao capturar snapshot operacional: %s", exc)


def list_scheduled_jobs(db: Session) -> list[schemas.ScheduledJob]:
    # Ordena pelo next_run_time bruto do APScheduler (antes de ScheduledJob
    # formatá-lo em string BR) usando uma chave (has_run_time, valor): jobs sem
    # próxima execução (None) vão para o fim sem comparar string com datetime,
    # nem datetime naive com aware (bug corrigido em 03/07/2026).
    entries: list[tuple[tuple[int, datetime | int], schemas.ScheduledJob]] = []
    for job in scheduler.get_jobs():
        auto_id = extract_automation_id_from_job(job.id)
        auto_name: str | None = None
        if auto_id is not None:
            auto = (
                db.query(models.Automation)
                .filter(models.Automation.id == auto_id)
                .first()
            )
            auto_name = cast(str | None, auto.name) if auto else None
        elif job.id.startswith("enterprise_"):
            auto_name = (
                f"System: {job.id.replace('enterprise_', '').replace('_', ' ').title()}"
            )
        sort_key = (0, job.next_run_time) if job.next_run_time else (1, 0)
        entries.append(
            (
                sort_key,
                schemas.ScheduledJob(
                    id=job.id,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    next_run_time=job.next_run_time,
                    trigger=str(job.trigger),
                ),
            )
        )
    entries.sort(key=lambda entry: entry[0])
    return [entry[1] for entry in entries]

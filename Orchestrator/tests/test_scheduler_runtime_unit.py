# pylint: disable=protected-access
"""Testes unitários de app/services/scheduler_runtime.py e app/runtime.py (wakeup)."""

import json
import os
import subprocess
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from app import models, runtime as app_runtime
from app.constants import EXECUTION_STATUS_ERROR, EXECUTION_STATUS_PENDING
from app.services import scheduler_runtime as sr
from app.timezone import get_now_local
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _fake_automation(name: str, schedule: dict[str, Any] | None) -> models.Automation:
    return models.Automation(
        name=name,
        script_path="./test/run.ps1",
        schedule=json.dumps(schedule) if schedule is not None else None,
    )


# ---------------------------------------------------------------------------
# extract_automation_id_from_job
# ---------------------------------------------------------------------------


def test_extract_automation_id_from_job_valido() -> None:
    assert sr.extract_automation_id_from_job("job_42_cron") == 42


def test_extract_automation_id_from_job_prefixo_invalido() -> None:
    assert sr.extract_automation_id_from_job("enterprise_wal_checkpoint") is None


def test_extract_automation_id_from_job_sem_partes_suficientes() -> None:
    assert sr.extract_automation_id_from_job("job_") is None


def test_extract_automation_id_from_job_nao_numerico() -> None:
    assert sr.extract_automation_id_from_job("job_abc_cron") is None


# ---------------------------------------------------------------------------
# _is_reserved_cleanup_automation
# ---------------------------------------------------------------------------


def test_is_reserved_cleanup_automation_none_retorna_false() -> None:
    assert sr._is_reserved_cleanup_automation(None) is False


def test_is_reserved_cleanup_automation_reconhece_caminho_relativo() -> None:
    assert (
        sr._is_reserved_cleanup_automation("./Tools/AplicarPoliticaRetencao.ps1")
        is True
    )


def test_is_reserved_cleanup_automation_ignora_script_diferente() -> None:
    assert sr._is_reserved_cleanup_automation("./Receitas Emitidas/run.ps1") is False


# ---------------------------------------------------------------------------
# _interval_window_blocks_trigger
# ---------------------------------------------------------------------------
# Congelado em quarta-feira (python weekday=2, dia UI=3) às 14:30.
_QUARTA_1430 = datetime(2026, 7, 8, 14, 30)


def test_interval_window_sem_schedule_nao_bloqueia() -> None:
    auto = _fake_automation("Robo", None)
    assert sr._interval_window_blocks_trigger(auto) is False


def test_interval_window_schedule_nao_interval_nao_bloqueia() -> None:
    auto = _fake_automation(
        "Robo", {"schedule_type": "cron", "cron_expression": "0 8 * * *"}
    )
    assert sr._interval_window_blocks_trigger(auto) is False


def test_interval_window_sem_janela_configurada_nao_bloqueia(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo", {"schedule_type": "interval", "interval_minutes": 30}
    )
    assert sr._interval_window_blocks_trigger(auto) is False


def test_interval_window_bloqueia_fora_do_dia_permitido(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "days_of_week": [1],
        },  # so segunda
    )
    assert sr._interval_window_blocks_trigger(auto) is True


def test_interval_window_permite_dentro_do_dia_permitido(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "days_of_week": [3],
        },  # quarta
    )
    assert sr._interval_window_blocks_trigger(auto) is False


def test_interval_window_bloqueia_antes_do_horario_inicial(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {"schedule_type": "interval", "interval_minutes": 30, "start_time": "15:00"},
    )
    assert sr._interval_window_blocks_trigger(auto) is True


def test_interval_window_bloqueia_apos_horario_final(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {"schedule_type": "interval", "interval_minutes": 30, "end_time": "14:00"},
    )
    assert sr._interval_window_blocks_trigger(auto) is True


def test_interval_window_permite_dentro_do_horario(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "start_time": "08:00",
            "end_time": "18:00",
        },
    )
    assert sr._interval_window_blocks_trigger(auto) is False


def test_interval_window_schedule_malformado_nao_lanca_excecao() -> None:
    auto = models.Automation(
        name="Robo Malformado",
        script_path="./test/run.ps1",
        schedule="{isso nao e json valido",
    )
    assert sr._interval_window_blocks_trigger(auto) is False


# ---------------------------------------------------------------------------
# safe_scheduler_heartbeat
# ---------------------------------------------------------------------------


def test_safe_scheduler_heartbeat_nao_lanca_mesmo_com_falha_de_log() -> None:
    with patch("app.services.scheduler_runtime.logger.info", side_effect=RuntimeError):
        sr.safe_scheduler_heartbeat()  # nao deve propagar excecao


# ---------------------------------------------------------------------------
# run_file_cleanup
# ---------------------------------------------------------------------------


def test_run_file_cleanup_sucesso_invoca_powershell_51() -> None:
    """Regressão: era o único ponto do runtime a exigir `pwsh.exe` (PS7).

    Em host sem PowerShell 7 o job das 02:00 falhava toda noite e o `except`
    largo transformava isso numa linha de log — a política de retenção nunca
    rodava e o disco crescia sem limite.
    """
    with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        sr.run_file_cleanup()

    args, kwargs = mock_run.call_args
    assert args[0][0] == "powershell.exe"
    assert kwargs.get("check") is True


def test_run_file_cleanup_tem_timeout() -> None:
    """Sem `timeout=`, um script travado prendia uma thread do APScheduler."""
    with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        sr.run_file_cleanup()

    _args, kwargs = mock_run.call_args
    assert kwargs.get("timeout") == sr.FILE_CLEANUP_TIMEOUT_SECONDS
    assert kwargs["timeout"] > 0


def test_run_file_cleanup_nao_repassa_segredos() -> None:
    """O subprocesso recebe a allowlist, não `os.environ` inteiro."""
    with patch.dict(
        os.environ,
        {"ORCHESTRATOR_API_KEY": "chave-secreta", "ORACLE_READONLY_PASSWORD": "senha"},
    ):
        with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            sr.run_file_cleanup()

    _args, kwargs = mock_run.call_args
    env = kwargs.get("env")
    assert env is not None, "run_file_cleanup precisa passar env= explícito"
    assert "ORCHESTRATOR_API_KEY" not in env
    assert "ORACLE_READONLY_PASSWORD" not in env


def test_run_file_cleanup_timeout_nao_propaga() -> None:
    with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("powershell.exe", 900)
        sr.run_file_cleanup()  # nao deve propagar excecao


def test_run_file_cleanup_falha_nao_propaga_excecao() -> None:
    with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "powershell.exe")
        sr.run_file_cleanup()  # nao deve propagar excecao


# ---------------------------------------------------------------------------
# list_scheduled_jobs
# ---------------------------------------------------------------------------


def test_list_scheduled_jobs_resolve_nome_da_automacao(db_session: Any) -> None:
    auto = models.Automation(name="Robo Agendado", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.commit()

    fake_job_automation = MagicMock(
        id=f"job_{auto.id}_cron",
        next_run_time=datetime(2026, 7, 8, 8, 0),
        trigger="cron",
    )
    fake_job_enterprise = MagicMock(
        id="enterprise_wal_checkpoint", next_run_time=None, trigger="interval"
    )

    with patch.object(
        app_runtime.scheduler,
        "get_jobs",
        return_value=[fake_job_enterprise, fake_job_automation],
    ):
        jobs = sr.list_scheduled_jobs(db_session)

    assert jobs[0].automation_name == "Robo Agendado"
    assert jobs[0].automation_id == auto.id
    assert jobs[1].id == "enterprise_wal_checkpoint"
    assert jobs[1].automation_name == "System: Wal Checkpoint"


def test_list_scheduled_jobs_resolve_nome_correto_por_job_com_multiplas_automacoes(
    db_session: Any,
) -> None:
    """Regressão: a resolução em lote (1 IN query) não pode trocar o nome
    entre automações distintas, como uma implementação incorreta de dict
    (ex.: sempre pegar a última linha) faria passar despercebido."""
    auto_a = models.Automation(name="Automacao A", script_path="./test/run.ps1")
    auto_b = models.Automation(name="Automacao B", script_path="./test/run.ps1")
    db_session.add_all([auto_a, auto_b])
    db_session.flush()
    db_session.commit()

    job_a = MagicMock(
        id=f"job_{auto_a.id}_cron",
        next_run_time=datetime(2026, 7, 8, 8, 0),
        trigger="cron",
    )
    job_b = MagicMock(
        id=f"job_{auto_b.id}_cron",
        next_run_time=datetime(2026, 7, 8, 9, 0),
        trigger="cron",
    )

    with patch.object(app_runtime.scheduler, "get_jobs", return_value=[job_a, job_b]):
        jobs = sr.list_scheduled_jobs(db_session)

    by_automation_id = {job.automation_id: job.automation_name for job in jobs}
    assert by_automation_id[int(auto_a.id)] == "Automacao A"
    assert by_automation_id[int(auto_b.id)] == "Automacao B"


def test_list_scheduled_jobs_sem_jobs_de_automacao_nao_consulta_o_banco(
    db_session: Any,
) -> None:
    """Sem nenhum job de automação (só enterprise_*), o lookup em lote não
    deve disparar a query IN(...) com uma lista vazia."""
    fake_job_enterprise = MagicMock(
        id="enterprise_wal_checkpoint", next_run_time=None, trigger="interval"
    )
    query_spy = MagicMock(wraps=db_session.query)
    with (
        patch.object(
            app_runtime.scheduler, "get_jobs", return_value=[fake_job_enterprise]
        ),
        patch.object(db_session, "query", query_spy),
    ):
        jobs = sr.list_scheduled_jobs(db_session)

    assert jobs[0].automation_name == "System: Wal Checkpoint"
    query_spy.assert_not_called()


# ---------------------------------------------------------------------------
# reload_scheduled_tasks — dispatch no scheduler REAL (achado nº 2)
# ---------------------------------------------------------------------------


def test_reload_preserva_next_run_time_do_interval_no_dispatch_real(
    client: TestClient,  # pylint: disable=unused-argument
    db_session: Session,
) -> None:
    """Achado nº 2: `_resolve_interval_start_date` tem 3 testes diretos, mas o
    CALL SITE — o dispatch que repassa o resultado como `start_date=` ao
    `IntervalTrigger` — nunca rodava com o scheduler real. Uma regressão que
    removesse a propagação do `start_date=` passaria com a suíte verde.
    """
    from apscheduler.triggers.interval import (  # pylint: disable=import-outside-toplevel
        IntervalTrigger,
    )

    auto = models.Automation(
        id=970,
        name="Automacao Interval Dispatch",
        script_path="./test/run.ps1",
        enabled=True,
        schedule=json.dumps({"schedule_type": "interval", "interval_minutes": 60}),
    )
    db_session.add(auto)
    db_session.commit()

    job_id = "job_970_interval"
    scheduler = app_runtime.scheduler
    try:
        # Job pré-existente com um `next_run_time` já a caminho (daqui a 1h).
        scheduler.add_job(
            sr.scheduled_task_wrapper,
            IntervalTrigger(minutes=60),
            args=[970],
            id=job_id,
            replace_existing=True,
        )
        esperado = scheduler.get_job(job_id).next_run_time
        assert esperado is not None

        sr.reload_scheduled_tasks()

        recriado = scheduler.get_job(job_id)
        assert recriado is not None, "o dispatch de interval não recriou a job"
        # `next_run_time` preservado (tolerância de 2s para o custo do reload).
        assert abs((recriado.next_run_time - esperado).total_seconds()) < 2
    finally:
        try:
            scheduler.remove_job(job_id)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        sr._pending_interval_resume.clear()


def test_register_schedule_once_no_passado_loga_aviso(
    caplog: Any, monkeypatch: Any
) -> None:
    # Achado de baixa severidade: um `once` com `run_at` no passado não gerava
    # job nenhum e o operador não tinha como saber por quê.
    monkeypatch.setattr(sr, "get_now_local", lambda: datetime(2026, 7, 8, 12, 0))
    with caplog.at_level("WARNING", logger="orchestrator"):
        sr._register_schedule(
            999, {"schedule_type": "once", "run_at": "2026-07-01T09:00:00"}
        )
    assert any("once" in r.message and "999" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# app.runtime: trigger_worker_wakeup / register_event_loop
# ---------------------------------------------------------------------------


def test_trigger_worker_wakeup_usa_call_soon_threadsafe(monkeypatch: Any) -> None:
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    monkeypatch.setattr(app_runtime, "_event_loop", fake_loop)

    app_runtime.trigger_worker_wakeup()

    fake_loop.call_soon_threadsafe.assert_called_once_with(
        app_runtime.task_queued_event.set
    )


def test_wakeup_sem_event_loop_registrado_nao_lanca_excecao(monkeypatch: Any) -> None:
    # Achado #34: sem loop registrado não existe caminho thread-safe para
    # sinalizar (asyncio.Event.set() fora do loop viola a premissa do módulo).
    # O wake-up vira no-op logado — o worker consome a tarefa no próximo polling.
    monkeypatch.setattr(app_runtime, "_event_loop", None)
    app_runtime.task_queued_event.clear()

    app_runtime.trigger_worker_wakeup()  # nao deve lancar excecao

    assert app_runtime.task_queued_event.is_set() is False


def test_wakeup_com_loop_fechado_nao_sinaliza_fora_do_loop(monkeypatch: Any) -> None:
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = True
    monkeypatch.setattr(app_runtime, "_event_loop", fake_loop)
    app_runtime.task_queued_event.clear()

    app_runtime.trigger_worker_wakeup()

    fake_loop.call_soon_threadsafe.assert_not_called()
    assert app_runtime.task_queued_event.is_set() is False


def test_register_event_loop_atualiza_o_loop_global(monkeypatch: Any) -> None:
    monkeypatch.setattr(app_runtime, "_event_loop", None)
    fake_loop = MagicMock()

    app_runtime.register_event_loop(fake_loop)

    assert app_runtime._event_loop is fake_loop


# ---------------------------------------------------------------------------
# auto_retry_transient_failures
# ---------------------------------------------------------------------------


def _create_error_execution(
    db_session: Session,
    *,
    automation_id: int,
    exec_id: str,
    retries: tuple[int, int] = (0, 2),
    minutes_ago_finished: float = 5.0,
) -> models.Execution:
    retry_count, max_retries = retries
    execution = models.Execution(
        id=exec_id,
        automation_id=automation_id,
        status=EXECUTION_STATUS_ERROR,
        retry_count=retry_count,
        max_retries=max_retries,
        started_at=get_now_local() - timedelta(minutes=minutes_ago_finished + 1),
        finished_at=get_now_local() - timedelta(minutes=minutes_ago_finished),
    )
    db_session.add(execution)
    db_session.commit()
    return execution


def test_auto_retry_reenfileira_falha_transitoria_dentro_do_limite(
    client: TestClient, db_session: Session  # pylint: disable=unused-argument
) -> None:
    auto = models.Automation(
        id=980,
        name="Automacao Auto-Retry",
        script_path="./test/run.ps1",
        enabled=True,
        max_retries=2,
        cooldown_minutes=0,
    )
    db_session.add(auto)
    db_session.commit()
    _create_error_execution(db_session, automation_id=980, exec_id="AR_001")

    with patch("app.services.scheduler_runtime.trigger_worker_wakeup") as mock_wakeup:
        sr.auto_retry_transient_failures()

    mock_wakeup.assert_called_once()
    original = db_session.query(models.Execution).filter_by(id="AR_001").first()
    assert original is not None
    assert original.status == "REQUEUED"

    novos = (
        db_session.query(models.Execution)
        .filter(
            models.Execution.automation_id == 980,
            models.Execution.status == EXECUTION_STATUS_PENDING,
        )
        .all()
    )
    assert len(novos) == 1
    assert novos[0].retry_count == 1
    assert novos[0].requested_by == "AUTO_RETRY"


def test_auto_retry_respeita_cooldown_minutes(
    client: TestClient, db_session: Session  # pylint: disable=unused-argument
) -> None:
    auto = models.Automation(
        id=981,
        name="Automacao Com Cooldown",
        script_path="./test/run.ps1",
        enabled=True,
        max_retries=2,
        cooldown_minutes=30,
    )
    db_session.add(auto)
    db_session.commit()
    _create_error_execution(
        db_session, automation_id=981, exec_id="AR_002", minutes_ago_finished=5.0
    )

    sr.auto_retry_transient_failures()

    original = db_session.query(models.Execution).filter_by(id="AR_002").first()
    assert original is not None
    assert original.status == EXECUTION_STATUS_ERROR  # ainda nao retentado


def test_auto_retry_ignora_automacao_desabilitada(
    client: TestClient, db_session: Session  # pylint: disable=unused-argument
) -> None:
    auto = models.Automation(
        id=982,
        name="Automacao Desabilitada",
        script_path="./test/run.ps1",
        enabled=False,
        max_retries=2,
        cooldown_minutes=0,
    )
    db_session.add(auto)
    db_session.commit()
    _create_error_execution(db_session, automation_id=982, exec_id="AR_003")

    sr.auto_retry_transient_failures()

    original = db_session.query(models.Execution).filter_by(id="AR_003").first()
    assert original is not None
    assert original.status == EXECUTION_STATUS_ERROR


def test_auto_retry_nao_reenfileira_acima_do_max_retries(
    client: TestClient, db_session: Session  # pylint: disable=unused-argument
) -> None:
    auto = models.Automation(
        id=983,
        name="Automacao No Limite",
        script_path="./test/run.ps1",
        enabled=True,
        max_retries=2,
        cooldown_minutes=0,
    )
    db_session.add(auto)
    db_session.commit()
    _create_error_execution(
        db_session, automation_id=983, exec_id="AR_004", retries=(2, 2)
    )

    sr.auto_retry_transient_failures()

    original = db_session.query(models.Execution).filter_by(id="AR_004").first()
    assert original is not None
    assert original.status == EXECUTION_STATUS_ERROR


def test_auto_retry_ignora_conflito_de_concorrencia(
    client: TestClient, db_session: Session  # pylint: disable=unused-argument
) -> None:
    """Se ja existe execucao ativa para a automacao, prepare_requeue recusa e o job segue sem quebrar."""
    auto = models.Automation(
        id=984,
        name="Automacao Com Execucao Ativa",
        script_path="./test/run.ps1",
        enabled=True,
        max_retries=2,
        cooldown_minutes=0,
    )
    db_session.add(auto)
    db_session.commit()
    _create_error_execution(db_session, automation_id=984, exec_id="AR_005")
    db_session.add(
        models.Execution(
            id="AR_005_ATIVA",
            automation_id=984,
            status=EXECUTION_STATUS_PENDING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    sr.auto_retry_transient_failures()  # nao deve lancar excecao

    original = db_session.query(models.Execution).filter_by(id="AR_005").first()
    assert original is not None
    assert original.status == EXECUTION_STATUS_ERROR


# ---------------------------------------------------------------------------
# _dispatch_infra_alerts_from_payload
# ---------------------------------------------------------------------------


def test_dispatch_infra_alerts_dispara_apenas_breaches_mapeados() -> None:
    payload = {
        "slo_breaches": {
            "worker_offline": True,
            "wal_critical": False,
            "orphaned_running": True,
            "sla_breached": True,  # nao mapeado para alerta de infra
        }
    }
    with patch("app.services.scheduler_runtime.notifications") as mock_notifications:
        sr._dispatch_infra_alerts_from_payload(payload)

    called_components = {
        call.args[0] for call in mock_notifications.send_infra_alert.call_args_list
    }
    assert called_components == {"worker_offline", "orphaned_running"}


def test_dispatch_infra_alerts_sem_breaches_nao_dispara() -> None:
    with patch("app.services.scheduler_runtime.notifications") as mock_notifications:
        sr._dispatch_infra_alerts_from_payload({"slo_breaches": {}})

    mock_notifications.send_infra_alert.assert_not_called()

"""Testes unitários de app/services/scheduler_runtime.py e app/runtime.py (wakeup)."""

import contextlib
import json
import logging
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytz
from app import models, runtime as app_runtime
from app.constants import EXECUTION_STATUS_ERROR, EXECUTION_STATUS_PENDING
from app.services import execution_runtime as er, scheduler_runtime as sr
from app.timezone import get_now_local
from apscheduler.triggers.interval import (
    IntervalTrigger,
)
from carregadores_modulos import acessar_privado
from sqlalchemy.orm import Session


@dataclass
class _FakeJob:
    """Job do APScheduler reduzido ao que `_is_near_next_scheduled_run` lê."""

    id: str
    next_run_time: datetime


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
    assert acessar_privado(sr, "_is_reserved_cleanup_automation")(None) is False


def test_is_reserved_cleanup_automation_reconhece_caminho_relativo() -> None:
    assert (
        acessar_privado(sr, "_is_reserved_cleanup_automation")(
            "./Tools/AplicarPoliticaRetencao.ps1"
        )
        is True
    )


def test_is_reserved_cleanup_automation_ignora_script_diferente() -> None:
    assert (
        acessar_privado(sr, "_is_reserved_cleanup_automation")(
            "./Receitas Emitidas/run.ps1"
        )
        is False
    )


# ---------------------------------------------------------------------------
# _interval_window_blocks_trigger
# ---------------------------------------------------------------------------
# Congelado em quarta-feira (python weekday=2, dia UI=3) às 14:30.
_QUARTA_1430 = datetime(2026, 7, 8, 14, 30)


def test_interval_window_sem_schedule_nao_bloqueia() -> None:
    auto = _fake_automation("Robo", None)
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is False


def test_interval_window_schedule_nao_interval_nao_bloqueia() -> None:
    auto = _fake_automation(
        "Robo", {"schedule_type": "cron", "cron_expression": "0 8 * * *"}
    )
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is False


def test_interval_window_sem_janela_configurada_nao_bloqueia(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo", {"schedule_type": "interval", "interval_minutes": 30}
    )
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is False


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
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is True


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
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is False


def test_interval_window_bloqueia_antes_do_horario_inicial(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {"schedule_type": "interval", "interval_minutes": 30, "start_time": "15:00"},
    )
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is True


def test_interval_window_bloqueia_apos_horario_final(monkeypatch: Any) -> None:
    monkeypatch.setattr(sr, "get_now_local", lambda: _QUARTA_1430)
    auto = _fake_automation(
        "Robo",
        {"schedule_type": "interval", "interval_minutes": 30, "end_time": "14:00"},
    )
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is True


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
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is False


def test_interval_window_schedule_malformado_nao_lanca_excecao() -> None:
    auto = models.Automation(
        name="Robo Malformado",
        script_path="./test/run.ps1",
        schedule="{isso nao e json valido",
    )
    assert acessar_privado(sr, "_interval_window_blocks_trigger")(auto) is False


# ---------------------------------------------------------------------------
# safe_scheduler_heartbeat
# ---------------------------------------------------------------------------


class _StreamQuebrado:
    """Stream que falha em toda escrita (ex.: disco cheio); conta as tentativas."""

    def __init__(self) -> None:
        self.tentativas = 0

    def write(self, _texto: str) -> int:
        self.tentativas += 1
        raise OSError("disco cheio")

    def flush(self) -> None:
        return None


def test_safe_scheduler_heartbeat_nao_lanca_mesmo_com_falha_de_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # StreamHandler.emit captura a falha e chama handleError; com raiseExceptions
    # False o handleError fica silencioso, como em producao sem traceback no stderr.
    monkeypatch.setattr(logging, "raiseExceptions", False)
    stream = _StreamQuebrado()
    handler = logging.StreamHandler(stream)
    nivel_original = sr.logger.level
    sr.logger.setLevel(logging.INFO)
    sr.logger.addHandler(handler)
    try:
        sr.safe_scheduler_heartbeat()  # nao deve propagar excecao
    finally:
        sr.logger.removeHandler(handler)
        sr.logger.setLevel(nivel_original)
    # Garante que o caminho de falha foi de fato exercitado (nao um teste vazio).
    assert stream.tentativas >= 1


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
    with (
        patch.dict(
            os.environ,
            {
                "ORCHESTRATOR_API_KEY": "chave-secreta",
                "ORACLE_READONLY_PASSWORD": "senha",
            },
        ),
        patch("app.services.scheduler_runtime.subprocess.run") as mock_run,
    ):
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


@pytest.mark.usefixtures("client")
def test_reload_preserva_next_run_time_do_interval_no_dispatch_real(
    db_session: Session,
) -> None:
    """Achado nº 2: `_resolve_interval_start_date` tem 3 testes diretos, mas o
    CALL SITE — o dispatch que repassa o resultado como `start_date=` ao
    `IntervalTrigger` — nunca rodava com o scheduler real. Uma regressão que
    removesse a propagação do `start_date=` passaria com a suíte verde.
    """

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
        with contextlib.suppress(Exception):
            scheduler.remove_job(job_id)
        acessar_privado(sr, "_pending_interval_resume").clear()


@pytest.mark.usefixtures("client")
def test_reload_isola_falha_inesperada_de_uma_automacao(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falha de tipo fora de ERROS_DE_SCHEDULE (OverflowError) ao agendar uma
    automação não pode abortar o registro das demais."""
    agenda = json.dumps({"schedule_type": "interval", "interval_minutes": 60})
    for auto_id in (971, 972):
        db_session.add(
            models.Automation(
                id=auto_id,
                name=f"Automacao Isolamento {auto_id}",
                script_path=f"./test/run_{auto_id}.ps1",
                enabled=True,
                schedule=agenda,
            )
        )
    db_session.commit()

    registradas: list[int] = []

    def _registrar(automation_id: int, _sched: dict[str, Any]) -> None:
        if automation_id == 971:
            raise OverflowError("intervalo absurdo")
        registradas.append(automation_id)

    monkeypatch.setattr(sr, "_register_schedule", _registrar)
    try:
        sr.reload_scheduled_tasks()
    finally:
        acessar_privado(sr, "_pending_interval_resume").clear()

    assert 972 in registradas


def test_register_schedule_once_no_passado_loga_aviso(
    caplog: Any, monkeypatch: Any
) -> None:
    # Achado de baixa severidade: um `once` com `run_at` no passado não gerava
    # job nenhum e o operador não tinha como saber por quê.
    monkeypatch.setattr(sr, "get_now_local", lambda: datetime(2026, 7, 8, 12, 0))
    with caplog.at_level("WARNING", logger="orchestrator"):
        acessar_privado(sr, "_register_schedule")(
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

    assert acessar_privado(app_runtime, "_event_loop") is fake_loop


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


@pytest.mark.usefixtures("client")
def test_auto_retry_reenfileira_falha_transitoria_dentro_do_limite(
    db_session: Session,
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


@pytest.mark.usefixtures("client")
def test_auto_retry_respeita_cooldown_minutes(
    db_session: Session,
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


@pytest.mark.usefixtures("client")
def test_auto_retry_ignora_automacao_desabilitada(
    db_session: Session,
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


@pytest.mark.usefixtures("client")
def test_auto_retry_nao_reenfileira_acima_do_max_retries(
    db_session: Session,
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


@pytest.mark.usefixtures("client")
def test_auto_retry_ignora_conflito_de_concorrencia(
    db_session: Session,
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
        acessar_privado(sr, "_dispatch_infra_alerts_from_payload")(payload)

    called_components = {
        call.args[0] for call in mock_notifications.send_infra_alert.call_args_list
    }
    assert called_components == {"worker_offline", "orphaned_running"}


def test_dispatch_infra_alerts_sem_breaches_nao_dispara() -> None:
    with patch("app.services.scheduler_runtime.notifications") as mock_notifications:
        acessar_privado(sr, "_dispatch_infra_alerts_from_payload")({"slo_breaches": {}})

    mock_notifications.send_infra_alert.assert_not_called()


# ---------------------------------------------------------------------------
# register_beneficiamento_live_jobs / _live_interval_seconds
# ---------------------------------------------------------------------------


def test_live_interval_seconds_loga_aviso_em_valor_invalido(
    monkeypatch: Any, caplog: Any
) -> None:
    monkeypatch.delenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", raising=False)
    assert (
        acessar_privado(sr, "_live_interval_seconds")(
            "BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", 90
        )
        == 90
    )

    monkeypatch.setenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", "1800")
    assert (
        acessar_privado(sr, "_live_interval_seconds")(
            "BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", 90
        )
        == 1800
    )

    with caplog.at_level("WARNING", logger="orchestrator"):
        monkeypatch.setenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", "30m")
        assert (
            acessar_privado(sr, "_live_interval_seconds")(
                "BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", 90
            )
            == 90
        )
        monkeypatch.setenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", "0")
        assert (
            acessar_privado(sr, "_live_interval_seconds")(
                "BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", 90
            )
            == 90
        )

    warnings = [
        r.message
        for r in caplog.records
        if "BENEFICIAMENTO_LIVE_INTERVAL_SECONDS" in r.message
    ]
    assert len(warnings) == 2


def test_register_beneficiamento_live_jobs_escalona_e_preserva_timezone(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS", "86400")
    scheduler = app_runtime.scheduler
    try:
        sr.register_beneficiamento_live_jobs()
        diario = scheduler.get_job("beneficiamento_live_diario")
        mensal = scheduler.get_job("beneficiamento_mensal_rollup")
        assert diario is not None and mensal is not None
        assert diario.next_run_time is not None and mensal.next_run_time is not None
        assert (mensal.next_run_time - diario.next_run_time).total_seconds() >= 100
        assert diario.misfire_grace_time >= 120
        assert str(diario.trigger.timezone) == str(scheduler.timezone)
        assert str(mensal.trigger.timezone) == str(scheduler.timezone)
    finally:
        for job_id in ("beneficiamento_live_diario", "beneficiamento_mensal_rollup"):
            with contextlib.suppress(Exception):
                scheduler.remove_job(job_id)


def test_auto_retry_adia_oracle_quando_worker_tsplus_offline(
    db_session: Session, monkeypatch: Any
) -> None:
    auto = models.Automation(
        name="OBs Auto Retry Offline",
        script_path="./OBs Paradas Fase/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=2,
        cooldown_minutes=0,
    )
    db_session.add(auto)
    db_session.commit()
    falha = models.Execution(
        id="EXEC_AUTO_RETRY_OFF",
        automation_id=auto.id,
        status=EXECUTION_STATUS_ERROR,
        retry_count=0,
        max_retries=2,
        failure_reason="ORACLE_WORKER_OFFLINE",
        started_at=get_now_local() - timedelta(minutes=10),
        finished_at=get_now_local() - timedelta(minutes=9),
    )
    db_session.add(falha)
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)

    @contextlib.contextmanager
    def _fake_scope(factory: Any) -> Any:
        yield factory()

    monkeypatch.setattr(sr, "session_scope", _fake_scope)
    monkeypatch.setattr(sr, "_is_oracle_worker_online", lambda: False)
    wakeup = MagicMock()
    monkeypatch.setattr(sr, "trigger_worker_wakeup", wakeup)

    sr.auto_retry_transient_failures()

    db_session.refresh(falha)
    assert falha.status == EXECUTION_STATUS_ERROR
    wakeup.assert_not_called()


def test_recover_oracle_worker_outage_recupera_max_retries_zero_e_respeita_guardas(
    db_session: Session, monkeypatch: Any
) -> None:
    auto_ok = models.Automation(
        name="OBs Recovery OK",
        script_path="./OBs Paradas Fase/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=0,
    )
    auto_cron_perto = models.Automation(
        name="OBs Recovery Cron Perto",
        script_path="./Receitas Emitidas/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=0,
    )
    db_session.add_all([auto_ok, auto_cron_perto])
    db_session.commit()

    agora = get_now_local()
    e_ok = models.Execution(
        id="EXEC_REC_OK",
        automation_id=auto_ok.id,
        status=EXECUTION_STATUS_ERROR,
        retry_count=0,
        max_retries=0,
        failure_reason="ORACLE_WORKER_OFFLINE",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=30),
        finished_at=agora - timedelta(minutes=29),
    )
    e_perto = models.Execution(
        id="EXEC_REC_NEAR",
        automation_id=auto_cron_perto.id,
        status=EXECUTION_STATUS_ERROR,
        retry_count=0,
        max_retries=0,
        failure_reason="ORACLE_WORKER_OFFLINE",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=30),
        finished_at=agora - timedelta(minutes=29),
    )
    db_session.add_all([e_ok, e_perto])
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)

    @contextlib.contextmanager
    def _fake_scope(factory: Any) -> Any:
        yield factory()

    monkeypatch.setattr(sr, "session_scope", _fake_scope)
    monkeypatch.setattr(
        sr,
        "_get_oracle_queue_health",
        lambda **_kwargs: {"enabled": True, "alive": True, "oracle_ok": True},
    )

    monkeypatch.setattr(
        app_runtime.scheduler,
        "get_jobs",
        lambda: [
            _FakeJob(f"job_{auto_ok.id}_cron", agora + timedelta(hours=3)),
            _FakeJob(f"job_{auto_cron_perto.id}_cron", agora + timedelta(minutes=5)),
        ],
    )
    wakeup = MagicMock()
    monkeypatch.setattr(sr, "trigger_worker_wakeup", wakeup)

    count = sr.recover_oracle_worker_outage()
    assert count == 1
    db_session.refresh(e_ok)
    db_session.refresh(e_perto)
    assert e_ok.status == "REQUEUED"
    assert e_perto.status == EXECUTION_STATUS_ERROR
    wakeup.assert_called_once()

    # Segunda chamada com nova falha originada de ORACLE_WORKER_RECOVERY nao faz loop
    nova = (
        db_session.query(models.Execution)
        .filter(models.Execution.automation_id == auto_ok.id)
        .order_by(models.Execution.started_at.desc())
        .first()
    )
    assert nova is not None and nova.requested_by == "ORACLE_WORKER_RECOVERY"
    db_session.query(models.Execution).filter(models.Execution.id == nova.id).update(
        {
            "status": EXECUTION_STATUS_ERROR,
            "failure_reason": "ORACLE_WORKER_OFFLINE",
            "finished_at": get_now_local(),
        }
    )
    db_session.commit()
    assert sr.recover_oracle_worker_outage() == 0


def test_recover_oracle_worker_outage_fifo_uma_por_ciclo_sem_starvation(
    db_session: Session, monkeypatch: Any
) -> None:
    auto_recente = models.Automation(
        id=9901,
        name="OBs Recente ID Menor",
        script_path="./OBs Paradas Fase/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=0,
    )
    auto_antiga = models.Automation(
        id=9902,
        name="OBs Antiga ID Maior",
        script_path="./Receitas Emitidas/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=0,
    )
    db_session.add_all([auto_recente, auto_antiga])
    db_session.commit()

    agora = get_now_local()
    e_recente = models.Execution(
        id="EXEC_FIFO_REC",
        automation_id=auto_recente.id,
        status=EXECUTION_STATUS_ERROR,
        retry_count=0,
        max_retries=0,
        failure_reason="ORACLE_WORKER_OFFLINE",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=15),
        finished_at=agora - timedelta(minutes=10),
    )
    e_antiga = models.Execution(
        id="EXEC_FIFO_OLD",
        automation_id=auto_antiga.id,
        status=EXECUTION_STATUS_ERROR,
        retry_count=0,
        max_retries=0,
        failure_reason="ORACLE_WORKER_OFFLINE",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=50),
        finished_at=agora - timedelta(minutes=45),
    )
    db_session.add_all([e_recente, e_antiga])
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)

    @contextlib.contextmanager
    def _fake_scope(factory: Any) -> Any:
        yield factory()

    monkeypatch.setattr(sr, "session_scope", _fake_scope)
    monkeypatch.setattr(
        sr,
        "_get_oracle_queue_health",
        lambda **_kwargs: {"enabled": True, "alive": True, "oracle_ok": True},
    )
    monkeypatch.setattr(app_runtime.scheduler, "get_jobs", list)
    monkeypatch.setattr(sr, "trigger_worker_wakeup", MagicMock())

    spy_prepare = MagicMock(wraps=er.prepare_requeue)
    monkeypatch.setattr(sr, "prepare_requeue", spy_prepare)

    # Ciclo 1: recupera a mais antiga primeiro (FIFO finished_at.asc), para após 1 sem 409
    assert sr.recover_oracle_worker_outage(max_requeues=3) == 1
    assert spy_prepare.call_count == 1
    db_session.refresh(e_antiga)
    db_session.refresh(e_recente)
    assert e_antiga.status == "REQUEUED"
    assert e_recente.status == EXECUTION_STATUS_ERROR

    # Enquanto a execução reenfileirada está PENDING no grupo oracle, novo ciclo sai cedo
    spy_prepare.reset_mock()
    assert sr.recover_oracle_worker_outage() == 0
    spy_prepare.assert_not_called()

    # Após concluir a execução da auto_antiga, o próximo ciclo recupera auto_recente
    pendente_antiga = (
        db_session.query(models.Execution)
        .filter(
            models.Execution.automation_id == auto_antiga.id,
            models.Execution.status == EXECUTION_STATUS_PENDING,
        )
        .first()
    )
    assert pendente_antiga is not None
    db_session.query(models.Execution).filter(
        models.Execution.id == pendente_antiga.id
    ).update({"status": "SUCCESS", "finished_at": get_now_local()})
    db_session.commit()

    assert sr.recover_oracle_worker_outage() == 1
    db_session.refresh(e_recente)
    assert e_recente.status == "REQUEUED"


def test_recover_oracle_worker_outage_max_requeues_nao_positivo(
    monkeypatch: Any,
) -> None:
    health_spy = MagicMock()
    monkeypatch.setattr(sr, "_get_oracle_queue_health", health_spy)

    assert sr.recover_oracle_worker_outage(max_requeues=0) == 0
    assert sr.recover_oracle_worker_outage(max_requeues=-2) == 0
    health_spy.assert_not_called()


def test_recover_oracle_worker_outage_nao_recupera_max_runtime_exceeded(
    db_session: Session, monkeypatch: Any
) -> None:
    auto = models.Automation(
        id=9903,
        name="OBs Max Runtime",
        script_path="./OBs Paradas Fase/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=2,
    )
    db_session.add(auto)
    db_session.commit()

    agora = get_now_local()
    execucao = models.Execution(
        id="EXEC_MAX_RT",
        automation_id=auto.id,
        status="TIMEOUT",
        retry_count=0,
        max_retries=2,
        failure_reason="MAX_RUNTIME_EXCEEDED",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=30),
        finished_at=agora - timedelta(minutes=20),
    )
    db_session.add(execucao)
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)

    @contextlib.contextmanager
    def _fake_scope(factory: Any) -> Any:
        yield factory()

    monkeypatch.setattr(sr, "session_scope", _fake_scope)
    monkeypatch.setattr(
        sr,
        "_get_oracle_queue_health",
        lambda **_kwargs: {"enabled": True, "alive": True, "oracle_ok": True},
    )
    monkeypatch.setattr(app_runtime.scheduler, "get_jobs", list)

    assert sr.recover_oracle_worker_outage() == 0
    db_session.refresh(execucao)
    assert execucao.status == "TIMEOUT"


def test_recover_oracle_worker_outage_queue_timeout_nao_faz_bypass_de_max_retries_zero(
    db_session: Session, monkeypatch: Any
) -> None:
    auto_protegida = models.Automation(
        id=9904,
        name="OBs WhatsApp Sem Retry",
        script_path="./OBs Paradas Fase/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=0,
    )
    auto_com_retry = models.Automation(
        id=9905,
        name="OBs Com Retry",
        script_path="./Receitas Emitidas/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=1,
    )
    db_session.add_all([auto_protegida, auto_com_retry])
    db_session.commit()

    agora = get_now_local()
    exec_protegida = models.Execution(
        id="EXEC_QTO_NO_BYPASS",
        automation_id=auto_protegida.id,
        status="TIMEOUT",
        retry_count=0,
        max_retries=0,
        failure_reason="ORACLE_QUEUE_TIMEOUT",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=40),
        finished_at=agora - timedelta(minutes=35),
    )
    exec_com_retry = models.Execution(
        id="EXEC_QTO_RETRY",
        automation_id=auto_com_retry.id,
        status="TIMEOUT",
        retry_count=0,
        max_retries=1,
        failure_reason="ORACLE_QUEUE_TIMEOUT",
        requested_by="SCHEDULER",
        started_at=agora - timedelta(minutes=25),
        finished_at=agora - timedelta(minutes=20),
    )
    db_session.add_all([exec_protegida, exec_com_retry])
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)

    @contextlib.contextmanager
    def _fake_scope(factory: Any) -> Any:
        yield factory()

    monkeypatch.setattr(sr, "session_scope", _fake_scope)
    monkeypatch.setattr(
        sr,
        "_get_oracle_queue_health",
        lambda **_kwargs: {"enabled": True, "alive": True, "oracle_ok": True},
    )
    monkeypatch.setattr(app_runtime.scheduler, "get_jobs", list)
    monkeypatch.setattr(sr, "trigger_worker_wakeup", MagicMock())

    # Primeira candidata por FIFO é exec_protegida (max_retries=0): recusada;
    # loop continua e recupera exec_com_retry (max_retries=1).
    assert sr.recover_oracle_worker_outage() == 1
    db_session.refresh(exec_protegida)
    db_session.refresh(exec_com_retry)
    assert exec_protegida.status == "TIMEOUT"
    assert exec_com_retry.status == "REQUEUED"


def test_is_near_next_scheduled_run_suporta_next_run_timezone_aware(
    monkeypatch: Any,
) -> None:
    tz_sp = pytz.timezone("America/Sao_Paulo")
    tz_utc = pytz.utc
    now_naive_br = datetime(2026, 7, 8, 10, 0, 0)

    # Aware America/Sao_Paulo dentro da janela (10 min)
    monkeypatch.setattr(
        app_runtime.scheduler,
        "get_jobs",
        lambda: [
            _FakeJob("job_10_cron", tz_sp.localize(datetime(2026, 7, 8, 10, 10, 0)))
        ],
    )
    assert acessar_privado(sr, "_is_near_next_scheduled_run")(10, now_naive_br) is True

    # Aware America/Sao_Paulo fora da janela (30 min)
    monkeypatch.setattr(
        app_runtime.scheduler,
        "get_jobs",
        lambda: [
            _FakeJob("job_10_cron", tz_sp.localize(datetime(2026, 7, 8, 10, 30, 0)))
        ],
    )
    assert acessar_privado(sr, "_is_near_next_scheduled_run")(10, now_naive_br) is False

    # Aware UTC: 13:15 UTC == 10:15 BRT (15 min após 10:00 BRT -> dentro da janela)
    monkeypatch.setattr(
        app_runtime.scheduler,
        "get_jobs",
        lambda: [
            _FakeJob("job_10_cron", tz_utc.localize(datetime(2026, 7, 8, 13, 15, 0)))
        ],
    )
    assert acessar_privado(sr, "_is_near_next_scheduled_run")(10, now_naive_br) is True


def test_find_eligible_outage_execution_desempata_started_at_por_id_desc(
    db_session: Session, monkeypatch: Any
) -> None:
    auto = models.Automation(
        id=9906,
        name="OBs Desempate ID",
        script_path="./OBs Paradas Fase/run.ps1",
        enabled=True,
        queue_group="oracle",
    )
    db_session.add(auto)
    db_session.commit()

    agora = get_now_local()
    mesmo_inicio = agora - timedelta(minutes=25)
    e_a = models.Execution(
        id="EXEC_TIE_A",
        automation_id=auto.id,
        status=EXECUTION_STATUS_ERROR,
        failure_reason="ORACLE_WORKER_OFFLINE",
        requested_by="SCHEDULER",
        started_at=mesmo_inicio,
        finished_at=agora - timedelta(minutes=20),
    )
    e_z = models.Execution(
        id="EXEC_TIE_Z",
        automation_id=auto.id,
        status=EXECUTION_STATUS_ERROR,
        failure_reason="ORACLE_WORKER_OFFLINE",
        requested_by="SCHEDULER",
        started_at=mesmo_inicio,
        finished_at=agora - timedelta(minutes=19),
    )
    db_session.add_all([e_a, e_z])
    db_session.commit()
    monkeypatch.setattr(app_runtime.scheduler, "get_jobs", list)

    escolhida = acessar_privado(sr, "_find_eligible_outage_execution")(
        db_session, auto, agora - timedelta(hours=2), agora
    )
    assert escolhida is not None
    assert escolhida.id == "EXEC_TIE_Z"


# ---------------------------------------------------------------------------
# Auto-retry com Worker Oracle offline (D1) e trava entre os jobs de requeue (D2)
# ---------------------------------------------------------------------------


def test_auto_retry_oracle_offline_nao_deixa_erros_antigas_do_grupo_bloquear_fila(
    db_session: Session, monkeypatch: Any
) -> None:
    oracle = models.Automation(
        name="Oracle Com Muitas Falhas Antigas",
        script_path="./OBs/run.ps1",
        enabled=True,
        queue_group="oracle",
        max_retries=2,
        cooldown_minutes=0,
    )
    comum = models.Automation(
        name="Comum Com Falha Nova",
        script_path="./Outra/run.ps1",
        enabled=True,
        queue_group="hub-global",
        max_retries=2,
        cooldown_minutes=0,
    )
    db_session.add_all([oracle, comum])
    db_session.commit()
    # 25 falhas antigas do grupo oracle: mais que a janela de 20 candidatos.
    for i in range(25):
        _create_error_execution(
            db_session,
            automation_id=int(oracle.id),
            exec_id=f"ORA_ANTIGA_{i:02d}",
            retries=(0, 2),
            minutes_ago_finished=1000.0 + i,
        )
    _create_error_execution(
        db_session,
        automation_id=int(comum.id),
        exec_id="COMUM_NOVA",
        retries=(0, 2),
        minutes_ago_finished=5.0,
    )

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)

    @contextlib.contextmanager
    def _fake_scope(factory: Any) -> Any:
        yield factory()

    monkeypatch.setattr(sr, "session_scope", _fake_scope)
    monkeypatch.setattr(sr, "_is_oracle_worker_online", lambda: False)
    wakeup = MagicMock()
    monkeypatch.setattr(sr, "trigger_worker_wakeup", wakeup)

    sr.auto_retry_transient_failures()

    novas_comum = (
        db_session.query(models.Execution)
        .filter(
            models.Execution.automation_id == comum.id,
            models.Execution.status == EXECUTION_STATUS_PENDING,
        )
        .all()
    )
    assert len(novas_comum) == 1
    assert novas_comum[0].requested_by == "AUTO_RETRY"
    pendentes_oracle = (
        db_session.query(models.Execution)
        .filter(
            models.Execution.automation_id == oracle.id,
            models.Execution.status == EXECUTION_STATUS_PENDING,
        )
        .count()
    )
    assert pendentes_oracle == 0
    antigas_intactas = (
        db_session.query(models.Execution)
        .filter(
            models.Execution.automation_id == oracle.id,
            models.Execution.status == EXECUTION_STATUS_ERROR,
        )
        .count()
    )
    assert antigas_intactas == 25
    wakeup.assert_called_once()


def test_requeue_jobs_lock_e_threading_lock() -> None:
    assert isinstance(acessar_privado(sr, "_REQUEUE_JOBS_LOCK"), type(threading.Lock()))


def _assert_job_espera_trava_de_requeue(
    db_session: Session,
    monkeypatch: Any,
    chamada: Callable[[], Any],
) -> None:
    """Com a trava tomada por outra thread, o job não entra na seção de banco."""
    entradas: list[str] = []

    @contextlib.contextmanager
    def _scope_espiao(factory: Any) -> Any:
        entradas.append("scope")
        yield factory()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(sr, "session_scope", _scope_espiao)
    monkeypatch.setattr(sr, "_is_oracle_worker_online", lambda: True)
    monkeypatch.setattr(
        sr,
        "_get_oracle_queue_health",
        lambda **_kwargs: {"enabled": True, "alive": True, "oracle_ok": True},
    )
    monkeypatch.setattr(sr, "trigger_worker_wakeup", MagicMock())

    with acessar_privado(sr, "_REQUEUE_JOBS_LOCK"):
        job = threading.Thread(target=chamada, daemon=True)
        job.start()
        job.join(timeout=0.3)
        # Determinístico: sem a trava, o job terminaria; com ela, está bloqueado.
        assert job.is_alive()
        assert not entradas

    job.join(timeout=5)
    assert not job.is_alive()
    assert entradas == ["scope"]


def test_auto_retry_espera_trava_de_requeue(
    db_session: Session, monkeypatch: Any
) -> None:
    _assert_job_espera_trava_de_requeue(
        db_session, monkeypatch, sr.auto_retry_transient_failures
    )


def test_recover_oracle_outage_espera_trava_de_requeue(
    db_session: Session, monkeypatch: Any
) -> None:
    _assert_job_espera_trava_de_requeue(
        db_session, monkeypatch, sr.recover_oracle_worker_outage
    )


def test_recover_oracle_worker_outage_decide_com_dado_fresco(
    monkeypatch: Any,
) -> None:
    spy = MagicMock(return_value={"enabled": True, "alive": False})
    monkeypatch.setattr(sr, "_get_oracle_queue_health", spy)

    assert sr.recover_oracle_worker_outage() == 0
    spy.assert_called_once_with(use_cache=False)

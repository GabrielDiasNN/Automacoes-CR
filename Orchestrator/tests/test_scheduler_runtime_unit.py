# pylint: disable=protected-access
"""Testes unitários de app/services/scheduler_runtime.py e app/runtime.py (wakeup)."""

import json
import subprocess
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from app import models
from app import runtime as app_runtime
from app.services import scheduler_runtime as sr


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


def test_run_file_cleanup_sucesso_invoca_pwsh() -> None:
    with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        sr.run_file_cleanup()

    args, kwargs = mock_run.call_args
    assert args[0][0] == "pwsh.exe"
    assert kwargs.get("check") is True


def test_run_file_cleanup_falha_nao_propaga_excecao() -> None:
    with patch("app.services.scheduler_runtime.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "pwsh.exe")
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
    monkeypatch.setattr(app_runtime, "_event_loop", None)
    app_runtime.task_queued_event.clear()

    app_runtime.trigger_worker_wakeup()  # nao deve lancar excecao

    assert app_runtime.task_queued_event.is_set() is True
    app_runtime.task_queued_event.clear()


def test_wakeup_com_loop_fechado_usa_fallback_direto(monkeypatch: Any) -> None:
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = True
    monkeypatch.setattr(app_runtime, "_event_loop", fake_loop)
    app_runtime.task_queued_event.clear()

    app_runtime.trigger_worker_wakeup()

    fake_loop.call_soon_threadsafe.assert_not_called()
    assert app_runtime.task_queued_event.is_set() is True
    app_runtime.task_queued_event.clear()


def test_register_event_loop_atualiza_o_loop_global(monkeypatch: Any) -> None:
    monkeypatch.setattr(app_runtime, "_event_loop", None)
    fake_loop = MagicMock()

    app_runtime.register_event_loop(fake_loop)

    assert app_runtime._event_loop is fake_loop

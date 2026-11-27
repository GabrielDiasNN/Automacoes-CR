"""Testes unitários da integração do worker/diagnóstico/health com a fila Oracle."""

import contextlib
import itertools
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Any
from unittest.mock import MagicMock, patch

import psutil
import pytest
import worker
from app.constants import EXECUTION_STATUS_PENDING, ORCHESTRATOR_SCHEMA_VERSION
from app.schemas import WorkerStatus
from app.services import system_diagnostics, system_runtime
from app.services.diagnostic_checks import check_oracle_queue_worker_health
from app.services.system_diagnostics import _build_oracle_queue_worker_check
from carregadores_modulos import acessar_privado
from sqlalchemy.orm import Session


@dataclass
class _FakeAutomation:
    test_mode: bool = False
    queue_group: str | None = None


@dataclass
class _FakeExecution:
    queue_group: str | None
    automation: _FakeAutomation


def _execucao(
    *, auto_queue_group: str | None, exec_queue_group: str | None
) -> _FakeExecution:
    """Execução cujo queue_group congelado pode divergir do atual da automação."""
    return _FakeExecution(
        queue_group=exec_queue_group,
        automation=_FakeAutomation(queue_group=auto_queue_group),
    )


def _build_subprocess_env(
    db_exec: _FakeExecution, exec_id: str, max_runtime: int
) -> dict[str, str]:
    construir = acessar_privado(worker, "_build_subprocess_env")
    env: dict[str, str] = construir(db_exec, exec_id, max_runtime=max_runtime)
    return env


# ---------------------------------------------------------------------------
# worker._build_subprocess_env (queue_group + ORACLE_QUEUE_DEADLINE_EPOCH)
# ---------------------------------------------------------------------------


def test_build_subprocess_env_prioriza_automation_queue_group_oracle(
    monkeypatch: Any,
) -> None:
    # Sem TIMEOUT no ambiente pai: o worker não injeta cap nenhum.
    monkeypatch.delenv("ORACLE_QUEUE_TIMEOUT_SECONDS", raising=False)
    exec_oracle_na_auto = _execucao(
        auto_queue_group="oracle", exec_queue_group="hub-global"
    )
    antes = time.time()
    env = _build_subprocess_env(exec_oracle_na_auto, "EXEC-ORA-1", max_runtime=10)

    assert "ORACLE_QUEUE_DEADLINE_EPOCH" in env
    deadline = float(env["ORACLE_QUEUE_DEADLINE_EPOCH"])
    # max_runtime=10 -> budget = 10*60 - 90 = 510s
    assert antes + 505 <= deadline <= time.time() + 515
    assert "ORACLE_QUEUE_TIMEOUT_SECONDS" not in env


def test_build_subprocess_env_ignora_queue_group_congelado_quando_automation_mudou(
    monkeypatch: Any,
) -> None:
    # A variável está na allowlist de subprocess_env: sem limpar o ambiente pai, o
    # valor do .env local (carregado no import do worker) chega ao subprocesso.
    monkeypatch.delenv("ORACLE_QUEUE_TIMEOUT_SECONDS", raising=False)
    exec_movida = _execucao(auto_queue_group="hub-global", exec_queue_group="oracle")
    env = _build_subprocess_env(exec_movida, "EXEC-MOV-1", max_runtime=10)

    assert "ORACLE_QUEUE_DEADLINE_EPOCH" not in env
    assert "ORACLE_QUEUE_TIMEOUT_SECONDS" not in env


def test_build_subprocess_env_usa_exec_queue_group_como_fallback(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_TIMEOUT_SECONDS", "600")
    exec_fallback = _execucao(auto_queue_group=None, exec_queue_group="oracle")
    env = _build_subprocess_env(exec_fallback, "EXEC-FB-1", max_runtime=5)

    # O prazo global é a única fonte do limite. O TIMEOUT não é injetado: o valor
    # que chega ao subprocesso é o do ambiente pai (allowlist de subprocess_env),
    # e não o cap de 180 s que o worker calculava antes.
    assert "ORACLE_QUEUE_DEADLINE_EPOCH" in env
    assert env["ORACLE_QUEUE_TIMEOUT_SECONDS"] == "600"


def test_build_subprocess_env_nao_herda_deadline_epoch_do_pai_e_respeita_bordas(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", "1000.0")

    exec_nao_oracle = _execucao(
        auto_queue_group="hub-global", exec_queue_group="hub-global"
    )
    exec_nao_oracle.automation.test_mode = True
    env_nao_oracle = _build_subprocess_env(exec_nao_oracle, "EXEC-HUB-1", max_runtime=10)
    assert "ORACLE_QUEUE_DEADLINE_EPOCH" not in env_nao_oracle
    assert env_nao_oracle["ORCHESTRATOR_TEST_MODE"] == "true"
    assert env_nao_oracle["EXEC_ID"] == "EXEC-HUB-1"
    assert env_nao_oracle["CORRELATION_ID"] == "EXEC-HUB-1"

    exec_sem_prazo = _execucao(auto_queue_group="oracle", exec_queue_group="oracle")
    env_sem_prazo = _build_subprocess_env(exec_sem_prazo, "EXEC-ORA-0", max_runtime=0)
    assert "ORACLE_QUEUE_DEADLINE_EPOCH" not in env_sem_prazo

    antes = time.time()
    env_minimo = _build_subprocess_env(exec_sem_prazo, "EXEC-ORA-1M", max_runtime=1)
    deadline = float(env_minimo["ORACLE_QUEUE_DEADLINE_EPOCH"])
    # max_runtime=1 -> max(30, 60 - 90) == 30s (não herda 1000.0 do pai)
    assert antes + 25 <= deadline <= time.time() + 35


# ---------------------------------------------------------------------------
# worker._cleanup_oracle_queue_requests nos caminhos de aborto
# ---------------------------------------------------------------------------


def test_monitor_process_shutdown_chama_cleanup_oracle_queue_requests(
    monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", MagicMock())

    @contextlib.contextmanager
    def _fake_scope(_factory: Any) -> Any:
        yield MagicMock()

    monkeypatch.setattr(worker, "session_scope", _fake_scope)

    process = MagicMock()
    process.pid = 7777
    process.poll.return_value = None  # vivo no momento do shutdown

    task_ctx = {
        "exec_id": "EXEC_SHUT_CLEAN",
        "task_start": None,
        "task_start_ts": time.time(),
        "task_start_monotonic": time.monotonic(),
        "max_runtime": 10,
        "robot_dir": "C:\\robot",
        "reader_thread": None,
    }

    worker.shutdown_event.set()
    try:
        with (
            patch("worker._force_kill") as mock_kill,
            patch("worker._cleanup_oracle_queue_requests") as mock_cleanup,
            patch("worker.finalize_reboot_interrupted_task"),
            patch("worker.broadcast_log"),
            patch("worker.broadcast_event"),
        ):
            resultado = acessar_privado(worker, "_monitor_process")(
                process, Queue(), [], task_ctx
            )
    finally:
        worker.shutdown_event.clear()

    assert resultado is False
    mock_kill.assert_called_once_with(7777)
    mock_cleanup.assert_called_once_with("EXEC_SHUT_CLEAN")


def test_monitor_process_encerrado_pelo_banco_chama_cleanup_oracle(
    reset_worker_globals: None,
) -> None:
    del reset_worker_globals
    process = MagicMock()
    process.poll.return_value = None
    task_ctx = {
        "exec_id": "EXEC_DB_STOP",
        "task_start": None,
        "task_start_ts": time.time(),
        "task_start_monotonic": time.monotonic(),
        "max_runtime": 10,
        "robot_dir": "C:\\robot",
        "reader_thread": None,
    }

    with (
        patch("worker._encerrada_pelo_banco", return_value=True) as mock_db_check,
        patch("worker._cleanup_oracle_queue_requests") as mock_cleanup,
    ):
        resultado = acessar_privado(worker, "_monitor_process")(
            process, Queue(), [], task_ctx
        )

    assert resultado is False
    mock_db_check.assert_called_once()
    mock_cleanup.assert_called_once_with("EXEC_DB_STOP")


def test_cleanup_oracle_queue_requests_corpo_real(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cleanup_fn = acessar_privado(worker, "_cleanup_oracle_queue_requests")

    # Fora do modo queue: não tenta carregar o módulo da fila.
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    with patch("worker.load_oracle_queue_module") as mock_load:
        cleanup_fn("EXEC-THICK")
    mock_load.assert_not_called()

    # Em modo queue com arquivo real órfão na pasta da fila: remove req_*.sql do exec_id.
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    req_alvo = tmp_path / "req_alvo.sql"
    req_outro = tmp_path / "req_outro.sql"
    req_alvo.write_text("--#meta:exec_id=EXEC-REAL-1\nSELECT 1 FROM dual\n", encoding="cp1252")
    req_outro.write_text("--#meta:exec_id=EXEC-OUTRO\nSELECT 1 FROM dual\n", encoding="cp1252")
    fake_mod = MagicMock()
    fake_mod.cleanup_requests_for_exec_id.side_effect = (
        lambda eid: 1 if eid == "EXEC-REAL-1" else 0
    )
    with (
        patch("worker.load_oracle_queue_module", return_value=fake_mod),
        caplog.at_level(logging.INFO, logger="worker"),
    ):
        cleanup_fn("EXEC-REAL-1")
    fake_mod.cleanup_requests_for_exec_id.assert_called_once_with("EXEC-REAL-1")
    assert any("EXEC-REAL-1" in rec.message for rec in caplog.records)

    # Erros esperados de carga/SMB/host UNC são absorvidos sem propagar.
    for erro in (ImportError("sem mod"), OSError("smb down"), ValueError("unc invalido")):
        with patch("worker.load_oracle_queue_module", side_effect=erro):
            cleanup_fn("EXEC-ERR")

    # Bug inesperado continua visível.
    with (
        patch("worker.load_oracle_queue_module", side_effect=RuntimeError("bug")),
        pytest.raises(RuntimeError, match="bug"),
    ):
        cleanup_fn("EXEC-BUG")


def _patch_worker_main_loop_base(
    monkeypatch: pytest.MonkeyPatch, fake_db: Any
) -> None:
    @contextlib.contextmanager
    def _fake_scope(_factory: Any) -> Any:
        yield fake_db

    monkeypatch.setattr(worker, "SessionLocal", MagicMock())
    monkeypatch.setattr(worker, "session_scope", _fake_scope)
    monkeypatch.setattr(worker, "heartbeat_loop", lambda: None)
    monkeypatch.setattr(worker, "log_flusher_loop", lambda: None)
    monkeypatch.setattr(worker, "wakeup_listener_loop", lambda: None)
    monkeypatch.setattr(worker, "POLL_INTERVAL", 0.02)
    monkeypatch.setattr(worker, "MAX_POLL_INTERVAL", 0.05)


def test_main_loop_shutdown_gracioso_executa_monitor_antes_de_terminate(
    monkeypatch: pytest.MonkeyPatch, reset_worker_globals: None
) -> None:
    """main_loop deve esperar active_futures antes de chamar _terminate_active_processes."""
    del reset_worker_globals
    fake_auto = MagicMock(script_path="./run.ps1", max_runtime_minutes=10)
    fake_auto.name = "Oracle Test"
    fake_exec = MagicMock(automation_id=1, status=EXECUTION_STATUS_PENDING, automation=fake_auto)
    fake_db = MagicMock()
    # _despachar_reivindicada consulta Execution e Automation; depois _iniciar_tarefa consulta Execution
    fake_db.query.return_value.filter.return_value.first.side_effect = [
        fake_exec,
        fake_auto,
        fake_exec,
    ]
    _patch_worker_main_loop_base(monkeypatch, fake_db)

    ordem_eventos: list[str] = []
    process = MagicMock(pid=4321)
    process.stdout.readline.return_value = ""
    process_vivo = [True]
    process.poll.side_effect = lambda: None if process_vivo[0] else -1

    def _fake_kill(pid: int) -> None:
        ordem_eventos.append(f"kill:{pid}")
        process_vivo[0] = False

    def _fake_start_process(*_args: Any, **_kw: Any) -> Any:
        with worker.stats["lock"]:
            worker.stats["active_processes"]["EXEC_GRACE_1"] = process
        worker.shutdown_event.set()
        return process

    with (
        patch(
            "worker.claim_next_task",
            side_effect=itertools.chain(["EXEC_GRACE_1"], itertools.repeat(None)),
        ),
        patch("worker.resolve_script_path", return_value="C:\\robot\\run.ps1"),
        patch("worker.snapshot_artifact_files", return_value=set()),
        patch("worker._start_process", side_effect=_fake_start_process),
        patch("worker._force_kill", side_effect=_fake_kill),
        patch(
            "worker._cleanup_oracle_queue_requests",
            side_effect=lambda eid: ordem_eventos.append(f"cleanup:{eid}"),
        ),
        patch(
            "worker.finalize_reboot_interrupted_task",
            side_effect=lambda _db, eid, *_a: ordem_eventos.append(
                f"finalize_reboot:{eid}"
            ),
        ),
        patch("worker._terminate_active_processes") as mock_terminate_fallback,
        patch("worker.broadcast_log"),
        patch("worker.broadcast_event"),
        patch("worker.notifications.shutdown_notification_executor"),
    ):
        worker.main_loop()

    mock_terminate_fallback.assert_not_called()
    assert ordem_eventos == [
        "kill:4321",
        "cleanup:EXEC_GRACE_1",
        "finalize_reboot:EXEC_GRACE_1",
    ]


def test_main_loop_shutdown_fallback_termina_e_limpa_quando_future_nao_encerra(
    monkeypatch: pytest.MonkeyPatch, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    fake_auto = MagicMock(script_path="./run.ps1", max_runtime_minutes=10)
    fake_auto.name = "Oracle Stuck"
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.side_effect = [
        MagicMock(automation_id=1),
        fake_auto,
    ]
    _patch_worker_main_loop_base(monkeypatch, fake_db)
    monkeypatch.setattr(worker, "SHUTDOWN_GRACE_SECONDS", 0.05)

    liberar_stuck = threading.Event()
    process_stuck = MagicMock(pid=9991)
    claim_calls = [0]

    def _claim_stuck(*_args: Any, **_kwargs: Any) -> str | None:
        claim_calls[0] += 1
        return "EXEC_STUCK" if claim_calls[0] == 1 else None

    def _stuck_task(exec_id: str, *_args: Any) -> None:
        with worker.stats["lock"]:
            worker.stats["active_processes"][exec_id] = process_stuck
        worker.shutdown_event.set()
        liberar_stuck.wait(timeout=2.0)

    try:
        with (
            patch("worker.claim_next_task", side_effect=_claim_stuck),
            patch("worker.resolve_script_path", return_value="C:\\robot\\run.ps1"),
            patch("worker.run_task", side_effect=_stuck_task),
            patch("worker._force_kill") as mock_kill,
            patch("worker._cleanup_oracle_queue_requests") as mock_cleanup,
            patch("worker.notifications.shutdown_notification_executor"),
        ):
            worker.main_loop()
    finally:
        liberar_stuck.set()

    mock_kill.assert_called_once_with(9991)
    mock_cleanup.assert_called_once_with("EXEC_STUCK")


def test_run_task_finally_orfao_chama_cleanup_oracle_queue_requests(
    monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals

    fake_auto = _FakeAutomation(test_mode=False, queue_group="oracle")
    fake_exec = MagicMock()
    fake_exec.status = EXECUTION_STATUS_PENDING
    fake_exec.automation_id = 1
    fake_exec.automation = fake_auto

    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = fake_exec

    @contextlib.contextmanager
    def _fake_scope(_factory: Any) -> Any:
        yield fake_db

    monkeypatch.setattr(worker, "SessionLocal", MagicMock())
    monkeypatch.setattr(worker, "session_scope", _fake_scope)

    orfao = MagicMock()
    orfao.pid = 8888
    orfao.poll.return_value = None  # continua vivo quando _monitor_process falha

    def _fake_start_process(_db_exec: Any, _path: str, exec_id: str, **_kw: Any) -> Any:
        with worker.stats["lock"]:
            worker.stats["active_processes"][exec_id] = orfao
        return orfao

    with (
        patch("worker.snapshot_artifact_files", return_value=set()),
        patch("worker._start_process", side_effect=_fake_start_process),
        patch("worker.enqueue_output"),
        patch("worker._monitor_process", side_effect=RuntimeError("boom sqlite")),
        patch("worker.apply_internal_worker_error"),
        patch("worker._force_kill") as mock_kill,
        patch("worker._cleanup_oracle_queue_requests") as mock_cleanup,
        patch("worker.broadcast_event"),
    ):
        worker.run_task("EXEC_ORFAO_CLEAN", "C:\\robot\\run.ps1", max_runtime=10)

    mock_kill.assert_called_once_with(8888)
    mock_cleanup.assert_called_once_with("EXEC_ORFAO_CLEAN")


# ---------------------------------------------------------------------------
# system_diagnostics / diagnostic_checks (age=n/a)
# ---------------------------------------------------------------------------


def test_oracle_queue_worker_check_formata_age_none_como_na() -> None:
    check_none = _build_oracle_queue_worker_check(
        {"enabled": True, "reachable": True, "alive": False, "age_seconds": None}
    )
    assert check_none["status"] == "error"
    assert check_none["value"] == "v?;age=n/a"
    assert "Nones" not in check_none["value"]

    check_com_idade = _build_oracle_queue_worker_check(
        {
            "enabled": True,
            "reachable": True,
            "alive": True,
            "oracle_ok": True,
            "version": "1.2",
            "age_seconds": 15,
        }
    )
    assert check_com_idade["status"] == "ok"
    assert check_com_idade["value"] == "v1.2;age=15s"


def test_check_oracle_queue_worker_health_com_age_none_sem_nones() -> None:
    findings = check_oracle_queue_worker_health(
        {
            "enabled": True,
            "reachable": True,
            "alive": False,
            "age_seconds": None,
            "machine": "APL_SGT",
        }
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "ERROR"
    assert "Nones" not in findings[0]["message"]
    assert "None" not in findings[0]["message"]
    assert "APL_SGT" in findings[0]["action_hint"]
    assert "ORACLE_QUEUE_DIR" in findings[0]["action_hint"]


@pytest.mark.parametrize(
    "oracle_q",
    [
        {"enabled": True, "reachable": False, "alive": False},
        {"enabled": True, "reachable": True, "alive": False, "machine": "TSPLUS"},
        {
            "enabled": True,
            "reachable": True,
            "alive": True,
            "oracle_ok": False,
            "machine": "TSPLUS",
        },
    ],
)
def test_check_oracle_queue_worker_health_sem_ips_hardcoded(
    oracle_q: dict[str, Any],
) -> None:
    findings = check_oracle_queue_worker_health(oracle_q)
    assert len(findings) == 1
    texto = f"{findings[0]['message']} {findings[0]['action_hint']}"
    assert "10.62.0.3" not in texto
    assert "10.62.0.2" not in texto
    assert "ORACLE_QUEUE_DIR" in findings[0]["action_hint"]


# ---------------------------------------------------------------------------
# Alinhamento /health/full, /diagnostics e /baseline com worker TSplus degradado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "oracle_snapshot",
    [
        {"enabled": True, "reachable": False, "alive": False, "oracle_ok": None},
        {"enabled": True, "reachable": True, "alive": False, "oracle_ok": None},
        {"enabled": True, "reachable": True, "alive": True, "oracle_ok": False},
    ],
)
def test_health_diagnostics_e_baseline_alinhados_quando_tsplus_degradado(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    oracle_snapshot: dict[str, Any],
) -> None:
    worker_vivo = WorkerStatus(
        is_alive=True,
        pid=100,
        instance_id="w-1",
        host="host",
        tasks_completed=0,
        tasks_failed=0,
        active_tasks=0,
        version="1.0.0",
    )
    fake_scheduler = MagicMock(running=True)
    fake_scheduler.get_jobs.return_value = [MagicMock(id="auto_1", next_run_time=None)]

    monkeypatch.setattr(system_runtime, "scheduler", fake_scheduler)
    monkeypatch.setattr(system_runtime, "get_db_size_mb", lambda: 1.0)
    monkeypatch.setattr(system_runtime, "get_wal_size_mb", lambda: 0.1)
    monkeypatch.setattr(psutil, "cpu_percent", lambda: 5.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MagicMock(percent=40.0))
    monkeypatch.setattr(
        system_runtime, "collect_oracle_queue_health", lambda: dict(oracle_snapshot)
    )

    monkeypatch.setattr(
        system_diagnostics,
        "validate_database_schema",
        lambda: {"valid": True, "missing_tables": []},
    )
    monkeypatch.setattr(
        system_diagnostics,
        "get_schema_version",
        lambda: ORCHESTRATOR_SCHEMA_VERSION,
    )
    monkeypatch.setattr(system_diagnostics, "get_db_size_mb", lambda: 1.0)
    monkeypatch.setattr(
        system_diagnostics, "collect_scheduler_inconsistencies", lambda _db, _s: []
    )
    monkeypatch.setattr(
        system_diagnostics,
        "collect_oracle_queue_health",
        lambda: dict(oracle_snapshot),
    )

    health = system_runtime.build_health_payload(db_session, worker_vivo)
    diag = system_diagnostics.build_diagnostics_payload(
        db_session,
        fake_scheduler,
        lambda _db: worker_vivo,
        wal_size_fn=lambda: 0.1,
        include_history=False,
    )
    baseline = diag["operational_baseline"]

    assert health.status == "degraded"
    assert diag["overall_status"] == "degraded"
    assert baseline["status"] == "attention"
    assert diag["recovery"]["recommended_action"] is None
    assert baseline["recommended_action"] is None
    assert diag["slo_breaches"]["oracle_queue_degraded"] is True
    metric_oracle = next(
        m for m in baseline["metrics"] if m["code"] == "oracle_queue_worker"
    )
    assert metric_oracle["status"] == "attention"
    assert metric_oracle["action_code"] is None


# ---------------------------------------------------------------------------
# system_runtime.build_health_payload
# ---------------------------------------------------------------------------


def _fake_healthy_db() -> Any:
    query_chain = MagicMock()
    query_chain.filter.return_value.count.return_value = 0
    db = MagicMock()
    db.execute.return_value = 1
    db.query.return_value = query_chain
    return db


@pytest.mark.parametrize(
    "oracle_snapshot",
    [
        {"enabled": True, "reachable": False, "alive": False},
        {"enabled": True, "reachable": True, "alive": False, "oracle_ok": True},
        {"enabled": True, "reachable": True, "alive": True, "oracle_ok": False},
    ],
)
def test_build_health_payload_degrada_quando_oracle_queue_worker_offline(
    monkeypatch: Any, oracle_snapshot: dict[str, Any]
) -> None:
    monkeypatch.setattr(system_runtime, "scheduler", MagicMock(running=True))
    monkeypatch.setattr(
        system_runtime, "collect_oracle_queue_health", lambda: oracle_snapshot
    )
    monkeypatch.setattr(system_runtime, "get_db_size_mb", lambda: 1.0)
    monkeypatch.setattr(system_runtime, "get_wal_size_mb", lambda: 0.1)
    monkeypatch.setattr(psutil, "cpu_percent", lambda: 5.0)
    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: MagicMock(percent=40.0),
    )

    payload = system_runtime.build_health_payload(
        _fake_healthy_db(), WorkerStatus(is_alive=True)
    )
    assert payload.status == "degraded"
    assert payload.oracle_queue_worker == oracle_snapshot


def test_build_health_payload_mantem_healthy_e_unhealthy_coerentes(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(system_runtime, "get_db_size_mb", lambda: 1.0)
    monkeypatch.setattr(system_runtime, "get_wal_size_mb", lambda: 0.1)
    monkeypatch.setattr(psutil, "cpu_percent", lambda: 5.0)
    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: MagicMock(percent=40.0),
    )

    # Saudável quando worker Oracle ativo e conectado
    monkeypatch.setattr(system_runtime, "scheduler", MagicMock(running=True))
    monkeypatch.setattr(
        system_runtime,
        "collect_oracle_queue_health",
        lambda: {"enabled": True, "reachable": True, "alive": True, "oracle_ok": True},
    )
    healthy = system_runtime.build_health_payload(
        _fake_healthy_db(), WorkerStatus(is_alive=True)
    )
    assert healthy.status == "healthy"

    # Unhealthy quando scheduler parado mesmo com oracle_queue_worker offline
    monkeypatch.setattr(system_runtime, "scheduler", MagicMock(running=False))
    monkeypatch.setattr(
        system_runtime,
        "collect_oracle_queue_health",
        lambda: {"enabled": True, "reachable": False, "alive": False},
    )
    unhealthy = system_runtime.build_health_payload(
        _fake_healthy_db(), WorkerStatus(is_alive=True)
    )
    assert unhealthy.status == "unhealthy"

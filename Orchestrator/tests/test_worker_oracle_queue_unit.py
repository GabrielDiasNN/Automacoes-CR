"""Testes unitários da integração do worker/diagnóstico/health com a fila Oracle."""

import contextlib
import time
from dataclasses import dataclass
from queue import Queue
from typing import Any
from unittest.mock import MagicMock, patch

import psutil
import pytest
import worker
from app.constants import EXECUTION_STATUS_PENDING
from app.schemas import WorkerStatus
from app.services import system_runtime
from app.services.diagnostic_checks import check_oracle_queue_worker_health
from app.services.system_diagnostics import _build_oracle_queue_worker_check
from carregadores_modulos import acessar_privado


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


def test_build_subprocess_env_ignora_queue_group_congelado_quando_automation_mudou() -> (
    None
):
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
        {"enabled": True, "reachable": True, "alive": False, "age_seconds": None}
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "ERROR"
    assert "Nones" not in findings[0]["message"]
    assert "None" not in findings[0]["message"]


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

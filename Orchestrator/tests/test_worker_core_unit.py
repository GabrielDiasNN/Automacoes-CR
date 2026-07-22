# pylint: disable=protected-access
"""Testes unitários dos utilitários internos do worker.py (kill, env, caps de log, finalize)."""

import json
import os
import subprocess
import threading
import time
from queue import Queue
from typing import Any
from unittest.mock import MagicMock, patch

import worker
from app import models
from app.timezone import get_now_local


class _FakeAutomation:  # pylint: disable=too-few-public-methods
    def __init__(self, test_mode: bool) -> None:
        self.test_mode = test_mode


class _FakeExecution:  # pylint: disable=too-few-public-methods
    def __init__(self, test_mode: bool) -> None:
        self.automation = _FakeAutomation(test_mode)


# ---------------------------------------------------------------------------
# _force_kill
# ---------------------------------------------------------------------------


def test_force_kill_chama_taskkill_com_args_corretos() -> None:
    with patch("worker.subprocess.run") as mock_run:
        worker._force_kill(1234)

    mock_run.assert_called_once_with(
        ["taskkill", "/F", "/T", "/PID", "1234"],
        capture_output=True,
        check=False,
        timeout=15,
    )


def test_force_kill_timeout_expired_loga_warning() -> None:
    with (
        patch("worker.subprocess.run") as mock_run,
        patch("worker.logger.warning") as mock_warning,
    ):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="taskkill", timeout=15)
        worker._force_kill(1234)

    mock_warning.assert_called_once()


# ---------------------------------------------------------------------------
# _build_subprocess_env
# ---------------------------------------------------------------------------


def test_subprocess_env_nao_contem_oracle_readonly_password(monkeypatch: Any) -> None:
    monkeypatch.setenv("ORACLE_READONLY_PASSWORD", "super-secret")
    env = worker._build_subprocess_env(_FakeExecution(test_mode=False), "EXEC-1")
    assert "ORACLE_READONLY_PASSWORD" not in env


def test_subprocess_env_contem_apenas_allowed_keys(monkeypatch: Any) -> None:
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.setenv("SOME_RANDOM_SECRET", "leak-me-not")
    env = worker._build_subprocess_env(_FakeExecution(test_mode=False), "EXEC-1")
    extras = {"ORCHESTRATOR_TEST_MODE", "EXEC_ID", "CORRELATION_ID"}
    assert (set(env.keys()) - extras).issubset(worker._ALLOWED_ENV_KEYS)
    assert "SOME_RANDOM_SECRET" not in env


def test_subprocess_env_test_mode_propagado() -> None:
    env_true = worker._build_subprocess_env(_FakeExecution(test_mode=True), "EXEC-1")
    env_false = worker._build_subprocess_env(_FakeExecution(test_mode=False), "EXEC-1")
    assert env_true["ORCHESTRATOR_TEST_MODE"] == "true"
    assert env_false["ORCHESTRATOR_TEST_MODE"] == "false"


def test_subprocess_env_exec_id_e_correlation_id_iguais() -> None:
    env = worker._build_subprocess_env(_FakeExecution(test_mode=False), "EXEC-99")
    assert env["EXEC_ID"] == "EXEC-99"
    assert env["CORRELATION_ID"] == "EXEC-99"


# ---------------------------------------------------------------------------
# _drain_process_output caps
# ---------------------------------------------------------------------------


def test_drain_cap_linhas_para_em_max_log_lines() -> None:
    queue: "Queue[str]" = Queue()
    for _ in range(5):
        queue.put("linha\n")
    logs: list[str] = []

    with patch("worker.MAX_LOG_LINES", 3), patch("worker.broadcast_log"):
        worker._drain_process_output(queue, logs, "EXEC-1")

    assert len(logs) == 3


def test_drain_cap_chars_para_em_max_log_chars() -> None:
    queue: "Queue[str]" = Queue()
    for _ in range(10):
        queue.put("x" * 10)
    logs: list[str] = []

    with patch("worker.MAX_LOG_CHARS", 25), patch("worker.broadcast_log"):
        worker._drain_process_output(queue, logs, "EXEC-1")

    assert sum(len(line) for line in logs) <= 30


def test_drain_acima_do_cap_continua_broadcast_mas_nao_acumula() -> None:
    queue: "Queue[str]" = Queue()
    for _ in range(5):
        queue.put("linha\n")

    logs: list[str] = []
    with (
        patch("worker.MAX_LOG_LINES", 2),
        patch("worker.broadcast_log") as mock_broadcast,
    ):
        worker._drain_process_output(queue, logs, "EXEC-1")

    assert len(logs) == 2
    assert mock_broadcast.call_count == 5


# ---------------------------------------------------------------------------
# _finalize_execution guard de status
# ---------------------------------------------------------------------------


def _seed_execution(db_session: Any, exec_id: str, status: str) -> Any:
    auto = models.Automation(name=f"Finalize {exec_id}", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    execucao = models.Execution(
        id=exec_id,
        automation_id=auto.id,
        status=status,
        requested_by="TEST",
        started_at=get_now_local(),
        logs="log previo",
    )
    db_session.add(execucao)
    db_session.commit()
    return execucao


def _finalize(
    db_session: Any, exec_id: str, tmp_path: Any, returncode: int = 0
) -> None:
    process = MagicMock()
    process.returncode = returncode
    task_ctx = {
        "exec_id": exec_id,
        "robot_dir": str(tmp_path),
        "task_start_ts": time.time() - 1,
        "task_start_monotonic": time.monotonic() - 1,
    }
    with patch("worker.broadcast_log"), patch("worker.broadcast_event"):
        worker._finalize_execution(db_session, process, ["novo log"], task_ctx)


def test_finalize_nao_sobrescreve_status_terminated(
    db_session: Any, tmp_path: Any
) -> None:
    _seed_execution(db_session, "EXEC_TERM", "TERMINATED")
    _finalize(db_session, "EXEC_TERM", tmp_path)

    execucao = db_session.query(models.Execution).filter_by(id="EXEC_TERM").first()
    assert execucao.status == "TERMINATED"
    assert execucao.logs == "log previo"


def test_finalize_nao_sobrescreve_status_timeout(
    db_session: Any, tmp_path: Any
) -> None:
    _seed_execution(db_session, "EXEC_TIMEOUT", "TIMEOUT")
    _finalize(db_session, "EXEC_TIMEOUT", tmp_path)

    execucao = db_session.query(models.Execution).filter_by(id="EXEC_TIMEOUT").first()
    assert execucao.status == "TIMEOUT"
    assert execucao.logs == "log previo"


def test_finalize_completa_execucao_running_normalmente(
    db_session: Any, tmp_path: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    _seed_execution(db_session, "EXEC_RUN", "RUNNING")
    _finalize(db_session, "EXEC_RUN", tmp_path, returncode=0)

    execucao = db_session.query(models.Execution).filter_by(id="EXEC_RUN").first()
    assert execucao.status == "SUCCESS"
    assert execucao.exit_code == 0
    assert worker.stats["tasks_completed"] == 1


# ---------------------------------------------------------------------------
# update_stat thread-safety
# ---------------------------------------------------------------------------


def test_update_stat_concorrente_nao_corrompe(reset_worker_globals: None) -> None:
    del reset_worker_globals

    def _increment_many() -> None:
        for _ in range(1000):
            worker.update_stat("tasks_completed", 1)

    threads = [threading.Thread(target=_increment_many) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert worker.stats["tasks_completed"] == 2000


# ---------------------------------------------------------------------------
# scan_for_artifacts
# ---------------------------------------------------------------------------


def test_scan_ignora_arquivo_anterior_ao_start_time(tmp_path: Any) -> None:
    arquivo = tmp_path / "antigo.csv"
    arquivo.write_text("dados", encoding="utf-8")
    antigo_ts = time.time() - 3600
    os.utime(arquivo, (antigo_ts, antigo_ts))

    resultado = worker.scan_for_artifacts(str(tmp_path), time.time())

    assert resultado is None


def test_scan_inclui_arquivo_gerado_durante_execucao(tmp_path: Any) -> None:
    start_ts = time.time()
    arquivo = tmp_path / "novo.xlsx"
    arquivo.write_text("dados", encoding="utf-8")

    resultado = worker.scan_for_artifacts(str(tmp_path), start_ts - 1)

    assert resultado is not None
    assert "novo.xlsx" in json.loads(resultado)


def test_scan_retorna_none_sem_artefatos(tmp_path: Any) -> None:
    resultado = worker.scan_for_artifacts(str(tmp_path), time.time())
    assert resultado is None


# ---------------------------------------------------------------------------
# LOG_FILENAME
# ---------------------------------------------------------------------------


def test_log_filename_usa_worker_test_em_pytest() -> None:
    assert worker.is_pytest is True
    assert worker.LOG_FILENAME == "Worker_test.jsonl"


# ---------------------------------------------------------------------------
# broadcast_log buffer
# ---------------------------------------------------------------------------


def test_broadcast_log_enfileira_por_exec_id(reset_worker_globals: None) -> None:
    del reset_worker_globals
    worker.broadcast_log("linha 1", "EXEC-A")
    worker.broadcast_log("linha 2", "EXEC-A")

    assert worker.log_buffer["EXEC-A"] == ["linha 1", "linha 2"]


def test_broadcast_log_thread_safe_dois_threads_simultaneos(
    reset_worker_globals: None,
) -> None:
    del reset_worker_globals

    def _emit_many() -> None:
        for i in range(500):
            worker.broadcast_log(f"msg-{i}", "EXEC-CONC")

    threads = [threading.Thread(target=_emit_many) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(worker.log_buffer["EXEC-CONC"]) == 1000

"""Testes unitarios para app.metrics (Counters/Gauges Prometheus)."""

import time
from typing import Any
from unittest.mock import patch

from app import metrics
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def _metric_value(metric: Any) -> float:
    """Le o valor interno de um Counter/Gauge do prometheus_client em testes."""
    return float(metric._value.get())  # pylint: disable=protected-access


def test_is_available_retorna_true_quando_prometheus_client_instalado() -> None:
    assert metrics.is_available() is True


def test_record_execution_complete_incrementa_counter_e_observa_duracao() -> None:
    before = _metric_value(
        metrics.EXEC_TOTAL.labels(
            status="sucesso", automation_name="automacao-teste-metrics"
        )
    )

    metrics.record_execution_complete(
        status="sucesso",
        automation_name="automacao-teste-metrics",
        duration_seconds=42.0,
    )

    after = _metric_value(
        metrics.EXEC_TOTAL.labels(
            status="sucesso", automation_name="automacao-teste-metrics"
        )
    )
    assert after == before + 1.0

    text = generate_latest(metrics.EXEC_DURATION).decode("utf-8")
    assert "automacoes_execution_duration_seconds_count" in text


def test_update_system_gauges_seta_pending_e_active() -> None:
    metrics.update_system_gauges(pending=7, active=3)

    assert _metric_value(metrics.QUEUE_PENDING) == 7
    assert _metric_value(metrics.WORKER_ACTIVE) == 3


def test_update_db_gauges_seta_db_size_e_wal_size_com_mocks() -> None:
    with (
        patch("app.database.get_db_size_mb", return_value=12.5),
        patch("app.database.get_wal_size_mb", return_value=3.2),
    ):
        metrics.update_db_gauges()

    assert _metric_value(metrics.DB_SIZE_MB) == 12.5
    assert _metric_value(metrics.WAL_SIZE_MB) == 3.2


def test_update_throttle_gauge_conta_apenas_estados_recentes() -> None:
    fake_state = {
        1: {"count": 1, "last_sent": time.time()},
        2: {"count": 2, "last_sent": time.time() - 700},
        3: {"count": 1, "last_sent": time.time() - 100},
    }

    with patch("app.notifications._alert_state", fake_state):
        metrics.update_throttle_gauge()

    assert _metric_value(metrics.ALERT_THROTTLE_ACTIVE) == 2


def test_update_throttle_gauge_sem_estados_seta_zero() -> None:
    with patch("app.notifications._alert_state", {}):
        metrics.update_throttle_gauge()

    assert _metric_value(metrics.ALERT_THROTTLE_ACTIVE) == 0


def test_get_metrics_response_retorna_bytes_e_content_type() -> None:
    with (
        patch("app.database.get_db_size_mb", return_value=1.0),
        patch("app.database.get_wal_size_mb", return_value=0.5),
        patch("app.notifications._alert_state", {}),
    ):
        body, content_type = metrics.get_metrics_response()

    assert body is not None
    assert len(body) > 0
    assert content_type == CONTENT_TYPE_LATEST
    assert b"automacoes_queue_pending_total" in body


def test_record_execution_complete_indisponivel_retorna_sem_erro() -> None:
    with patch("app.metrics._PROMETHEUS_AVAILABLE", False):
        metrics.record_execution_complete(
            status="erro", automation_name="qualquer", duration_seconds=1.0
        )


def test_update_system_gauges_indisponivel_retorna_sem_erro() -> None:
    with patch("app.metrics._PROMETHEUS_AVAILABLE", False):
        metrics.update_system_gauges(pending=1, active=1)


def test_update_db_gauges_indisponivel_retorna_sem_erro() -> None:
    with patch("app.metrics._PROMETHEUS_AVAILABLE", False):
        metrics.update_db_gauges()


def test_update_throttle_gauge_indisponivel_retorna_sem_erro() -> None:
    with patch("app.metrics._PROMETHEUS_AVAILABLE", False):
        metrics.update_throttle_gauge()


def test_get_metrics_response_indisponivel_retorna_none_none() -> None:
    with patch("app.metrics._PROMETHEUS_AVAILABLE", False):
        body, content_type = metrics.get_metrics_response()
    assert body is None
    assert content_type is None

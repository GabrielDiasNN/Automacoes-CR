# pylint: disable=possibly-used-before-assignment,import-outside-toplevel,relative-beyond-top-level
"""
Métricas Prometheus do Orchestrator (3.4/Fase 3).

Expostas em GET /metrics (texto plain Prometheus).
Opt-in: sempre ativo; consumo é zero se nenhum scraper conectar.

Contadores e gauges refletem o estado do sistema em tempo real via callbacks.
"""

import logging
from typing import Optional

logger = logging.getLogger("orchestrator")

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.info("prometheus_client não instalado — endpoint /metrics desabilitado.")

if _PROMETHEUS_AVAILABLE:
    EXEC_TOTAL = Counter(
        "automacoes_executions_total",
        "Execuções totais por status e automação",
        ["status", "automation_name"],
    )
    EXEC_DURATION = Histogram(
        "automacoes_execution_duration_seconds",
        "Duração das execuções em segundos",
        buckets=[30, 60, 120, 300, 600, 1800],
    )
    QUEUE_PENDING = Gauge(
        "automacoes_queue_pending_total",
        "Execuções com status PENDING na fila",
    )
    WORKER_ACTIVE = Gauge(
        "automacoes_worker_active_tasks",
        "Tarefas ativas no worker no momento",
    )
    DB_SIZE_MB = Gauge(
        "automacoes_db_size_mb",
        "Tamanho do banco SQLite principal em MB",
    )
    WAL_SIZE_MB = Gauge(
        "automacoes_wal_size_mb",
        "Tamanho do WAL SQLite em MB (checkpoint pendente quando alto)",
    )
    ALERT_THROTTLE_ACTIVE = Gauge(
        "automacoes_alert_throttle_active_total",
        "Automações com throttle de alerta ativo no momento",
    )


def record_execution_complete(
    status: str, automation_name: str, duration_seconds: float
) -> None:
    """Registra conclusão de execução nos contadores Prometheus."""
    if not _PROMETHEUS_AVAILABLE:
        return
    EXEC_TOTAL.labels(status=status, automation_name=automation_name).inc()
    EXEC_DURATION.observe(duration_seconds)


def update_system_gauges(pending: int, active: int) -> None:
    """Atualiza gauges de fila e workers ativos (chamado pelo health snapshot)."""
    if not _PROMETHEUS_AVAILABLE:
        return
    QUEUE_PENDING.set(pending)
    WORKER_ACTIVE.set(active)


def update_db_gauges() -> None:
    """Atualiza gauges de tamanho do banco e WAL."""
    if not _PROMETHEUS_AVAILABLE:
        return
    from .database import get_db_size_mb, get_wal_size_mb

    DB_SIZE_MB.set(get_db_size_mb())
    WAL_SIZE_MB.set(get_wal_size_mb())


def update_throttle_gauge() -> None:
    """Atualiza gauge de alertas em throttle ativo."""
    if not _PROMETHEUS_AVAILABLE:
        return
    import time

    from .notifications import _alert_state, _state_lock

    with _state_lock:
        active = sum(
            1
            for state in _alert_state.values()
            if (time.time() - state["last_sent"]) < 600
        )
    ALERT_THROTTLE_ACTIVE.set(active)


def get_metrics_response() -> tuple[Optional[bytes], Optional[str]]:
    """Retorna (body_bytes, content_type) para o endpoint /metrics."""
    if not _PROMETHEUS_AVAILABLE:
        return None, None
    update_db_gauges()
    update_throttle_gauge()
    return generate_latest(), CONTENT_TYPE_LATEST


def is_available() -> bool:
    return _PROMETHEUS_AVAILABLE

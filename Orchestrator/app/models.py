# pylint: disable=R0903,R0901,W0718,W0223,E0402
"""
Modelos SQLAlchemy do Orchestrator Central de Automacoes v1.0.0.

Tabelas:
  - Automation: Cadastro de robos e suas configuracoes.
  - Execution: Historico de execucoes com FK para Automation.
  - WorkerHeartbeat: Registro de saude do Worker (heartbeat).
  - AuditLog: Trilha de auditoria de toda acao administrativa.
"""

import base64
import zlib
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .database import Base
from .timezone import get_now_local


class CompressedText(TypeDecorator[str]):
    """Armazena texto comprimido com zlib+base64; transparente para o ORM (B1/2.3).

    Redução típica em logs de texto: 60–80%. Dados legados (não comprimidos)
    são lidos corretamente pelo fallback em process_result_value.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any | None:
        if value is None:
            return None
        compressed = zlib.compress(value.encode("utf-8"), level=6)
        return base64.b64encode(compressed).decode("ascii")

    def process_result_value(self, value: Any, dialect: Any) -> Any | None:
        if value is None:
            return None
        try:
            compressed = base64.b64decode(value.encode("ascii"))
            return zlib.decompress(compressed).decode("utf-8")
        except Exception:
            return value  # fallback: dado legado não comprimido


class Automation(Base):  # type: ignore[misc,valid-type]
    """Cadastro de automacoes registradas no Hub."""

    __tablename__ = "automations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, index=True, nullable=False)
    description = Column(String(500), nullable=True)
    script_path = Column(String(500), nullable=False)
    schedule = Column(Text, nullable=True)  # JSON estruturado
    max_runtime_minutes = Column(Integer, default=30)
    max_retries = Column(Integer, default=0)
    cooldown_minutes = Column(Integer, default=0)
    sla_minutes = Column(
        Integer, nullable=True
    )  # SLA de recuperação esperado em minutos
    queue_group = Column(String(100), nullable=True)
    enabled = Column(Boolean, default=True)
    test_mode = Column(Boolean, default=False)
    notification_channels = Column(Text, nullable=True)  # Ex: "whatsapp,email"
    created_at = Column(DateTime, default=get_now_local)
    updated_at = Column(DateTime, default=get_now_local, onupdate=get_now_local)

    # Relationship bidirecional
    executions = relationship(
        "Execution",
        back_populates="automation",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


class Execution(Base):  # type: ignore[misc,valid-type]
    """Historico de execucoes de automacoes."""

    __tablename__ = "executions"

    id = Column(String(50), primary_key=True, index=True)
    automation_id = Column(
        Integer,
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(30), default="PENDING", nullable=False)
    priority = Column(
        String(10), default="NORMAL", nullable=False
    )  # HIGH | NORMAL | LOW
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=0, nullable=False)
    queue_group = Column(String(100), nullable=True)
    failure_reason = Column(String(200), nullable=True)
    recovery_action = Column(String(200), nullable=True)
    exit_code = Column(Integer, nullable=True)
    requested_by = Column(String(100), default="SYSTEM")
    started_at = Column(DateTime, default=get_now_local)
    # Instante do ENFILEIRAMENTO. `started_at` é sobrescrito pelo claim (e é
    # lido como "início da execução" por ~8 consultas de métricas), então sem
    # esta coluna o tempo de espera em fila era inobservável — `claimed_at`
    # acabava sempre idêntico a `started_at`. Nulo em linhas anteriores a
    # 31/07/2026: tempo de fila desconhecido, não zero.
    queued_at = Column(DateTime, default=get_now_local, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    worker_instance_id = Column(String(100), nullable=True)
    worker_pid = Column(Integer, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    artifacts = Column(Text, nullable=True)  # JSON list de nomes de arquivo
    logs = Column(CompressedText, nullable=True)

    # Relationship bidirecional
    automation = relationship("Automation", back_populates="executions")

    # Indexes compostos para queries de metricas e fila priorizada.
    # ix_exec_finished_at / ix_exec_status_finished existem no banco desde a
    # migration 20260620_01 e precisam ser declarados aqui para o --autogenerate
    # do Alembic não emitir DROP INDEX acidental.
    __table_args__ = (
        Index("ix_exec_status_started", "status", "started_at"),
        Index("ix_exec_auto_status", "automation_id", "status"),
        Index("ix_exec_priority_status", "priority", "status", "started_at"),
        Index("ix_exec_finished_at", "finished_at"),
        Index("ix_exec_status_finished", "status", "finished_at"),
        # Impõe no banco a invariante "no máximo uma execução RUNNING por
        # automação" (migration 20260731_01). Os quatro produtores de execução
        # verificavam isso em Python no padrão ler-checar-inserir, sem lock:
        # jobs cron concorrentes do APScheduler podiam ambos ler "nenhuma ativa"
        # e ambos inserir. O predicado cobre só RUNNING de propósito —
        # múltiplas PENDING são legítimas e alimentam a fila de prioridades de
        # `claim_next_task`.
        Index(
            "ix_execucao_running_unica_por_automacao",
            "automation_id",
            unique=True,
            sqlite_where=text("status = 'RUNNING'"),
        ),
    )


class WorkerHeartbeat(Base):  # type: ignore[misc,valid-type]
    """Registro de saude do Worker - atualizado a cada ciclo."""

    __tablename__ = "worker_heartbeat"

    id = Column(Integer, primary_key=True, default=1)
    pid = Column(Integer, nullable=True)
    instance_id = Column(String(100), nullable=True)
    host = Column(String(200), nullable=True)
    last_ping = Column(DateTime, default=get_now_local, onupdate=get_now_local)
    uptime_seconds = Column(Float, default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    active_tasks = Column(Integer, default=0)
    version = Column(String(20), default="4.0.0")
    pool_saturated_seconds = Column(Float, default=0)


class SystemHealthSnapshot(Base):  # type: ignore[misc,valid-type]
    """Histórico leve da saúde operacional para tendência e triagem."""

    __tablename__ = "system_health_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=get_now_local, index=True)
    overall_status = Column(String(20), nullable=False)
    pending_count = Column(Integer, default=0, nullable=False)
    running_count = Column(Integer, default=0, nullable=False)
    oldest_pending_age_seconds = Column(Float, default=0, nullable=False)
    oldest_running_age_seconds = Column(Float, default=0, nullable=False)
    wal_size_mb = Column(Float, default=0, nullable=False)
    worker_last_ping_age_seconds = Column(Float, nullable=True)
    running_over_runtime_count = Column(Integer, default=0, nullable=False)
    orphaned_running_count = Column(Integer, default=0, nullable=False)
    failure_hotspots = Column(Text, nullable=True)
    active_queue_groups = Column(Text, nullable=True)
    slo_breaches = Column(Text, nullable=True)


class AuditLog(Base):  # type: ignore[misc,valid-type]
    """Trilha de auditoria para toda acao administrativa no Hub."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=get_now_local, index=True)
    action = Column(
        String(50), nullable=False
    )  # CREATE, UPDATE, DELETE, START, STOP, BACKUP
    entity_type = Column(String(50), nullable=False)  # AUTOMATION, EXECUTION, SYSTEM
    entity_id = Column(String(50), nullable=True)
    actor = Column(String(100), default="SYSTEM")  # IP ou identificador
    details = Column(Text, nullable=True)  # JSON com detalhes adicionais

    __table_args__ = (Index("ix_audit_action_ts", "action", "timestamp"),)

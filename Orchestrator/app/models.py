# pylint: disable=R0903,R0901,W0223
"""
Modelos SQLAlchemy do Orchestrator Central de Automacoes v1.0.0.

Tabelas:
  - Automation: Cadastro de robos e suas configuracoes.
  - Execution: Historico de execucoes com FK para Automation.
  - WorkerHeartbeat: Registro de saude do Worker (heartbeat).
  - AuditLog: Trilha de auditoria de toda acao administrativa.
"""

import base64
import logging
import zlib
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DynamicMapped, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .base import Base
from .timezone import get_now_local

logger = logging.getLogger("orchestrator")


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
        except (ValueError, zlib.error) as exc:
            # ValueError cobre base64 invalido (binascii.Error), UTF-8 invalido e
            # caracteres nao-ASCII; zlib.error cobre blob truncado ou corrompido.
            # O fallback cobre dado legado não comprimido (migration
            # 20260620_02), mas o mesmo except absorveria blob truncado,
            # valor editado à mão no .db ou mudança futura de formato,
            # devolvendo lixo como se fosse log válido. O warning deixa
            # rastro em Logs/orchestrator.jsonl para diferenciar os casos.
            logger.warning(
                "CompressedText: falha ao descomprimir valor (len=%d): %s. "
                "Retornando conteúdo cru como fallback de dado legado.",
                len(value),
                exc,
            )
            return value  # fallback: dado legado não comprimido


class Automation(Base):
    """Cadastro de automacoes registradas no Hub."""

    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(200), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    script_path: Mapped[str] = mapped_column(String(500), nullable=False)
    schedule: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON estruturado
    max_runtime_minutes: Mapped[int | None] = mapped_column(Integer, default=30)
    max_retries: Mapped[int | None] = mapped_column(Integer, default=0)
    cooldown_minutes: Mapped[int | None] = mapped_column(Integer, default=0)
    sla_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # SLA de recuperação esperado em minutos
    queue_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool | None] = mapped_column(Boolean, default=True)
    test_mode: Mapped[bool | None] = mapped_column(Boolean, default=False)
    notification_channels: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Ex: "whatsapp,email"
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=get_now_local)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=get_now_local, onupdate=get_now_local
    )

    # Relationship bidirecional
    executions: DynamicMapped["Execution"] = relationship(
        "Execution",
        back_populates="automation",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


class Execution(Base):
    """Historico de execucoes de automacoes."""

    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    automation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    priority: Mapped[str] = mapped_column(
        String(10), default="NORMAL", nullable=False
    )  # HIGH | NORMAL | LOW
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queue_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recovery_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(100), default="SYSTEM")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=get_now_local)
    # Instante do ENFILEIRAMENTO. `started_at` é sobrescrito pelo claim (e é
    # lido como "início da execução" por ~8 consultas de métricas), então sem
    # esta coluna o tempo de espera em fila era inobservável — `claimed_at`
    # acabava sempre idêntico a `started_at`. Nulo em linhas anteriores a
    # 31/07/2026: tempo de fila desconhecido, não zero.
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=get_now_local, nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    worker_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    worker_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifacts: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON list de nomes de arquivo
    logs: Mapped[str | None] = mapped_column(CompressedText, nullable=True)

    # Relationship bidirecional
    automation: Mapped["Automation"] = relationship(
        "Automation", back_populates="executions"
    )

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


class WorkerHeartbeat(Base):
    """Registro de saude do Worker - atualizado a cada ciclo."""

    __tablename__ = "worker_heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_ping: Mapped[datetime | None] = mapped_column(
        DateTime, default=get_now_local, onupdate=get_now_local
    )
    uptime_seconds: Mapped[float | None] = mapped_column(Float, default=0)
    tasks_completed: Mapped[int | None] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int | None] = mapped_column(Integer, default=0)
    active_tasks: Mapped[int | None] = mapped_column(Integer, default=0)
    version: Mapped[str | None] = mapped_column(String(20), default="4.0.0")
    pool_saturated_seconds: Mapped[float | None] = mapped_column(Float, default=0)


class SystemHealthSnapshot(Base):
    """Histórico leve da saúde operacional para tendência e triagem."""

    __tablename__ = "system_health_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime, default=get_now_local, index=True
    )
    overall_status: Mapped[str] = mapped_column(String(20), nullable=False)
    pending_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    running_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    oldest_pending_age_seconds: Mapped[float] = mapped_column(
        Float, default=0, nullable=False
    )
    oldest_running_age_seconds: Mapped[float] = mapped_column(
        Float, default=0, nullable=False
    )
    wal_size_mb: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    worker_last_ping_age_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    running_over_runtime_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    orphaned_running_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    failure_hotspots: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_queue_groups: Mapped[str | None] = mapped_column(Text, nullable=True)
    slo_breaches: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    """Trilha de auditoria para toda acao administrativa no Hub."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime, default=get_now_local, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # CREATE, UPDATE, DELETE, START, STOP, BACKUP
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # AUTOMATION, EXECUTION, SYSTEM
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor: Mapped[str | None] = mapped_column(
        String(100), default="SYSTEM"
    )  # IP ou identificador
    details: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON com detalhes adicionais

    __table_args__ = (Index("ix_audit_action_ts", "action", "timestamp"),)

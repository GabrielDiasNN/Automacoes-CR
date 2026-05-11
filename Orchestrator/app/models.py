"""
Modelos SQLAlchemy do Orchestrator Hub Soberano v5.0.

Tabelas:
  - Automation: Cadastro de robos e suas configuracoes.
  - Execution: Historico de execucoes com FK para Automation.
  - WorkerHeartbeat: Registro de saude do Worker (heartbeat).
  - AuditLog: Trilha de auditoria de toda acao administrativa.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text,
    ForeignKey, Index, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class Automation(Base):
    """Cadastro de automacoes registradas no Hub."""
    __tablename__ = "automations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, index=True, nullable=False)
    description = Column(String(500), nullable=True)
    script_path = Column(String(500), nullable=False)
    schedule = Column(Text, nullable=True)  # JSON estruturado
    max_runtime_minutes = Column(Integer, default=30)
    enabled = Column(Boolean, default=True)
    test_mode = Column(Boolean, default=False)
    notification_channels = Column(Text, nullable=True)  # Ex: "whatsapp,email"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship bidirecional
    executions = relationship(
        "Execution",
        back_populates="automation",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )


class Execution(Base):
    """Historico de execucoes de automacoes."""
    __tablename__ = "executions"

    id = Column(String(50), primary_key=True, index=True)
    automation_id = Column(
        Integer,
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    status = Column(String(30), default="PENDING", nullable=False)
    priority = Column(String(10), default="NORMAL", nullable=False)  # HIGH | NORMAL | LOW
    exit_code = Column(Integer, nullable=True)
    requested_by = Column(String(100), default="SYSTEM")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    artifacts = Column(Text, nullable=True)  # JSON list de nomes de arquivo
    logs = Column(Text, nullable=True)

    # Relationship bidirecional
    automation = relationship("Automation", back_populates="executions")

    # Indexes compostos para queries de metricas e fila priorizada
    __table_args__ = (
        Index("ix_exec_status_started", "status", "started_at"),
        Index("ix_exec_auto_status", "automation_id", "status"),
        Index("ix_exec_priority_status", "priority", "status", "started_at"),
    )


class WorkerHeartbeat(Base):
    """Registro de saude do Worker - atualizado a cada ciclo."""
    __tablename__ = "worker_heartbeat"

    id = Column(Integer, primary_key=True, default=1)
    pid = Column(Integer, nullable=True)
    last_ping = Column(DateTime(timezone=True), server_default=func.now())
    uptime_seconds = Column(Float, default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    active_tasks = Column(Integer, default=0)
    version = Column(String(20), default="4.0.0")


class AuditLog(Base):
    """Trilha de auditoria para toda acao administrativa no Hub."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    action = Column(String(50), nullable=False)   # CREATE, UPDATE, DELETE, START, STOP, BACKUP
    entity_type = Column(String(50), nullable=False)  # AUTOMATION, EXECUTION, SYSTEM
    entity_id = Column(String(50), nullable=True)
    actor = Column(String(100), default="SYSTEM")  # IP ou identificador
    details = Column(Text, nullable=True)  # JSON com detalhes adicionais

    __table_args__ = (
        Index("ix_audit_action_ts", "action", "timestamp"),
    )

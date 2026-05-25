# pylint: disable=invalid-name, line-too-long, no-member
"""operational history and worker ownership

Revision ID: 20260524_01
Revises: a5b212d4418f
Create Date: 2026-05-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260524_01"
down_revision = "a5b212d4418f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("executions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("claimed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("worker_instance_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("worker_pid", sa.Integer(), nullable=True))

    with op.batch_alter_table("worker_heartbeat", schema=None) as batch_op:
        batch_op.add_column(sa.Column("instance_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("host", sa.String(length=200), nullable=True))

    op.create_table(
        "system_health_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("overall_status", sa.String(length=20), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("running_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("oldest_pending_age_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("oldest_running_age_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("wal_size_mb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("worker_last_ping_age_seconds", sa.Float(), nullable=True),
        sa.Column("running_over_runtime_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orphaned_running_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_hotspots", sa.Text(), nullable=True),
        sa.Column("active_queue_groups", sa.Text(), nullable=True),
        sa.Column("slo_breaches", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_system_health_snapshots_timestamp",
        "system_health_snapshots",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_system_health_snapshots_timestamp", table_name="system_health_snapshots")
    op.drop_table("system_health_snapshots")

    with op.batch_alter_table("worker_heartbeat", schema=None) as batch_op:
        batch_op.drop_column("host")
        batch_op.drop_column("instance_id")

    with op.batch_alter_table("executions", schema=None) as batch_op:
        batch_op.drop_column("worker_pid")
        batch_op.drop_column("worker_instance_id")
        batch_op.drop_column("claimed_at")

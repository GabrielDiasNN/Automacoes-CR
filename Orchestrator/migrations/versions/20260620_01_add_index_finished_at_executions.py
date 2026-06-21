# pylint: disable=invalid-name,no-member
"""add_index_finished_at_executions

Revision ID: 20260620_01
Revises: 20260524_01
Create Date: 2026-06-20 00:00:00.000000
"""

from alembic import op

revision = "20260620_01"
down_revision = "20260524_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_exec_finished_at", "executions", ["finished_at"])
    op.create_index("ix_exec_status_finished", "executions", ["status", "finished_at"])
    op.create_index("ix_snapshot_timestamp", "system_health_snapshots", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_exec_finished_at", table_name="executions")
    op.drop_index("ix_exec_status_finished", table_name="executions")
    op.drop_index("ix_snapshot_timestamp", table_name="system_health_snapshots")

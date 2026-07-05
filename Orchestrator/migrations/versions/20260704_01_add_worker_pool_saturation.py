# pylint: disable=invalid-name, no-member
"""add_worker_pool_saturation

Adiciona worker_heartbeat.pool_saturated_seconds: tempo contínuo (em segundos)
em que o pool de workers ficou 100% ocupado no ciclo atual. Alimenta o finding
de saturação de capacidade em diagnostic_checks.py (fase de crescimento).

Revision ID: 20260704_01
Revises: 20260620_02
Create Date: 2026-07-04 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260704_01"
down_revision = "20260620_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("worker_heartbeat", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "pool_saturated_seconds",
                sa.Float(),
                nullable=True,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("worker_heartbeat", schema=None) as batch_op:
        batch_op.drop_column("pool_saturated_seconds")

# pylint: disable=invalid-name,no-member
"""drop_redundant_snapshot_timestamp_index

Remove ix_snapshot_timestamp (criado em 20260620_01), que duplica o
ix_system_health_snapshots_timestamp criado em 20260524_01 pelo index=True do
ORM sobre a MESMA coluna system_health_snapshots.timestamp. Dois indices
identicos so somam custo de escrita a cada snapshot e mantem drift permanente
no --autogenerate (o segundo nunca foi declarado no ORM).

Usa DROP INDEX IF EXISTS porque um banco legado pode ter sido carimbado
diretamente no head pelo caminho de stamp de run_alembic_migrations, sem nunca
ter executado 20260620_01 — nesse caso o indice nao existe.

Revision ID: 20260721_01
Revises: 20260704_01
Create Date: 2026-07-21 00:00:00.000000
"""

from alembic import op

revision = "20260721_01"
down_revision = "20260704_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_snapshot_timestamp")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_snapshot_timestamp "
        "ON system_health_snapshots (timestamp)"
    )

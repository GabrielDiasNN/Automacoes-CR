# pylint: disable=invalid-name,no-member
"""add_queued_at_to_executions

Torna o tempo de espera em fila observavel.

`claim_next_task` grava o mesmo instante em `started_at` E em `claimed_at`. Como
`started_at` era o momento do ENFILEIRAMENTO (default da coluna, preenchido no
INSERT), o dado original era destruido no claim: o par de colunas fica sempre
identico e `claimed_at` — adicionada justamente para separar as duas semanticas
— nunca carrega informacao nova. O tempo de fila (enfileiramento -> claim) era
permanentemente inobservavel.

A correcao NAO altera a semantica de `started_at`, que segue sendo "inicio da
execucao": cerca de oito consultas em `metrics_queries.py` o usam nesse sentido
(janelas, `last_run`, `last_failure_at`), e mudar isso produziria um degrau na
serie historica e distorceria relatorios de producao. Em vez disso, o instante
do enfileiramento passa a ter coluna propria.

Linhas historicas ficam com `queued_at` nulo — nelas o dado ja havia sido
perdido e nao ha de onde recupera-lo. Consumidores devem tratar nulo como
"tempo de fila desconhecido", nao como zero.

Revision ID: 20260731_02
Revises: 20260731_01
Create Date: 2026-07-31 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260731_02"
down_revision = "20260731_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("executions") as batch_op:
        batch_op.add_column(sa.Column("queued_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("executions") as batch_op:
        batch_op.drop_column("queued_at")

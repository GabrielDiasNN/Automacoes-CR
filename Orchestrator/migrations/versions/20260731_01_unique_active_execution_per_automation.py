# pylint: disable=invalid-name,no-member
"""unique_running_execution_per_automation

Indice UNICO PARCIAL que impoe, no banco, a invariante "no maximo uma execucao
RUNNING por automacao" — a protecao contra execucao SIMULTANEA, que e o dano
concreto da corrida descrita abaixo.

Quatro pontos criavam execucao no padrao ler-checar-inserir, sem lock nem
constraint:

- scheduler_runtime.scheduled_task_wrapper
- routers/automations.start_automation
- execution_runtime.prepare_requeue (requeue manual e auto-retry)
- routers/executions.telemetry_start (que nao checava nada)

Somente claim_next_task tinha CAS real. O APScheduler roda jobs em pool de
threads e _register_cron_schedule cria uma job por expressao cron: duas
expressoes que coincidam no mesmo minuto entram concorrentemente no wrapper,
ambas leem "nenhuma execucao ativa" e ambas inserem.

ESCOPO DELIBERADO: o predicado cobre apenas RUNNING, nao PENDING. Multiplas
execucoes PENDING da mesma automacao sao legitimas — claim_next_task ordena os
candidatos por prioridade (HIGH/NORMAL/LOW) justamente para escolher entre elas,
e proibi-las quebraria a fila de prioridades. Duas PENDING criadas por uma
corrida sao enfileiradas e executadas EM SEQUENCIA; o dano real seria as duas
rodando ao mesmo tempo, e e isso que o indice impede.

Indice parcial e suportado pelo SQLite desde a 3.8. As linhas historicas nao
sao afetadas.

Se o banco ja contiver duas execucoes RUNNING para a mesma automacao (corrida
que de fato ocorreu antes desta migration), a criacao do indice falha — de
proposito. O erro nomeia o problema em vez de mascara-lo, e a limpeza e uma
decisao operacional: identifique com
    SELECT automation_id, COUNT(*) FROM executions
    WHERE status = 'RUNNING' GROUP BY automation_id HAVING COUNT(*) > 1;

Revision ID: 20260731_01
Revises: 20260721_01
Create Date: 2026-07-31 00:00:00.000000
"""

from alembic import op

revision = "20260731_01"
down_revision = "20260721_01"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_execucao_running_unica_por_automacao"


def upgrade() -> None:
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} "
        "ON executions (automation_id) "
        "WHERE status = 'RUNNING'"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")

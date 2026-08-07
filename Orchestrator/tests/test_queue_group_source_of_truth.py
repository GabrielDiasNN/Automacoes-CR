"""Regressão: `queue_group` tinha duas fontes de verdade divergentes.

Até 31/07/2026 o grupo operacional era lido de colunas diferentes conforme o
caminho:

- `_has_running_execution_for_group` — usada pelo worker em `claim_next_task`,
  o ponto onde a fila de fato serializa — filtrava por `Execution.queue_group`,
  cópia CONGELADA no enfileiramento por `build_queued_execution`.
- `get_group_active_execution` — usada por `start_automation`, `prepare_requeue`
  e `scheduled_task_wrapper` — faz join e filtra por `Automation.queue_group`,
  o valor ATUAL.

Depois de um `PATCH /api/automations/{id}` que alterasse o `queue_group`, as
execuções PENDING já na fila carregavam o valor antigo. As duas guardas passavam
a discordar, e duas automações do mesmo grupo novo — `hub-global`, que
compartilha uma única sessão WhatsApp — podiam rodar em paralelo.

A fonte única passou a ser `Automation.queue_group`. `Execution.queue_group`
continua gravado como registro histórico, mas nenhuma decisão de concorrência
o consulta.
"""

import pytest
from app.constants import EXECUTION_STATUS_PENDING, EXECUTION_STATUS_RUNNING
from app.models import Automation, Execution
from app.services.execution_runtime import (
    _has_running_execution_for_group,
    claim_next_task,
)
from app.timezone import get_now_local
from sqlalchemy.orm import Session


def _criar_automacao(db: Session, nome: str, grupo: str | None) -> Automation:
    auto = Automation(
        name=nome,
        script_path=f"{nome}\\run.ps1",
        queue_group=grupo,
        enabled=True,
    )
    db.add(auto)
    db.commit()
    db.refresh(auto)
    return auto


def _criar_execucao(
    db: Session,
    auto: Automation,
    exec_id: str,
    status: str,
    queue_group_congelado: str | None,
) -> Execution:
    execucao = Execution(
        id=exec_id,
        automation_id=auto.id,
        status=status,
        started_at=get_now_local(),
        queue_group=queue_group_congelado,
    )
    db.add(execucao)
    db.commit()
    return execucao


@pytest.mark.integracao
def test_grupo_congelado_obsoleto_nao_libera_claim(db_session: Session) -> None:
    """O cenário exato do defeito: duas automações UNIFICADAS num grupo.

    A vivia em `grupo-oracle` e B em `grupo-email`, e as execuções de cada uma
    congelaram esses valores no enfileiramento. O operador então move as duas
    para `hub-global` — a partir daí elas disputam a mesma sessão WhatsApp e
    são mutuamente exclusivas.

    Com a fonte antiga (`Execution.queue_group`), os valores congelados ainda
    DIFEREM entre si: o worker não enxergava conflito nenhum e reivindicava B
    enquanto A rodava. Com a fonte atual (`Automation.queue_group`), ambas estão
    em `hub-global` e o claim é corretamente bloqueado.
    """
    auto_a = _criar_automacao(db_session, "Automacao A", "hub-global")
    auto_b = _criar_automacao(db_session, "Automacao B", "hub-global")

    _criar_execucao(
        db_session,
        auto_a,
        "EXEC_A_RUNNING",
        EXECUTION_STATUS_RUNNING,
        # Congelado quando a automação ainda era do `grupo-oracle`.
        queue_group_congelado="grupo-oracle",
    )
    _criar_execucao(
        db_session,
        auto_b,
        "EXEC_B_PENDING",
        EXECUTION_STATUS_PENDING,
        # Congelado quando a automação ainda era do `grupo-email`.
        queue_group_congelado="grupo-email",
    )

    reivindicada = claim_next_task(db_session, worker_instance_id="w1", worker_pid=1)

    assert reivindicada is None, (
        "O worker reivindicou uma execução do grupo `hub-global` enquanto outra "
        "automação do mesmo grupo estava RUNNING — a exclusão mútua da sessão "
        "WhatsApp foi violada porque o grupo congelado estava obsoleto."
    )


@pytest.mark.integracao
def test_deteccao_usa_grupo_atual_e_ignora_o_congelado(db_session: Session) -> None:
    """A execução RUNNING tem grupo congelado obsoleto; vale o da automação."""
    auto = _criar_automacao(db_session, "Automacao C", "hub-global")
    _criar_execucao(
        db_session,
        auto,
        "EXEC_C_RUNNING",
        EXECUTION_STATUS_RUNNING,
        queue_group_congelado="grupo-antigo",
    )

    assert _has_running_execution_for_group(db_session, "hub-global") is True
    assert _has_running_execution_for_group(db_session, "grupo-antigo") is False


@pytest.mark.integracao
def test_grupos_distintos_continuam_paralelizando(db_session: Session) -> None:
    """Guarda contra o teste acima passar por bloquear tudo."""
    auto_a = _criar_automacao(db_session, "Automacao D", "grupo-oracle")
    auto_b = _criar_automacao(db_session, "Automacao E", "grupo-email")

    _criar_execucao(
        db_session, auto_a, "EXEC_D_RUNNING", EXECUTION_STATUS_RUNNING, "grupo-oracle"
    )
    _criar_execucao(
        db_session, auto_b, "EXEC_E_PENDING", EXECUTION_STATUS_PENDING, "grupo-email"
    )

    assert claim_next_task(db_session, worker_instance_id="w1", worker_pid=1) == (
        "EXEC_E_PENDING"
    )


@pytest.mark.integracao
def test_automacao_sem_grupo_nao_serializa(db_session: Session) -> None:
    """`queue_group` nulo significa 'sem exclusão mútua'."""
    auto_a = _criar_automacao(db_session, "Automacao F", None)
    auto_b = _criar_automacao(db_session, "Automacao G", None)

    _criar_execucao(
        db_session, auto_a, "EXEC_F_RUNNING", EXECUTION_STATUS_RUNNING, None
    )
    _criar_execucao(
        db_session, auto_b, "EXEC_G_PENDING", EXECUTION_STATUS_PENDING, None
    )

    assert claim_next_task(db_session, worker_instance_id="w1", worker_pid=1) == (
        "EXEC_G_PENDING"
    )

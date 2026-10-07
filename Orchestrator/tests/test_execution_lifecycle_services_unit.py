"""Regras de ciclo de vida que saíram dos routers para os services (07/10/2026).

Cobrem `delete_automation`, `start_automation`, `stop_execution`,
`telemetry_start` e `telemetry_end` no nível do service, sem passar pelo HTTP.
"""

from datetime import datetime, timedelta

import pytest
from app import models
from app.constants import (
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_TERMINATED,
    EXECUTION_TERMINAL_STATUSES,
)
from app.services import automation_repository as repo, execution_runtime as runtime
from app.services.domain_errors import DomainRuleError
from app.timezone import get_now_local
from sqlalchemy.orm import Session

_T0 = datetime(2026, 10, 7, 10, 0, 0)


def _automacao(db: Session, nome: str = "Auto", **extra: object) -> models.Automation:
    auto = models.Automation(name=nome, script_path="./x.ps1", **extra)
    db.add(auto)
    db.commit()
    return auto


def _execucao(db: Session, auto: models.Automation, exec_id: str, status: str) -> None:
    db.add(
        models.Execution(
            id=exec_id,
            automation_id=auto.id,
            status=status,
            requested_by="t",
            started_at=_T0,
        )
    )
    db.commit()


# --- duração ----------------------------------------------------------------


def test_duracao_normal_arredonda_em_duas_casas() -> None:
    assert runtime.compute_duration_seconds(_T0, _T0 + timedelta(seconds=1.239)) == 1.24


@pytest.mark.parametrize("inicio, fim", [(None, _T0), (_T0, None), (None, None)])
def test_duracao_sem_data_devolve_none(
    inicio: datetime | None, fim: datetime | None
) -> None:
    assert runtime.compute_duration_seconds(inicio, fim) is None


def test_duracao_nunca_e_negativa() -> None:
    assert runtime.compute_duration_seconds(_T0, _T0 - timedelta(seconds=5)) == 0.0


def test_duracao_com_tipos_incomparaveis_devolve_none() -> None:
    assert runtime.compute_duration_seconds("a", "b") is None


# --- delete -----------------------------------------------------------------


def test_remocao_bloqueada_com_execucao_ativa(db_session: Session) -> None:
    auto = _automacao(db_session)
    _execucao(db_session, auto, "E1", EXECUTION_STATUS_RUNNING)

    with pytest.raises(DomainRuleError) as erro:
        repo.ensure_deletable(db_session, int(auto.id))

    assert erro.value.status_code == 409
    assert "E1" in erro.value.detail


def test_remocao_liberada_sem_execucao_ativa(db_session: Session) -> None:
    auto = _automacao(db_session)
    _execucao(db_session, auto, "E1", EXECUTION_STATUS_TERMINATED)

    repo.ensure_deletable(db_session, int(auto.id))


# --- start ------------------------------------------------------------------


def test_start_bloqueado_por_execucao_ativa(db_session: Session) -> None:
    auto = _automacao(db_session)
    _execucao(db_session, auto, "E1", EXECUTION_STATUS_RUNNING)

    with pytest.raises(DomainRuleError) as erro:
        runtime.prepare_manual_start(db_session, auto, requested_by="ip")

    assert erro.value.status_code == 409
    assert "execução ativa" in erro.value.detail


def test_start_bloqueado_por_grupo_operacional(db_session: Session) -> None:
    a = _automacao(db_session, "A", queue_group="g")
    b = _automacao(db_session, "B", queue_group="g")
    _execucao(db_session, a, "E1", EXECUTION_STATUS_RUNNING)

    with pytest.raises(DomainRuleError) as erro:
        runtime.prepare_manual_start(db_session, b, requested_by="ip")

    assert erro.value.status_code == 409
    assert "Grupo operacional" in erro.value.detail


def test_start_bloqueado_por_cooldown(db_session: Session) -> None:
    auto = _automacao(db_session, cooldown_minutes=100000)
    _execucao(db_session, auto, "E1", EXECUTION_STATUS_TERMINATED)
    db_session.query(models.Execution).update({"started_at": datetime.now()})
    db_session.commit()

    with pytest.raises(DomainRuleError) as erro:
        runtime.prepare_manual_start(db_session, auto, requested_by="ip")

    assert erro.value.status_code == 409
    assert "Cooldown" in erro.value.detail


def test_start_livre_monta_execucao_enfileirada_sem_commitar(
    db_session: Session,
) -> None:
    auto = _automacao(db_session)

    nova = runtime.prepare_manual_start(db_session, auto, requested_by="10.0.0.1")

    assert str(nova.id).startswith("EXEC_")
    assert nova.requested_by == "10.0.0.1"
    assert nova.status == EXECUTION_STATUS_PENDING
    assert db_session.query(models.Execution).count() == 0


# --- commit com conflito ----------------------------------------------------


def test_commit_or_conflict_traduz_violacao_do_indice_unico(
    db_session: Session,
) -> None:
    auto = _automacao(db_session)
    _execucao(db_session, auto, "E1", EXECUTION_STATUS_RUNNING)
    db_session.add(runtime.build_telemetry_execution(auto))

    with pytest.raises(DomainRuleError) as erro:
        runtime.commit_or_conflict(db_session, "conflito de teste")

    assert (erro.value.status_code, erro.value.detail) == (409, "conflito de teste")
    assert db_session.query(models.Execution).count() == 1  # rollback feito


# --- stop -------------------------------------------------------------------


def test_stop_marca_terminated_com_duracao_e_log() -> None:
    execucao = models.Execution(
        id="E1",
        automation_id=1,
        status=EXECUTION_STATUS_RUNNING,
        started_at=get_now_local() - timedelta(seconds=30),
        logs="antes",
    )

    anterior = runtime.terminate_execution(execucao)

    assert anterior == EXECUTION_STATUS_RUNNING
    assert execucao.status == EXECUTION_STATUS_TERMINATED
    assert execucao.finished_at is not None
    assert execucao.duration_seconds is not None and execucao.duration_seconds > 0
    assert str(execucao.logs).startswith("antes\n[STOP]")
    assert f"status={EXECUTION_STATUS_RUNNING}" in str(execucao.logs)


def test_stop_em_execucao_ja_finalizada_falha_com_400() -> None:
    execucao = models.Execution(
        id="E1", automation_id=1, status=EXECUTION_STATUS_TERMINATED
    )

    with pytest.raises(DomainRuleError) as erro:
        runtime.terminate_execution(execucao)

    assert erro.value.status_code == 400


# --- telemetria -------------------------------------------------------------


def test_telemetria_inicia_running_herdando_config_da_automacao() -> None:
    auto = models.Automation(
        id=7, name="A", script_path="./x.ps1", max_retries=3, queue_group="g"
    )

    execucao = runtime.build_telemetry_execution(auto)

    assert str(execucao.id).startswith("TEL_")
    assert execucao.status == EXECUTION_STATUS_RUNNING
    assert execucao.requested_by == "TERMINAL"
    assert execucao.automation_id == 7
    assert execucao.max_retries == 3
    assert execucao.queue_group == "g"


def test_telemetria_rejeita_status_nao_terminal_com_422() -> None:
    execucao = models.Execution(id="T1", automation_id=1, status="RUNNING")

    with pytest.raises(DomainRuleError) as erro:
        runtime.finish_telemetry_execution(
            execucao,
            status=EXECUTION_STATUS_PENDING,
            exit_code=None,
            logs=None,
            artifacts=None,
        )

    assert erro.value.status_code == 422
    assert execucao.status == "RUNNING"  # nada foi alterado


def test_telemetria_encerra_com_status_terminal_em_maiusculas() -> None:
    terminal = sorted(EXECUTION_TERMINAL_STATUSES)[0]
    execucao = models.Execution(
        id="T1",
        automation_id=1,
        status="RUNNING",
        started_at=get_now_local() - timedelta(seconds=10),
    )

    runtime.finish_telemetry_execution(
        execucao,
        status=terminal.lower(),
        exit_code=2,
        logs="saida",
        artifacts='["a"]',
    )

    assert execucao.status == terminal
    assert execucao.exit_code == 2
    assert execucao.logs == "saida"
    assert execucao.artifacts == '["a"]'
    assert execucao.duration_seconds is not None and execucao.duration_seconds > 0


def test_telemetria_sem_campos_opcionais_preserva_os_existentes() -> None:
    terminal = sorted(EXECUTION_TERMINAL_STATUSES)[0]
    execucao = models.Execution(
        id="T1", automation_id=1, status="RUNNING", logs="orig", exit_code=9
    )

    runtime.finish_telemetry_execution(
        execucao, status=terminal, exit_code=None, logs=None, artifacts=None
    )

    assert execucao.logs == "orig"
    assert execucao.exit_code == 9

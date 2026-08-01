"""Regressões dos achados 1/4 (outliers) da revisão por consenso estocástico."""

import concurrent.futures
import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app import models
from app.constants import (
    EXECUTION_STATUS_REQUEUED,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_TERMINAL_STATUSES,
)
from app.services import env_admin
from app.services.execution_runtime import complete_process_execution, prepare_requeue
from app.timezone import get_now_local
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "Produção Beneficimento",
        "src",
    ),
)


# ---------------------------------------------------------------------------
# A1#7 — PUT /env podia apagar segredos
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_placeholder_mascarado_preserva_o_valor_real() -> None:
    """A API mandava "remova a linha para preservar o atual" — e isso APAGAVA.

    `write_env_content` sobrescreve o arquivo inteiro com o payload; não havia
    merge nenhum. Seguir a instrução removia ORCHESTRATOR_API_KEY e as
    credenciais Oracle, e o efeito só aparecia no restart seguinte.
    """
    atual = "ORCHESTRATOR_API_KEY=chave-real-secreta\nORACLE_USER=leitor\n"
    novo = "ORCHESTRATOR_API_KEY=********\nORACLE_USER=leitor\n"

    resultado = env_admin.restore_masked_values(novo, atual)

    assert "ORCHESTRATOR_API_KEY=chave-real-secreta" in resultado
    assert "********" not in resultado


@pytest.mark.unitario
def test_remocao_deliberada_de_chave_continua_funcionando() -> None:
    """Resolver o placeholder não pode virar merge implícito."""
    atual = "CHAVE_A=1\nCHAVE_B=2\n"
    novo = "CHAVE_A=1\n"

    resultado = env_admin.restore_masked_values(novo, atual)

    assert "CHAVE_B" not in resultado


@pytest.mark.unitario
def test_novo_valor_explicito_sobrescreve() -> None:
    atual = "CHAVE=antigo\n"
    novo = "CHAVE=novo\n"
    assert "CHAVE=novo" in env_admin.restore_masked_values(novo, atual)


# ---------------------------------------------------------------------------
# A2#12 — telemetry_end aceitava status não terminal
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_telemetry_end_recusa_status_nao_terminal(
    client: TestClient, db_session: Session
) -> None:
    """`status: "PENDING"` devolvia a execução à fila, fora de todo controle.

    O worker a reivindicava e rodava a automação de novo, ignorando cooldown,
    max_retries, queue_group e a checagem de execução ativa.
    """
    auto = models.Automation(name="Tel Status", script_path="./tel.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="TEL_STATUS",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    resposta = client.post(
        "/api/executions/telemetry/end/TEL_STATUS",
        json={"status": "PENDING", "exit_code": 0},
        headers=AUTH_HEADERS,
    )
    assert resposta.status_code == 422

    execucao = db_session.query(models.Execution).filter_by(id="TEL_STATUS").first()
    assert execucao is not None
    assert execucao.status == EXECUTION_STATUS_RUNNING


@pytest.mark.unitario
def test_status_terminais_nao_incluem_ativos() -> None:
    assert "PENDING" not in EXECUTION_TERMINAL_STATUSES
    assert "RUNNING" not in EXECUTION_TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# A4#2 — execuções REQUEUED eram imortais no purge
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_requeue_preenche_finished_at(db_session: Session) -> None:
    """Sem `finished_at`, o predicado do purge (`finished_at < cutoff`) nunca
    alcançava a linha — e REQUEUED também não constava dos status terminais."""
    auto = models.Automation(name="Requeue Purge", script_path="./r.ps1", max_retries=3)
    db_session.add(auto)
    db_session.flush()
    origem = models.Execution(
        id="EXEC_ORIGEM",
        automation_id=auto.id,
        status="ERROR",
        started_at=get_now_local(),
        finished_at=get_now_local(),
        retry_count=0,
        max_retries=3,
    )
    db_session.add(origem)
    db_session.commit()

    prepare_requeue(
        db_session,
        origem,
        payload_reason="teste",
        payload_requested_by="QA",
        payload_priority=None,
        fallback_requested_by="QA",
    )

    assert origem.status == EXECUTION_STATUS_REQUEUED
    assert origem.finished_at is not None


# ---------------------------------------------------------------------------
# A3#15 — finalização destruía a trilha [TRACE] do enfileiramento
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_finalizacao_preserva_trilha_de_correlacao(db_session: Session) -> None:
    """`complete_process_execution` SUBSTITUÍA os logs.

    A linha `[TRACE] correlation_id=... event=QUEUED` gravada no enfileiramento
    — única ligação entre o pedido HTTP e a execução — era destruída em todo
    desfecho de sucesso, o caminho mais comum.
    """
    auto = models.Automation(name="Trace", script_path="./t.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_TRACE",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
            logs="[TRACE] correlation_id=abc123 event=QUEUED requested_by=tester",
        )
    )
    db_session.commit()

    complete_process_execution(
        db_session,
        "EXEC_TRACE",
        return_code=0,
        logs=["saida do script\n"],
        artifacts_json=None,
        duration_seconds=1.0,
    )

    execucao = db_session.query(models.Execution).filter_by(id="EXEC_TRACE").first()
    assert execucao is not None
    assert "correlation_id=abc123" in str(execucao.logs)
    assert "saida do script" in str(execucao.logs)


# ---------------------------------------------------------------------------
# A4#19 — deleção com execução ativa apagava a linha em cascata
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_delete_bloqueado_com_execucao_ativa(
    client: TestClient, db_session: Session
) -> None:
    """Com cascade + FK ON, apagar a automação removia a execução RUNNING
    enquanto o PowerShell seguia vivo — sem registro, artefato ou alerta."""
    auto = models.Automation(name="Del Ativa", script_path="./d.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_ATIVA",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    resposta = client.delete(f"/api/automations/{auto.id}", headers=AUTH_HEADERS)
    assert resposta.status_code == 409
    assert db_session.query(models.Execution).filter_by(id="EXEC_ATIVA").first()


# ---------------------------------------------------------------------------
# A4#5 / A4#6 — Future engolido e throttle nunca resetado
# ---------------------------------------------------------------------------


class _ExecutorSincrono:  # pylint: disable=too-few-public-methods
    """Executa na thread do chamador e devolve um Future já concluído.

    O pool real tem `max_workers=2`, então submeter uma segunda tarefa não
    sequencia nada: ela roda na outra thread e o teste podia checar o log antes
    de o callback do primeiro Future ter rodado. Com o Future já concluído,
    `add_done_callback` executa de imediato, na thread do teste.
    """

    def submit(
        self, fn: Any, *args: Any, **kwargs: Any
    ) -> "concurrent.futures.Future[Any]":
        future: "concurrent.futures.Future[Any]" = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pylint: disable=broad-except
            future.set_exception(exc)
        return future


@pytest.mark.unitario
def test_excecao_no_dispatch_e_registrada() -> None:
    """Sem `.result()` nem callback, a exceção ficava presa no Future.

    A asserção é sobre o logger do módulo, não sobre `caplog`: outros testes da
    suíte reconfiguram o logging estruturado e a captura pela raiz deixa de ver
    o registro, o que fazia este teste passar isolado e reprovar na suíte.
    """
    from app import notifications  # pylint: disable=import-outside-toplevel

    with (
        patch.object(
            notifications, "dispatch_alerts", side_effect=RuntimeError("boom")
        ),
        patch.object(notifications, "_notification_executor", _ExecutorSincrono()),
        patch.object(notifications, "logger") as logger_mock,
    ):
        notifications.dispatch_alerts_async(MagicMock(), MagicMock())

    assert logger_mock.error.called, "A exceção do dispatch não chegou ao logger."
    assert "dispatch" in str(logger_mock.error.call_args).lower()


@pytest.mark.unitario
def test_reset_alert_state_zera_o_contador() -> (
    None
):  # pylint: disable=protected-access
    """`reset_alert_state` não tinha chamador em produção: o contador de falhas
    "consecutivas" era, na prática, "falhas desde o boot da API"."""
    from app import notifications  # pylint: disable=import-outside-toplevel

    notifications._mark_sent(4242)
    assert 4242 in notifications._alert_state

    notifications.reset_alert_state(4242)
    assert 4242 not in notifications._alert_state


# ---------------------------------------------------------------------------
# A4#21 — snapshot: tmp compartilhado e sem fsync
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_snapshot_usa_temporario_unico_por_processo(tmp_path: Any) -> None:
    """O `.tmp` determinístico era compartilhado entre o refresh agendado e o
    manual, que chamam a mesma função e podiam intercalar escritas."""
    from beneficiamento.snapshot_store import (  # pylint: disable=import-outside-toplevel
        write_json_atomic,
    )

    destino = tmp_path / "diario.overview.json"
    write_json_atomic(destino, {"ok": True})

    assert json.loads(destino.read_text(encoding="utf-8")) == {"ok": True}
    # Nenhum temporário órfão deixado para trás.
    assert not list(tmp_path.glob("*.tmp"))


# ---------------------------------------------------------------------------
# A2#3 — busy_timeout anulava o timeout do connect_args
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_busy_timeout_alinhado_ao_connect_timeout() -> None:
    """O PRAGMA rodava DEPOIS do connect e substituía o handler de 30 s por 5 s."""
    import inspect  # pylint: disable=import-outside-toplevel

    from app import database  # pylint: disable=import-outside-toplevel

    fonte = inspect.getsource(database.set_sqlite_pragma)
    assert "PRAGMA busy_timeout=30000" in fonte

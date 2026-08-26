"""Cobertura dos caminhos introduzidos pela revisão por consenso estocástico.

Os testes de regressão vivem em `test_revisao_consenso_onda2/onda3.py` e provam
o defeito. Este arquivo exercita os ramos que aqueles não alcançam — tratamento
de `IntegrityError` nos produtores de execução, o reaper de telemetria órfã, a
retomada do relógio de intervalo e o sentinela de parada — para que a correção
não entre com pontos cegos.
"""

# Este arquivo exercita deliberadamente estado e helpers privados dos módulos sob
# teste — é o que significa cobrir os ramos internos da correção.
# pylint: disable=protected-access

import os
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from app import models
from app.constants import (
    DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS,
    EXECUTION_FAILED_STATUSES,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_EXPIRED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_REQUEUED,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_SUCCESS,
    FAILURE_REASON_QUEUE_GROUP_WINDOW_EXPIRED,
    FAILURE_REASON_TELEMETRY_ABANDONED,
    RECOVERY_ACTION_REQUEUE_MANUAL,
)
from app.services import scheduler_runtime as sr
from app.services.execution_runtime import claim_next_task, prepare_requeue
from app.timezone import get_now_local
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _automacao(
    db: Session, nome: str, queue_group: str | None = None
) -> models.Automation:
    auto = models.Automation(
        name=nome, script_path=f"./{nome}.ps1", enabled=True, queue_group=queue_group
    )
    db.add(auto)
    db.flush()
    return auto


# ---------------------------------------------------------------------------
# Reaper de telemetria órfã (C22)
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_reaper_encerra_telemetria_abandonada(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Telemetria sem `/end` congelava o queue_group indefinidamente."""
    auto = _automacao(db_session, "TelOrfa")
    antiga = get_now_local() - timedelta(
        minutes=sr.TELEMETRY_ORPHAN_TIMEOUT_MINUTES + 10
    )
    db_session.add(
        models.Execution(
            id="TEL_ORFA",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=antiga,
            requested_by="TERMINAL",
        )
    )
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(sr, "session_scope", lambda _factory: _NoOpScope(db_session))
    monkeypatch.setattr(sr, "trigger_worker_wakeup", lambda: None)

    sr.reap_orphaned_telemetry()

    execucao = db_session.query(models.Execution).filter_by(id="TEL_ORFA").first()
    assert execucao is not None
    assert execucao.status == EXECUTION_STATUS_ERROR
    assert execucao.failure_reason == FAILURE_REASON_TELEMETRY_ABANDONED
    assert execucao.duration_seconds is not None
    assert "[REAPER]" in str(execucao.logs)


@pytest.mark.integracao
def test_reaper_preserva_telemetria_recente(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guarda: o reaper não pode matar execução externa ainda em curso."""
    auto = _automacao(db_session, "TelRecente")
    db_session.add(
        models.Execution(
            id="TEL_RECENTE",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
            requested_by="TERMINAL",
        )
    )
    db_session.commit()

    monkeypatch.setattr(sr, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(sr, "session_scope", lambda _factory: _NoOpScope(db_session))

    sr.reap_orphaned_telemetry()

    execucao = db_session.query(models.Execution).filter_by(id="TEL_RECENTE").first()
    assert execucao is not None
    assert execucao.status == EXECUTION_STATUS_RUNNING


@pytest.mark.unitario
def test_reaper_nao_propaga_excecao(monkeypatch: pytest.MonkeyPatch) -> None:
    def _explode(_factory: Any) -> Any:
        raise RuntimeError("banco fora")

    monkeypatch.setattr(sr, "session_scope", _explode)
    sr.reap_orphaned_telemetry()  # não deve propagar


class _NoOpScope:
    """Context manager que devolve a sessão de teste sem fechá-la."""

    def __init__(self, sessao: Session) -> None:
        self._sessao = sessao

    def __enter__(self) -> Session:
        return self._sessao

    def __exit__(self, *_args: Any) -> None:
        return None


# ---------------------------------------------------------------------------
# Retomada do relógio dos agendamentos por intervalo (A4#15)
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_intervalo_retoma_horario_anterior() -> None:
    """Sem isso, cada reload reiniciava a contagem e a automação nunca disparava."""
    futuro = get_now_local() + timedelta(minutes=42)
    sr._pending_interval_resume.clear()
    sr._pending_interval_resume["job_99_interval"] = futuro

    resultado = sr._resolve_interval_start_date(99, 60, None)

    assert resultado == futuro


@pytest.mark.unitario
def test_intervalo_descarta_horario_passado() -> None:
    """Horário no passado cairia no misfire e seria descartado."""
    passado = get_now_local() - timedelta(minutes=10)
    sr._pending_interval_resume.clear()
    sr._pending_interval_resume["job_98_interval"] = passado

    assert sr._resolve_interval_start_date(98, 60, None) is None


@pytest.mark.unitario
def test_intervalo_sem_registro_anterior_comeca_do_zero() -> None:
    sr._pending_interval_resume.clear()
    assert sr._resolve_interval_start_date(97, 30, None) is None


# ---------------------------------------------------------------------------
# IntegrityError nos produtores de execução (C15)
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_start_devolve_409_quando_constraint_barra(
    client: TestClient, db_session: Session
) -> None:
    """A corrida entre checagem e commit passa a ser barrada pelo banco."""
    auto = _automacao(db_session, "StartConflito")
    db_session.commit()

    erro = IntegrityError("stmt", {}, Exception("UNIQUE constraint failed"))
    with patch.object(db_session, "commit", side_effect=erro):
        resposta = client.post(
            f"/api/automations/{auto.id}/start", headers=AUTH_HEADERS
        )

    assert resposta.status_code == 409


@pytest.mark.integracao
def test_cron_ignora_disparo_quando_constraint_barra(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrida entre jobs cron do mesmo minuto deixa de criar duplicata.

    Antes da constraint, ambas as threads liam "nenhuma execução ativa" e ambas
    inseriam; o `IntegrityError` da colisão de PK era engolido pelo `except`
    largo e o disparo sumia com uma linha de log.
    """
    auto = _automacao(db_session, "CronConflito")
    db_session.commit()

    monkeypatch.setattr(sr, "session_scope", lambda _f: _NoOpScope(db_session))

    erro = IntegrityError("stmt", {}, Exception("UNIQUE constraint failed"))
    with patch.object(db_session, "commit", side_effect=erro):
        with patch.object(db_session, "rollback") as rollback:
            sr.scheduled_task_wrapper(int(auto.id))

    rollback.assert_called_once()


@pytest.mark.integracao
def test_requeue_devolve_409_quando_constraint_barra(
    client: TestClient, db_session: Session
) -> None:
    auto = _automacao(db_session, "RequeueConflito")
    db_session.add(
        models.Execution(
            id="EXEC_REQ_CONF",
            automation_id=auto.id,
            status=EXECUTION_STATUS_ERROR,
            started_at=get_now_local(),
            finished_at=get_now_local(),
            retry_count=0,
            max_retries=3,
        )
    )
    db_session.commit()

    erro = IntegrityError("stmt", {}, Exception("UNIQUE constraint failed"))
    with patch.object(db_session, "commit", side_effect=erro):
        resposta = client.post(
            "/api/executions/EXEC_REQ_CONF/requeue", json={}, headers=AUTH_HEADERS
        )

    assert resposta.status_code == 409


@pytest.mark.integracao
def test_telemetry_start_devolve_409_quando_constraint_barra(
    client: TestClient, db_session: Session
) -> None:
    """O endpoint não checava execução ativa nenhuma — inseria direto em RUNNING."""
    _automacao(db_session, "TelConflito")
    db_session.commit()

    erro = IntegrityError("stmt", {}, Exception("UNIQUE constraint failed"))
    with patch.object(db_session, "commit", side_effect=erro):
        resposta = client.post(
            "/api/executions/telemetry/start",
            json={"automation_name": "TelConflito"},
            headers=AUTH_HEADERS,
        )

    assert resposta.status_code == 409


# ---------------------------------------------------------------------------
# Download de artefato (C10)
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_download_recusa_arquivo_fora_da_lista(
    client: TestClient, db_session: Session
) -> None:
    """`?filename=whatsapp-config.json` devolvia o contactId do destinatário."""
    auto = _automacao(db_session, "DownloadGuard")
    db_session.add(
        models.Execution(
            id="EXEC_DOWNLOAD",
            automation_id=auto.id,
            status="SUCCESS",
            started_at=get_now_local(),
            artifacts='["relatorio.xlsx"]',
        )
    )
    db_session.commit()

    resposta = client.get(
        "/api/executions/EXEC_DOWNLOAD/download?filename=whatsapp-config.json",
        headers=AUTH_HEADERS,
    )
    assert resposta.status_code == 403


@pytest.mark.integracao
def test_download_recusa_caminho_com_diretorio(
    client: TestClient, db_session: Session
) -> None:
    auto = _automacao(db_session, "DownloadTraversal")
    db_session.add(
        models.Execution(
            id="EXEC_TRAVERSAL",
            automation_id=auto.id,
            status="SUCCESS",
            started_at=get_now_local(),
            artifacts='["relatorio.xlsx"]',
        )
    )
    db_session.commit()

    resposta = client.get(
        "/api/executions/EXEC_TRAVERSAL/download?filename=sub/../../evil.ps1",
        headers=AUTH_HEADERS,
    )
    assert resposta.status_code == 400


@pytest.mark.integracao
def test_download_de_artefato_declarado_mas_ausente_devolve_404(
    client: TestClient, db_session: Session
) -> None:
    """Passa pela allowlist e pela contenção, mas o arquivo não existe."""
    auto = _automacao(db_session, "DownloadAusente")
    db_session.add(
        models.Execution(
            id="EXEC_AUSENTE",
            automation_id=auto.id,
            status="SUCCESS",
            started_at=get_now_local(),
            artifacts='["relatorio-inexistente.xlsx"]',
        )
    )
    db_session.commit()

    resposta = client.get(
        "/api/executions/EXEC_AUSENTE/download?filename=relatorio-inexistente.xlsx",
        headers=AUTH_HEADERS,
    )
    assert resposta.status_code == 404


@pytest.mark.unitario
def test_artifacts_com_json_invalido_cai_no_fallback() -> None:
    """`artifacts` corrompido não pode liberar arquivo arbitrário."""
    from app.routers.executions import (  # pylint: disable=import-outside-toplevel
        _artifact_is_downloadable,
    )

    class _Exec:  # pylint: disable=too-few-public-methods
        artifacts = "{nao é json"

    assert _artifact_is_downloadable(_Exec(), "relatorio.xlsx") is True  # type: ignore[arg-type]
    assert _artifact_is_downloadable(_Exec(), "config.json") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Sentinela de parada gracioso (A1#5)
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_sentinela_de_parada_e_detectado(tmp_path: Any) -> None:
    """`Stop-Process -Force` não entrega sinal no Windows; o arquivo entrega."""
    import worker  # pylint: disable=import-outside-toplevel

    sentinela = tmp_path / "worker.shutdown"
    with patch.object(worker, "SHUTDOWN_SENTINEL_PATH", str(sentinela)):
        assert worker._graceful_stop_requested() is False
        sentinela.write_text("", encoding="utf-8")
        assert worker._graceful_stop_requested() is True
        worker._clear_shutdown_sentinel()
        assert os.path.exists(str(sentinela)) is False


@pytest.mark.unitario
def test_limpar_sentinela_inexistente_nao_falha(tmp_path: Any) -> None:
    import worker  # pylint: disable=import-outside-toplevel

    with patch.object(worker, "SHUTDOWN_SENTINEL_PATH", str(tmp_path / "nao-existe")):
        worker._clear_shutdown_sentinel()


# ---------------------------------------------------------------------------
# Sanitização do log ao vivo (A4#17)
# ---------------------------------------------------------------------------


@pytest.mark.unitario
def test_env_admin_restore_ignora_comentario_e_linha_vazia() -> None:
    """Linhas sem `=` e comentários passam intactos pelo restore."""
    from app.services.env_admin import (  # pylint: disable=import-outside-toplevel
        restore_masked_values,
    )

    atual = "# comentario\n\nCHAVE=valor\n"
    novo = "# comentario\n\nCHAVE=********\n"
    resultado = restore_masked_values(novo, atual)

    assert "# comentario" in resultado
    assert "CHAVE=valor" in resultado


@pytest.mark.unitario
def test_env_admin_placeholder_de_chave_nova_fica_como_esta() -> None:
    """Placeholder sem correspondente no arquivo atual não tem o que restaurar."""
    from app.services.env_admin import (  # pylint: disable=import-outside-toplevel
        restore_masked_values,
    )

    resultado = restore_masked_values("NOVA=********\n", "OUTRA=1\n")
    assert "NOVA=********" in resultado


# ---------------------------------------------------------------------------
# Descarte silencioso por queue_group ocupado (26/08/2026)
#
# Até aqui, um tick cujo queue_group estivesse ocupado era descartado dentro
# de `scheduled_task_wrapper` antes de qualquer `Execution` existir: sem
# execução, sem retry, sem alerta — só uma linha de log. `claim_next_task` já
# sabia segurar uma PENDING até o grupo liberar; o agendador é quem jogava o
# tick fora antes de chegar lá. Os testes abaixo cobrem o novo contrato:
# o agendador SEMPRE enfileira (exceto pela regra de H1, inalterada), e é o
# worker quem decide quando — ou se, dentro da janela de validade — reivindicar.
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_scheduled_task_wrapper_enfileira_mesmo_com_queue_group_ocupado(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O tick vira PENDING mesmo com outra automação do mesmo grupo RUNNING.

    Antes desta correção, nenhuma `Execution` era criada aqui: o cenário exato
    do incidente de produção (OBs Restrição Branco perdendo ticks porque
    Montagem de Terceirizados ocupava o grupo `oracle`).
    """
    ocupante = _automacao(db_session, "OcupanteGrupo", queue_group="oracle")
    bloqueada = _automacao(db_session, "BloqueadaGrupo", queue_group="oracle")
    db_session.add(
        models.Execution(
            id="EXEC_OCUPANTE",
            automation_id=ocupante.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    monkeypatch.setattr(sr, "session_scope", lambda _factory: _NoOpScope(db_session))

    sr.scheduled_task_wrapper(int(bloqueada.id))

    criada = (
        db_session.query(models.Execution)
        .filter(models.Execution.automation_id == bloqueada.id)
        .first()
    )
    assert criada is not None, (
        "O tick foi descartado em vez de enfileirado: a regressão do "
        "descarte silencioso por queue_group voltou."
    )
    assert criada.status == EXECUTION_STATUS_PENDING


@pytest.mark.integracao
def test_scheduled_task_wrapper_nao_empilha_pending_da_mesma_automacao(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1: mesmo enfileirando sempre, uma automação não acumula 2 PENDING.

    Guarda contra o efeito colateral óbvio de remover o corte por
    queue_group: se o corte por "já tem execução ativa" (checado antes)
    quebrasse, uma automação de cadência curta acumularia execuções durante
    um bloqueio longo e disparia todas em sequência quando o grupo liberasse.
    """
    ocupante = _automacao(db_session, "OcupanteH1", queue_group="oracle")
    auto = _automacao(db_session, "CadenciaCurtaH1", queue_group="oracle")
    db_session.add(
        models.Execution(
            id="EXEC_OCUPANTE_H1",
            automation_id=ocupante.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    monkeypatch.setattr(sr, "session_scope", lambda _factory: _NoOpScope(db_session))

    sr.scheduled_task_wrapper(int(auto.id))
    sr.scheduled_task_wrapper(int(auto.id))
    sr.scheduled_task_wrapper(int(auto.id))

    pendentes = (
        db_session.query(models.Execution)
        .filter(
            models.Execution.automation_id == auto.id,
            models.Execution.status == EXECUTION_STATUS_PENDING,
        )
        .all()
    )
    assert len(pendentes) == 1


@pytest.mark.integracao
def test_claim_next_task_reivindica_pending_apos_grupo_liberar(
    db_session: Session,
) -> None:
    """A PENDING que ficou presa atrás do grupo é reivindicada quando ele libera.

    Fecha o ciclo: `scheduled_task_wrapper` enfileira apesar do bloqueio
    (teste acima), `claim_next_task` já sabia segurar essa PENDING enquanto
    o grupo estava ocupado — e agora prova que ela é de fato processada assim
    que a execução ocupante termina, em vez de ficar presa para sempre.
    """
    ocupante = _automacao(db_session, "OcupanteLibera", queue_group="oracle")
    presa = _automacao(db_session, "PresaLibera", queue_group="oracle")
    db_session.add(
        models.Execution(
            id="EXEC_OCUPANTE_LIBERA",
            automation_id=ocupante.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.add(
        models.Execution(
            id="EXEC_PRESA_LIBERA",
            automation_id=presa.id,
            status=EXECUTION_STATUS_PENDING,
            queue_group="oracle",
        )
    )
    db_session.commit()

    assert claim_next_task(db_session) is None, (
        "Reivindicou a PENDING com o grupo ainda ocupado — exclusão mútua " "quebrada."
    )

    ocupante_exec = (
        db_session.query(models.Execution).filter_by(id="EXEC_OCUPANTE_LIBERA").first()
    )
    assert ocupante_exec is not None
    ocupante_exec.status = EXECUTION_STATUS_SUCCESS  # type: ignore[assignment]
    ocupante_exec.finished_at = get_now_local()  # type: ignore[assignment]
    db_session.commit()

    assert claim_next_task(db_session) == "EXEC_PRESA_LIBERA"


@pytest.mark.integracao
def test_claim_next_task_expira_pending_velha_de_queue_group(
    db_session: Session,
) -> None:
    """H2: uma PENDING velha demais, presa atrás do grupo, não roda tardiamente.

    O grupo está OCUPADO no momento do claim (execução RUNNING do mesmo
    `queue_group`) — é essa ocupação que causou a espera. A política de
    validade reusa o limiar de INCIDENT do próprio watchdog de fila pendente
    (`DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS`): quando o dashboard já
    marcaria a fila como INCIDENT, o tick é descartado como EXPIRED em vez de
    ser reivindicado tardiamente. Sem a ocupante RUNNING aqui, a expiração
    não tem causa real e o teste estaria de volta a afirmar o bug do item 1
    da revisão de 26/08/2026 (expirar PENDING velha mesmo com grupo livre).
    """
    ocupante = _automacao(db_session, "OcupanteTickVelho", queue_group="oracle")
    auto = _automacao(db_session, "TickVelho", queue_group="oracle")
    velha = get_now_local() - timedelta(
        seconds=DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS + 1
    )
    db_session.add(
        models.Execution(
            id="EXEC_OCUPANTE_TICK_VELHO",
            automation_id=ocupante.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.add(
        models.Execution(
            id="EXEC_TICK_VELHO",
            automation_id=auto.id,
            status=EXECUTION_STATUS_PENDING,
            queue_group="oracle",
            queued_at=velha,
        )
    )
    db_session.commit()

    assert claim_next_task(db_session) is None

    expirada = (
        db_session.query(models.Execution).filter_by(id="EXEC_TICK_VELHO").first()
    )
    assert expirada is not None
    assert expirada.status == EXECUTION_STATUS_EXPIRED
    assert expirada.failure_reason == FAILURE_REASON_QUEUE_GROUP_WINDOW_EXPIRED
    assert expirada.recovery_action == RECOVERY_ACTION_REQUEUE_MANUAL
    assert expirada.finished_at is not None


@pytest.mark.integracao
def test_claim_next_task_nao_expira_pending_velha_com_grupo_livre(
    db_session: Session,
) -> None:
    """Item 1 da revisão de 26/08/2026: sem bloqueio de grupo, idade não expira.

    Uma PENDING antiga (acima do teto de `DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS`)
    cujo `queue_group` não tem nenhuma execução RUNNING não foi causada por
    disputa de grupo — não deve ser descartada como
    `FAILURE_REASON_QUEUE_GROUP_WINDOW_EXPIRED`, e sim reivindicada normalmente.
    """
    auto = _automacao(db_session, "TickVelhoGrupoLivre", queue_group="oracle")
    velha = get_now_local() - timedelta(
        seconds=DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS + 1
    )
    db_session.add(
        models.Execution(
            id="EXEC_TICK_VELHO_LIVRE",
            automation_id=auto.id,
            status=EXECUTION_STATUS_PENDING,
            queue_group="oracle",
            queued_at=velha,
        )
    )
    db_session.commit()

    assert claim_next_task(db_session) == "EXEC_TICK_VELHO_LIVRE"

    reivindicada = (
        db_session.query(models.Execution).filter_by(id="EXEC_TICK_VELHO_LIVRE").first()
    )
    assert reivindicada is not None
    assert reivindicada.status == EXECUTION_STATUS_RUNNING


@pytest.mark.integracao
def test_claim_next_task_nao_expira_pending_dentro_da_janela(
    db_session: Session,
) -> None:
    """Guarda contra política agressiva demais: dentro da janela, roda normal.

    Sem este teste, um teto de validade poderia ser implementado tão baixo
    que qualquer atraso normal do poller do worker já descartaria ticks
    legítimos — o que reintroduziria, por outra via, a mesma perda silenciosa
    que esta correção existe para eliminar.
    """
    auto = _automacao(db_session, "TickDentroDaJanela", queue_group="oracle")
    quase_no_limite = get_now_local() - timedelta(
        seconds=DIAGNOSTIC_PENDING_STALLED_INCIDENT_SECONDS - 60
    )
    db_session.add(
        models.Execution(
            id="EXEC_TICK_OK",
            automation_id=auto.id,
            status=EXECUTION_STATUS_PENDING,
            queue_group="oracle",
            queued_at=quase_no_limite,
        )
    )
    db_session.commit()

    assert claim_next_task(db_session) == "EXEC_TICK_OK"


# ---------------------------------------------------------------------------
# Achados da revisão de 26/08/2026 sobre EXPIRED (achados 1 e 2)
# ---------------------------------------------------------------------------


@pytest.mark.integracao
def test_prepare_requeue_aceita_expired_mesmo_com_max_retries_zero(
    db_session: Session,
) -> None:
    """`_expire_if_queue_window_exceeded` grava `recovery_action=RECOVERY_ACTION_REQUEUE_MANUAL`
    numa EXPIRED — esse requeue precisa realmente funcionar, mesmo para as
    automações com `max_retries=0` (maioria hoje: OFST-06, OBP-04, ORB-07,
    RE-03). Sem a isenção em `prepare_requeue`, o operador seguiria a ação
    recomendada e receberia 409 "Limite de retry excedido: 0/0" — a EXPIRED
    nunca chegou a rodar, então não deveria consumir orçamento de retry.
    """
    auto = _automacao(db_session, "ExpiradaSemRetryBudget")
    auto.max_retries = 0  # type: ignore[assignment]
    expirada = models.Execution(
        id="EXEC_EXPIRADA_MAX_RETRIES_ZERO",
        automation_id=auto.id,
        status=EXECUTION_STATUS_EXPIRED,
        started_at=get_now_local(),
        finished_at=get_now_local(),
        retry_count=0,
        max_retries=0,
        failure_reason=FAILURE_REASON_QUEUE_GROUP_WINDOW_EXPIRED,
        recovery_action=RECOVERY_ACTION_REQUEUE_MANUAL,
    )
    db_session.add(expirada)
    db_session.commit()

    novo_exec, _audit = prepare_requeue(
        db_session,
        expirada,
        payload_reason="teste requeue manual de EXPIRED",
        payload_requested_by="QA",
        payload_priority=None,
        fallback_requested_by="QA",
    )

    assert novo_exec.status == EXECUTION_STATUS_PENDING
    assert expirada.status == EXECUTION_STATUS_REQUEUED


@pytest.mark.unitario
def test_expired_nao_conta_como_falha() -> None:
    """EXPIRED representa um tick descartado por congestionamento de
    queue_group ANTES de qualquer tentativa — não uma automação que rodou e
    falhou. Contá-lo em `EXECUTION_FAILED_STATUSES` inflaria scoring, métricas
    diárias e portfólio toda vez que o grupo `oracle` (compartilhado por 6
    automações) ficar congestionado, mesmo sem nenhuma execução real ter
    falhado.
    """
    assert EXECUTION_STATUS_EXPIRED not in EXECUTION_FAILED_STATUSES

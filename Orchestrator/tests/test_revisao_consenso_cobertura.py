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
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_RUNNING,
    FAILURE_REASON_TELEMETRY_ABANDONED,
)
from app.services import scheduler_runtime as sr
from app.timezone import get_now_local
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _automacao(db: Session, nome: str) -> models.Automation:
    auto = models.Automation(name=nome, script_path=f"./{nome}.ps1", enabled=True)
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

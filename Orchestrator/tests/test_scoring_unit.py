"""Testes unitários de app/services/scoring.py (compute_attention_score)."""

# pylint: disable=too-many-arguments

from datetime import datetime, timedelta

from app import models
from app.services.scoring import compute_attention_score
from app.timezone import get_now_local


def _automation(
    *,
    automation_id: int = 1,
    max_runtime_minutes: int = 30,
    max_retries: int = 0,
    queue_group: str | None = None,
) -> models.Automation:
    return models.Automation(
        id=automation_id,
        name=f"Automacao {automation_id}",
        script_path="./test/run.ps1",
        max_runtime_minutes=max_runtime_minutes,
        max_retries=max_retries,
        queue_group=queue_group,
    )


def _execution(
    *,
    execution_id: str = "ex-1",
    automation: models.Automation | None = None,
    status: str = "PENDING",
    priority: str = "NORMAL",
    retry_count: int = 0,
    max_retries: int = 999,
    started_at: datetime | None = None,
    failure_reason: str | None = None,
    queue_group: str | None = None,
) -> models.Execution:
    auto = automation or _automation()
    ex = models.Execution(
        id=execution_id,
        automation_id=auto.id,
        status=status,
        priority=priority,
        retry_count=retry_count,
        max_retries=max_retries,
        started_at=started_at,
        failure_reason=failure_reason,
        queue_group=queue_group,
    )
    ex.automation = auto
    return ex


NOW = get_now_local()

# ---------------------------------------------------------------------------
# 1. Regras de fila (PENDING)
# ---------------------------------------------------------------------------


def test_pending_sem_started_at_soma_apenas_a_base_de_fila() -> None:
    ex = _execution(status="PENDING", started_at=None)
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 18
    assert reasons == ["Execução aguardando processamento na fila"]


def test_pending_idade_abaixo_do_limiar_nao_soma_bonus_de_envelhecimento() -> None:
    ex = _execution(status="PENDING", started_at=NOW - timedelta(seconds=899))
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 18


def test_pending_idade_no_limiar_exato_soma_bonus_de_envelhecimento() -> None:
    ex = _execution(status="PENDING", started_at=NOW - timedelta(seconds=900))
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 18 + 22
    assert "Fila envelhecida para esta execução" in reasons


def test_pending_idade_acima_do_limiar_soma_bonus_de_envelhecimento() -> None:
    ex = _execution(status="PENDING", started_at=NOW - timedelta(hours=1))
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 18 + 22


# ---------------------------------------------------------------------------
# 2. Regras de execução ativa (RUNNING)
# ---------------------------------------------------------------------------


def test_running_sem_automation_nao_soma_bonus_de_estouro() -> None:
    ex = _execution(status="RUNNING", started_at=NOW - timedelta(hours=2))
    ex.automation = None
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 45
    assert reasons == ["Execução ativa exige acompanhamento direto"]


def test_running_dentro_do_prazo_maximo_nao_soma_bonus_de_estouro() -> None:
    auto = _automation(max_runtime_minutes=30)
    ex = _execution(
        status="RUNNING", automation=auto, started_at=NOW - timedelta(minutes=10)
    )
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 45


def test_running_acima_do_prazo_maximo_soma_bonus_de_estouro() -> None:
    auto = _automation(max_runtime_minutes=30)
    ex = _execution(
        status="RUNNING", automation=auto, started_at=NOW - timedelta(minutes=31)
    )
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 45 + 35
    assert "Execução ativa acima do tempo máximo cadastrado" in reasons


def test_running_com_max_runtime_zerado_nao_soma_bonus_de_estouro() -> None:
    auto = _automation(max_runtime_minutes=0)
    ex = _execution(
        status="RUNNING", automation=auto, started_at=NOW - timedelta(days=1)
    )
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 45


# ---------------------------------------------------------------------------
# 3. Regras de estado terminal
# ---------------------------------------------------------------------------


def test_status_terminal_com_falha_soma_bonus_de_triagem() -> None:
    ex = _execution(status="ERROR")
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 30
    assert reasons == ["Execução terminal com necessidade de triagem"]


def test_status_terminal_entregue_nao_soma_bonus_de_estado() -> None:
    ex = _execution(status="SUCCESS")
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 0
    assert not reasons


# ---------------------------------------------------------------------------
# 4. Regras de concorrência (apenas para status "queueable": terminais + REQUEUED)
# ---------------------------------------------------------------------------


def test_conflito_de_automation_ativa_soma_bonus() -> None:
    auto = _automation(automation_id=7)
    ex = _execution(execution_id="ex-1", automation=auto, status="SUCCESS")
    outra_execucao = _execution(execution_id="ex-2", automation=auto, status="RUNNING")
    score, reasons = compute_attention_score(ex, NOW, {7: outra_execucao}, {})
    assert score == 15
    assert "Existe outra execução ativa para a automação" in reasons


def test_conflito_de_grupo_ativo_soma_bonus_quando_automation_esta_livre() -> None:
    auto = _automation(automation_id=7, queue_group="financeiro")
    ex = _execution(execution_id="ex-1", automation=auto, status="SUCCESS")
    outra_execucao = _execution(
        execution_id="ex-2", automation=_automation(automation_id=9), status="RUNNING"
    )
    score, reasons = compute_attention_score(
        ex, NOW, {}, {"financeiro": outra_execucao}
    )
    assert score == 18
    assert "Grupo operacional já está ocupado" in reasons


def test_limite_de_retry_atingido_soma_bonus_quando_sem_conflitos() -> None:
    ex = _execution(status="SUCCESS", retry_count=3, max_retries=3)
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    # +12 de limite de retry atingido, +24 (min(3*8, 24)) da regra de retries do bloco 5.
    assert score == 12 + 24
    assert "Limite de retry já foi atingido" in reasons


def test_sem_conflito_e_sem_retries_nao_soma_bonus_de_concorrencia() -> None:
    ex = _execution(status="SUCCESS", retry_count=0, max_retries=3)
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 0
    assert not reasons


def test_a_propria_execucao_ativa_nao_conta_como_conflito() -> None:
    auto = _automation(automation_id=7)
    ex = _execution(execution_id="ex-1", automation=auto, status="SUCCESS")
    score, reasons = compute_attention_score(ex, NOW, {7: ex}, {})
    assert score == 0
    assert not reasons


# ---------------------------------------------------------------------------
# 5. Regras de prioridade
# ---------------------------------------------------------------------------


def test_prioridade_high_soma_bonus() -> None:
    ex = _execution(status="SUCCESS", priority="HIGH")
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 20
    assert "Execução marcada como prioridade alta" in reasons


def test_prioridade_normal_nao_altera_score() -> None:
    ex = _execution(status="SUCCESS", priority="NORMAL")
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 0


def test_prioridade_low_subtrai_do_score_existente() -> None:
    ex = _execution(status="ERROR", priority="LOW")
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 30 - 5


def test_prioridade_low_nao_deixa_score_negativo() -> None:
    ex = _execution(status="SUCCESS", priority="LOW")
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 0


# ---------------------------------------------------------------------------
# 6. Regras de escala por retry
# ---------------------------------------------------------------------------


def test_retry_count_zero_nao_soma_bonus_de_retry() -> None:
    ex = _execution(status="SUCCESS", retry_count=0)
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 0
    assert not reasons


def test_retry_count_escala_linearmente_antes_do_teto() -> None:
    ex = _execution(status="SUCCESS", retry_count=1)
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 8
    assert "Execução já passou por 1 retry(s)" in reasons


def test_retry_count_no_teto_exato() -> None:
    ex = _execution(status="SUCCESS", retry_count=3)
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 24


def test_retry_count_acima_do_teto_fica_capado_em_24() -> None:
    ex = _execution(status="SUCCESS", retry_count=10)
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 24


# ---------------------------------------------------------------------------
# 7. Regra de motivo de falha
# ---------------------------------------------------------------------------


def test_failure_reason_presente_soma_bonus() -> None:
    ex = _execution(status="ERROR", failure_reason="timeout na conexão Oracle")
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 30 + 8
    assert "Há motivo de falha registrado" in reasons


def test_failure_reason_ausente_nao_soma_bonus() -> None:
    ex = _execution(status="ERROR", failure_reason=None)
    score, _reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 30


# ---------------------------------------------------------------------------
# 8. Combinação de regras (regressão do bug de ordenação PENDING x ativa)
# ---------------------------------------------------------------------------


def test_running_com_prioridade_alta_e_retries_acumula_todos_os_bonus() -> None:
    auto = _automation(max_runtime_minutes=0)
    ex = _execution(
        status="RUNNING",
        automation=auto,
        priority="HIGH",
        retry_count=2,
        failure_reason="erro transitório",
    )
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    # 45 (ativa) + 20 (HIGH) + 16 (min(2*8,24)) + 8 (failure_reason) = 89
    assert score == 45 + 20 + 16 + 8
    assert len(reasons) == 4


def test_pending_envelhecida_nao_e_reclassificada_como_ativa_generica() -> None:
    """Regressão: PENDING está em EXECUTION_ACTIVE_STATUSES, mas deve continuar
    caindo no ramo específico de fila (bloco 1), não no ramo genérico de
    "execução ativa" (bloco 2), que soma um valor e um motivo diferentes."""
    ex = _execution(status="PENDING", started_at=NOW - timedelta(seconds=901))
    score, reasons = compute_attention_score(ex, NOW, {}, {})
    assert score == 18 + 22
    assert reasons == [
        "Execução aguardando processamento na fila",
        "Fila envelhecida para esta execução",
    ]
    assert "Execução ativa exige acompanhamento direto" not in reasons

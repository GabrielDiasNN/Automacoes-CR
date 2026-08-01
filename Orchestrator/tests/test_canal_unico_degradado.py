"""Regressão A1#2: PARTIAL de canal degradado em automação de canal único.

Os exit codes 24 (WhatsApp) e 25 (e-mail) significam "o canal X falhou, mas o
outro entregou" — é o que justifica PARTIAL em vez de ERROR: sem alerta crítico
e sem penalidade de SLA.

Em automação de canal ÚNICO a premissa é falsa. `Montagem de Terceirizados`
(MT-02) emite `exit 25` e declara apenas `email` no manifesto: uma execução sem
nenhuma entrega era registrada como sucesso parcial, silenciosa.
"""

import json
import os

import pytest
from app import models
from app.constants import (
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PARTIAL,
    EXECUTION_STATUS_RUNNING,
    FAILURE_REASON_CHANNEL_DELIVERY_FAILED,
)
from app.services.execution_runtime import (
    classify_process_result,
    classify_process_result_for_channels,
    complete_process_execution,
)
from app.timezone import get_now_local
from sqlalchemy.orm import Session

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.unitario
@pytest.mark.parametrize(
    ("exit_code", "canal_unico"),
    [(24, "whatsapp"), (25, "email")],
)
def test_canal_unico_degradado_vira_erro(exit_code: int, canal_unico: str) -> None:
    status, reason, _ = classify_process_result_for_channels(exit_code, canal_unico)

    assert status == EXECUTION_STATUS_ERROR, (
        f"exit {exit_code} em automação que só tem '{canal_unico}' significa "
        "nenhuma entrega — PARTIAL suprime o alerta e preserva o SLA."
    )
    assert reason == FAILURE_REASON_CHANNEL_DELIVERY_FAILED


@pytest.mark.unitario
@pytest.mark.parametrize("exit_code", [24, 25])
def test_canal_redundante_continua_parcial(exit_code: int) -> None:
    """Guarda: o PARTIAL existe para não gerar incidente quando houve entrega."""
    status, _, _ = classify_process_result_for_channels(exit_code, "email,whatsapp")
    assert status == EXECUTION_STATUS_PARTIAL


@pytest.mark.unitario
@pytest.mark.parametrize("canais", [None, "", "   "])
def test_sem_canais_declarados_preserva_o_comportamento(canais: str | None) -> None:
    """Sem a lista não há evidência de canal único; não se inventa incidente."""
    assert classify_process_result_for_channels(25, canais)[0] == (
        EXECUTION_STATUS_PARTIAL
    )


@pytest.mark.unitario
@pytest.mark.parametrize("exit_code", [0, 1, 3, 9, 22])
def test_demais_exit_codes_nao_sao_afetados(exit_code: int) -> None:
    """A correção só pode tocar o ramo PARTIAL de canal degradado."""
    assert classify_process_result_for_channels(
        exit_code, "email"
    ) == classify_process_result(exit_code)


@pytest.mark.unitario
def test_canal_declarado_com_espaco_e_caixa_e_normalizado() -> None:
    assert classify_process_result_for_channels(25, " EMAIL ")[0] == (
        EXECUTION_STATUS_ERROR
    )


@pytest.mark.integracao
def test_finalizacao_usa_os_canais_da_automacao(db_session: Session) -> None:
    """O caminho real: `complete_process_execution` lê `notification_channels`."""
    auto = models.Automation(
        name="Canal Unico",
        script_path="./cu.ps1",
        notification_channels="email",
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_CANAL_UNICO",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    execucao = complete_process_execution(
        db_session,
        "EXEC_CANAL_UNICO",
        return_code=25,
        logs=["falha no envio de e-mail\n"],
        artifacts_json=None,
        duration_seconds=1.0,
    )

    assert execucao is not None
    assert execucao.status == EXECUTION_STATUS_ERROR


@pytest.mark.integracao
def test_finalizacao_preserva_parcial_com_dois_canais(db_session: Session) -> None:
    auto = models.Automation(
        name="Canal Duplo",
        script_path="./cd.ps1",
        notification_channels="email,whatsapp",
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_CANAL_DUPLO",
            automation_id=auto.id,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    execucao = complete_process_execution(
        db_session,
        "EXEC_CANAL_DUPLO",
        return_code=24,
        logs=["falha no WhatsApp\n"],
        artifacts_json=None,
        duration_seconds=1.0,
    )

    assert execucao is not None
    assert execucao.status == EXECUTION_STATUS_PARTIAL


@pytest.mark.unitario
def test_mt02_e_o_caso_real_de_canal_unico() -> None:
    """Âncora do achado: se MT-02 ganhar um segundo canal, isto passa a ser
    apenas defesa em profundidade — e o teste avisa que o cenário mudou."""
    manifesto = os.path.join(
        _RAIZ, "Montagem de Terceirizados", "automation.manifest.json"
    )
    with open(manifesto, encoding="utf-8") as arquivo:
        canais = json.load(arquivo)["channels"]

    assert canais == ["email"], (
        "MT-02 deixou de ser canal único. Revise se o exit 25 ainda deve ser "
        f"ERROR para ela; canais atuais: {canais}"
    )

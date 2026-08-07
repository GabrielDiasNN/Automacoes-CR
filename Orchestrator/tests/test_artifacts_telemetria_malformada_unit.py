"""Regressão do achado de revisão (severidade MÉDIA) do PR #29.

`GET /executions/{exec_id}/artifacts` ganhou `response_model=
ExecutionArtifactsResponse` (`artifacts: list[str]`). A coluna
`Execution.artifacts` tem dois escritores: `worker.scan_for_artifacts`
(sempre produz `list[str]`) e `POST /telemetry/end/{exec_id}`, cujo
`ExecutionTelemetryEnd.artifacts` era `str | None` sem validação de forma —
qualquer JSON válido (dict, lista com não-string) entrava no banco. Antes do
`response_model`, o endpoint de leitura devolvia esse valor cru com 200;
depois, o FastAPI falha a validação da resposta e devolve 500 — uma
regressão de disponibilidade para dado de telemetria externa malformado.

Duas correções, defesa em profundidade:
- `list_artifacts` trata JSON que não é `list[str]` como o mesmo fallback de
  lista vazia já usado para JSON inválido (em vez de deixar o FastAPI
  quebrar a validação do response_model).
- `ExecutionTelemetryEnd.artifacts` ganha `field_validator` que rejeita na
  escrita (422) um JSON que não seja lista de strings, para o dado malformado
  nem chegar a entrar no banco.
"""

import pytest
from app import models
from app.timezone import get_now_local
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _criar_execucao(
    db_session: Session, exec_id: str, artifacts_raw: str | None
) -> None:
    auto = models.Automation(name=f"Auto {exec_id}", script_path="./x.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id=exec_id,
            automation_id=auto.id,
            status="SUCCESS",
            started_at=get_now_local(),
            artifacts=artifacts_raw,
        )
    )
    db_session.commit()


@pytest.mark.integracao
@pytest.mark.parametrize(
    "artifacts_raw",
    ['{"file": "x"}', '["a", 123]', "not json"],
    ids=["dict", "lista_com_nao_string", "json_invalido"],
)
def test_list_artifacts_tolera_valor_malformado_de_telemetria_externa(
    client: TestClient, db_session: Session, artifacts_raw: str
) -> None:
    """Antes retornava 200 com o valor cru; a regressão do response_model
    trocaria isso por 500. A correção deve manter 200 com fallback []."""
    _criar_execucao(db_session, "ART_MALFORMADO", artifacts_raw)

    resposta = client.get(
        "/api/executions/ART_MALFORMADO/artifacts", headers=AUTH_HEADERS
    )

    assert resposta.status_code == 200
    assert resposta.json()["artifacts"] == []


@pytest.mark.integracao
def test_list_artifacts_continua_servindo_lista_valida(
    client: TestClient, db_session: Session
) -> None:
    """Guarda: a correção não pode quebrar o caminho feliz (worker real)."""
    _criar_execucao(db_session, "ART_VALIDO", '["relatorio.pdf", "dados.xlsx"]')

    resposta = client.get("/api/executions/ART_VALIDO/artifacts", headers=AUTH_HEADERS)

    assert resposta.status_code == 200
    assert resposta.json()["artifacts"] == ["relatorio.pdf", "dados.xlsx"]


@pytest.mark.integracao
@pytest.mark.parametrize(
    "artifacts_payload",
    ['{"file": "x"}', '["a", 123]', "not json"],
    ids=["dict", "lista_com_nao_string", "json_invalido"],
)
def test_telemetry_end_recusa_artifacts_malformado(
    client: TestClient, db_session: Session, artifacts_payload: str
) -> None:
    """Defesa em profundidade: rejeitar na escrita (422) em vez de deixar o
    dado malformado entrar no banco e só falhar depois, na leitura."""
    auto = models.Automation(name="Tel Artifacts", script_path="./tel.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="TEL_ARTIFACTS",
            automation_id=auto.id,
            status="RUNNING",
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    resposta = client.post(
        "/api/executions/telemetry/end/TEL_ARTIFACTS",
        json={"status": "SUCCESS", "exit_code": 0, "artifacts": artifacts_payload},
        headers=AUTH_HEADERS,
    )

    assert resposta.status_code == 422

    execucao = db_session.query(models.Execution).filter_by(id="TEL_ARTIFACTS").first()
    assert execucao is not None
    assert execucao.artifacts is None


@pytest.mark.integracao
def test_telemetry_end_aceita_lista_valida_de_strings(
    client: TestClient, db_session: Session
) -> None:
    """Guarda: a validação não pode quebrar o caminho feliz da telemetria."""
    auto = models.Automation(name="Tel Artifacts OK", script_path="./tel.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="TEL_ARTIFACTS_OK",
            automation_id=auto.id,
            status="RUNNING",
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    resposta = client.post(
        "/api/executions/telemetry/end/TEL_ARTIFACTS_OK",
        json={
            "status": "SUCCESS",
            "exit_code": 0,
            "artifacts": '["saida.csv"]',
        },
        headers=AUTH_HEADERS,
    )

    assert resposta.status_code == 200

    listagem = client.get(
        "/api/executions/TEL_ARTIFACTS_OK/artifacts", headers=AUTH_HEADERS
    )
    assert listagem.status_code == 200
    assert listagem.json()["artifacts"] == ["saida.csv"]

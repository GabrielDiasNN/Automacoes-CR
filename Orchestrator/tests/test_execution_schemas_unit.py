"""Testes unitários de app/schemas/executions.py (ExecutionResponse/ExecutionSummary).

Regressão da consolidação de ExecutionOperatorFields (achado #15 da
revisão arquitetural): trava o contrato de campos que antes eram
declarados duas vezes, para uma futura edição em uma classe não silenciar
a outra.
"""

from app.schemas.executions import (
    ExecutionOperatorFields,
    ExecutionResponse,
    ExecutionSummary,
)

OPERATOR_FIELDS = {
    "operator_attention_required",
    "operator_severity",
    "operator_score",
    "operator_reason_summary",
    "operator_action_code",
    "operator_action_label",
    "operator_action_hint",
    "requeue_allowed",
    "requeue_block_reason",
    "stop_allowed",
    "related_execution_id",
    "related_execution_status",
    "related_queue_group",
}


def test_execution_operator_fields_declara_exatamente_os_13_campos() -> None:
    assert set(ExecutionOperatorFields.model_fields) == OPERATOR_FIELDS


def test_execution_response_herda_todos_os_campos_de_operador() -> None:
    assert OPERATOR_FIELDS <= set(ExecutionResponse.model_fields)


def test_execution_summary_herda_todos_os_campos_de_operador() -> None:
    assert OPERATOR_FIELDS <= set(ExecutionSummary.model_fields)


def test_execution_summary_nao_expoe_campos_internos_do_worker() -> None:
    """ExecutionSummary é a view leve de listagem: claimed_at/worker_instance_id/
    worker_pid continuam exclusivos de ExecutionResponse (detalhe), não uma
    omissão acidental da consolidação."""
    internos = {"claimed_at", "worker_instance_id", "worker_pid"}
    assert internos <= set(ExecutionResponse.model_fields)
    assert not internos & set(ExecutionSummary.model_fields)


def test_execution_response_e_summary_tem_o_mesmo_default_dos_campos_de_operador() -> (
    None
):
    """Os defaults do mixin são os mesmos herdados pelas duas classes —
    garante que nenhuma delas sobrescreveu um default silenciosamente."""
    # pylint: disable=unsubscriptable-object
    for field_name in OPERATOR_FIELDS:
        default_response = ExecutionResponse.model_fields[field_name].default
        default_summary = ExecutionSummary.model_fields[field_name].default
        default_mixin = ExecutionOperatorFields.model_fields[field_name].default
        assert default_response == default_mixin
        assert default_summary == default_mixin

"""Regressoes de integridade de schema do Orchestrator."""

from fastapi.testclient import TestClient

from app import models as _models  # pylint: disable=unused-import
from app.database import Base, validate_database_schema

assert _models  # registra tabelas no Base.metadata antes da validacao de schema


def test_validate_database_schema_passes_for_current_models(
    client: TestClient,  # pylint: disable=unused-argument
) -> None:
    result = validate_database_schema()

    assert result["valid"] is True
    assert not result["missing_tables"]
    assert not result["missing_columns"]


def test_orm_schema_covers_execution_queue_contract() -> None:
    # Deriva o schema do ORM (mesma fonte que validate_database_schema)
    schema = {
        t_name: {col.name for col in table.columns}
        for t_name, table in Base.metadata.tables.items()
        if t_name != "alembic_version"
    }
    assert {"status", "priority", "started_at"}.issubset(schema["executions"])
    assert {"enabled", "schedule", "script_path"}.issubset(schema["automations"])
    assert {"retry_count", "max_retries", "failure_reason", "recovery_action"}.issubset(
        schema["executions"]
    )
    assert {"queue_group", "cooldown_minutes", "max_retries"}.issubset(
        schema["automations"]
    )

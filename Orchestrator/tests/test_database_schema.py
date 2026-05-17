# pylint: disable=all
# mypy: ignore-errors
"""Regressoes de integridade de schema do Orchestrator."""

from app.database import EXPECTED_SCHEMA, validate_database_schema


def test_validate_database_schema_passes_for_current_models(client):
    result = validate_database_schema()

    assert result["valid"] is True
    assert result["missing_tables"] == []
    assert result["missing_columns"] == {}


def test_expected_schema_covers_execution_queue_contract():
    assert {"status", "priority", "started_at"}.issubset(EXPECTED_SCHEMA["executions"])
    assert {"enabled", "schedule", "script_path"}.issubset(EXPECTED_SCHEMA["automations"])


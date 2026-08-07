"""Regressão do achado #18 (design): endpoints de leitura sem `response_model`
retornavam `dict[str, Any]`/`list[dict]` cru, sem contrato tipado no OpenAPI,
destoando do resto da API. Verifica que os 5 endpoints agora declaram um
schema nomeado (via `$ref`), não um objeto genérico.

`get_uptime` e `wait_for_task` (`Orchestrator/app/routers/system.py`) ficaram
de fora da varredura original e foram corrigidos em revisão de PR posterior
(severidade baixa) — mesmo padrão, cobertos abaixo.
"""

from typing import Any

from fastapi.testclient import TestClient


def _response_schema(openapi: dict[str, Any], path: str, method: str = "get") -> Any:
    operation = openapi["paths"][path][method]
    content = operation["responses"]["200"]["content"]["application/json"]
    return content["schema"]


def _resolve_ref_or_array_ref(schema: dict[str, Any]) -> str:
    """Devolve o nome do schema referenciado, seja objeto direto ou array de objetos."""
    if "$ref" in schema:
        return str(schema["$ref"])
    if schema.get("type") == "array":
        return str(schema["items"]["$ref"])
    raise AssertionError(f"Schema sem $ref nomeado: {schema}")


def test_automation_overview_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(
        _response_schema(openapi, "/api/automations/{automation_id}/overview")
    )
    assert ref.endswith("AutomationOverviewResponse")


def test_automation_configs_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(
        _response_schema(openapi, "/api/automations/{auto_id}/configs")
    )
    assert ref.endswith("ManagedFileEntry")


def test_automation_scripts_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(
        _response_schema(openapi, "/api/automations/{auto_id}/scripts")
    )
    assert ref.endswith("ManagedFileEntry")


def test_execution_logs_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(
        _response_schema(openapi, "/api/executions/{exec_id}/logs")
    )
    assert ref.endswith("ExecutionLogsResponse")


def test_execution_artifacts_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(
        _response_schema(openapi, "/api/executions/{exec_id}/artifacts")
    )
    assert ref.endswith("ExecutionArtifactsResponse")


def test_system_uptime_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(_response_schema(openapi, "/api/system/uptime"))
    assert ref.endswith("SystemUptime")


def test_wait_for_task_declara_schema_nomeado(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    ref = _resolve_ref_or_array_ref(
        _response_schema(openapi, "/api/system/wait-for-task")
    )
    assert ref.endswith("WaitForTaskResponse")

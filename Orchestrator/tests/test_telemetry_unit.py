"""Testes unitarios para app.telemetry (setup opt-in de OpenTelemetry)."""

import logging
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from app import telemetry
from app.telemetry import get_tracer, setup_telemetry


@pytest.fixture(autouse=True)
def reset_telemetry_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    lgr = logging.getLogger("orchestrator")
    monkeypatch.setattr(lgr, "handlers", [])
    monkeypatch.setattr(lgr, "propagate", True)
    monkeypatch.setattr(lgr, "level", logging.NOTSET)
    monkeypatch.setattr(lgr, "disabled", False)


def test_setup_telemetry_sem_env_var_retorna_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    resultado = setup_telemetry(MagicMock())
    assert resultado is False


def test_setup_telemetry_com_env_var_false_retorna_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "false")
    resultado = setup_telemetry(MagicMock())
    assert resultado is False


def test_setup_telemetry_habilitado_sem_sdk_retorna_false_com_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(telemetry, "_otel_available", False)

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        resultado = setup_telemetry(MagicMock())

    assert resultado is False
    assert "opentelemetry-sdk não instalado" in caplog.text


def test_setup_telemetry_disponivel_sem_endpoint_retorna_true_com_log_memoria(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_otel_available", True)

    mock_trace = MagicMock()
    monkeypatch.setattr(telemetry, "trace", mock_trace, raising=False)

    mock_tracer_provider_cls = MagicMock()
    monkeypatch.setattr(
        telemetry, "TracerProvider", mock_tracer_provider_cls, raising=False
    )
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", MagicMock(), raising=False)

    mock_resource_module = MagicMock()
    mock_instrumentation_module = MagicMock()
    fake_modules: dict[str, Any] = {
        "opentelemetry.sdk.resources": mock_resource_module,
        "opentelemetry.instrumentation.fastapi": mock_instrumentation_module,
    }
    for nome, modulo in fake_modules.items():
        monkeypatch.setitem(sys.modules, nome, modulo)
    mock_resource_module.SERVICE_NAME = "service.name"
    mock_resource_module.Resource = MagicMock()

    with caplog.at_level(logging.INFO, logger="orchestrator"):
        resultado = setup_telemetry(MagicMock())

    assert resultado is True
    assert "traces em memória apenas" in caplog.text
    mock_trace.set_tracer_provider.assert_called_once()
    mock_instrumentation_module.FastAPIInstrumentor.instrument_app.assert_called_once()


def test_setup_telemetry_disponivel_com_endpoint_retorna_true_com_log_export(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_ENDPOINT", "http://collector:4317")
    monkeypatch.setattr(telemetry, "_otel_available", True)

    mock_trace = MagicMock()
    monkeypatch.setattr(telemetry, "trace", mock_trace, raising=False)
    monkeypatch.setattr(telemetry, "TracerProvider", MagicMock(), raising=False)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", MagicMock(), raising=False)

    mock_resource_module = MagicMock()
    mock_resource_module.SERVICE_NAME = "service.name"
    mock_resource_module.Resource = MagicMock()
    mock_exporter_module = MagicMock()
    mock_instrumentation_module = MagicMock()

    monkeypatch.setitem(
        sys.modules, "opentelemetry.sdk.resources", mock_resource_module
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        mock_exporter_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.instrumentation.fastapi",
        mock_instrumentation_module,
    )

    with caplog.at_level(logging.INFO, logger="orchestrator"):
        resultado = setup_telemetry(MagicMock())

    assert resultado is True
    assert "exportando traces para http://collector:4317" in caplog.text


def test_setup_telemetry_endpoint_configurado_mas_exporter_ausente_loga_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_ENDPOINT", "http://collector:4317")
    monkeypatch.setattr(telemetry, "_otel_available", True)

    mock_trace = MagicMock()
    monkeypatch.setattr(telemetry, "trace", mock_trace, raising=False)
    monkeypatch.setattr(telemetry, "TracerProvider", MagicMock(), raising=False)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", MagicMock(), raising=False)

    mock_resource_module = MagicMock()
    mock_resource_module.SERVICE_NAME = "service.name"
    mock_resource_module.Resource = MagicMock()
    mock_instrumentation_module = MagicMock()

    monkeypatch.setitem(
        sys.modules, "opentelemetry.sdk.resources", mock_resource_module
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        None,
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.instrumentation.fastapi",
        mock_instrumentation_module,
    )

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        resultado = setup_telemetry(MagicMock())

    assert resultado is True
    assert "opentelemetry-exporter-otlp" in caplog.text
    assert "não instalado" in caplog.text


def test_setup_telemetry_instrumentation_fastapi_ausente_loga_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_otel_available", True)

    mock_trace = MagicMock()
    monkeypatch.setattr(telemetry, "trace", mock_trace, raising=False)
    monkeypatch.setattr(telemetry, "TracerProvider", MagicMock(), raising=False)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", MagicMock(), raising=False)

    mock_resource_module = MagicMock()
    mock_resource_module.SERVICE_NAME = "service.name"
    mock_resource_module.Resource = MagicMock()

    monkeypatch.setitem(
        sys.modules, "opentelemetry.sdk.resources", mock_resource_module
    )
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.fastapi", None)

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        resultado = setup_telemetry(MagicMock())

    assert resultado is True
    assert "instrumentation-fastapi não instalado" in caplog.text


def test_setup_telemetry_excecao_generica_retorna_false_com_log_erro(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(telemetry, "_otel_available", True)

    def _levanta_erro(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("falha simulada no TracerProvider")

    monkeypatch.setattr(telemetry, "TracerProvider", _levanta_erro, raising=False)
    monkeypatch.setattr(telemetry, "trace", MagicMock(), raising=False)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", MagicMock(), raising=False)

    mock_resource_module = MagicMock()
    mock_resource_module.SERVICE_NAME = "service.name"
    mock_resource_module.Resource = MagicMock()

    monkeypatch.setitem(
        sys.modules, "opentelemetry.sdk.resources", mock_resource_module
    )

    with caplog.at_level(logging.ERROR, logger="orchestrator"):
        resultado = setup_telemetry(MagicMock())

    assert resultado is False
    assert "Falha ao configurar OpenTelemetry" in caplog.text


def test_get_tracer_sem_otel_disponivel_retorna_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telemetry, "_otel_available", False)
    resultado = get_tracer()
    assert resultado is None


def test_get_tracer_com_otel_disponivel_retorna_tracer_do_modulo_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telemetry, "_otel_available", True)
    mock_trace = MagicMock()
    mock_tracer = MagicMock()
    mock_trace.get_tracer.return_value = mock_tracer
    monkeypatch.setattr(telemetry, "trace", mock_trace, raising=False)

    resultado = get_tracer("meu-servico")

    assert resultado is mock_tracer
    mock_trace.get_tracer.assert_called_once_with("meu-servico")

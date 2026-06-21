# mypy: ignore-errors
# pylint: disable=import-outside-toplevel,import-error,broad-exception-caught
"""
OpenTelemetry — setup opt-in do Orchestrator (3.3/Fase 3).

Ativação: definir OTEL_ENABLED=true no .env.
Sem essa variável, este módulo é no-op e não adiciona overhead.

Quando ativo, instrumenta automaticamente o FastAPI e propaga
correlation_id (exec_id) como trace ID nos logs de subprocessos
(variável CORRELATION_ID já injetada por _build_subprocess_env).
"""

import logging
import os

logger = logging.getLogger("orchestrator")

_otel_available = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _otel_available = True
except ImportError:
    pass


def setup_telemetry(app) -> bool:
    """Instrumenta o app FastAPI com OpenTelemetry se OTEL_ENABLED=true.

    Retorna True se a instrumentação foi ativada, False se foi ignorada.
    """
    if os.environ.get("OTEL_ENABLED", "").lower() != "true":
        return False

    if not _otel_available:
        logger.warning(
            "OTEL_ENABLED=true mas opentelemetry-sdk não instalado. "
            "Adicione opentelemetry-sdk e opentelemetry-instrumentation-fastapi "
            "ao requirements.in para ativar o tracing."
        )
        return False

    try:
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource

        resource = Resource(
            attributes={
                SERVICE_NAME: os.environ.get(
                    "OTEL_SERVICE_NAME", "automacoes-orchestrator"
                ),
            }
        )
        provider = TracerProvider(resource=resource)

        endpoint = os.environ.get("OTEL_EXPORTER_ENDPOINT", "")
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
                )
                logger.info("OTEL: exportando traces para %s", endpoint)
            except ImportError:
                logger.warning(
                    "OTEL_EXPORTER_ENDPOINT configurado mas opentelemetry-exporter-otlp "
                    "não instalado. Tracing ativo apenas em memória."
                )
        else:
            logger.info(
                "OTEL: OTEL_EXPORTER_ENDPOINT não configurado — traces em memória apenas."
            )

        trace.set_tracer_provider(provider)

        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
            logger.info("OTEL: FastAPI instrumentado com sucesso.")
        except ImportError:
            logger.warning(
                "opentelemetry-instrumentation-fastapi não instalado. "
                "Instrumentação automática de rotas desabilitada."
            )

        return True

    except Exception as exc:
        logger.error("Falha ao configurar OpenTelemetry: %s", exc)
        return False


def get_tracer(name: str = "orchestrator"):
    """Retorna um tracer OpenTelemetry (no-op se OTEL não ativo)."""
    if not _otel_available:
        return None
    return trace.get_tracer(name)

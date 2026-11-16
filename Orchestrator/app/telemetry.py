# RESIDUAL (import-outside-toplevel): os pacotes OpenTelemetry sao opcionais e so
# sao importados quando OTEL_ENABLED=true; o import tardio e o contrato (testes
# injetam modulos em sys.modules antes de chamar setup_telemetry).
# pylint: disable=import-outside-toplevel
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
from typing import Any

logger = logging.getLogger("orchestrator")
logger.propagate = True

_otel_available = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _otel_available = True
except ImportError:
    pass


def setup_telemetry(app: Any) -> bool:
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
        try:
            from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        except ImportError as exc:
            # Mesmo tratamento do bloco externo: falha de configuracao, nao de rota.
            logger.error("Falha ao configurar OpenTelemetry: %s", exc)
            return False

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

    # Residual: setup_telemetry e chamado sem try externo no import de main.py
    # (startup da API). A configuracao do SDK e do exporter OTLP e de terceiros e
    # pode levantar tipos nao enumeraveis; se escapasse, a API nao subiria por
    # causa de um recurso opcional (OTEL_ENABLED). Fixado por
    # tests/test_telemetry_unit.py::test_setup_telemetry_excecao_generica_retorna_false_com_log_erro.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Falha ao configurar OpenTelemetry: %s", exc)
        return False


def get_tracer(name: str = "orchestrator") -> Any:
    """Retorna um tracer OpenTelemetry (no-op se OTEL não ativo)."""
    if not _otel_available:
        return None
    return trace.get_tracer(name)

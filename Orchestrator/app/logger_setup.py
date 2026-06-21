# mypy: ignore-errors
"""Shared structured JSON logging factory for Orchestrator and Worker (Pilar L)."""

import json
import logging
import os
from logging.handlers import RotatingFileHandler


class OrchestratorJsonFormatter(logging.Formatter):
    """JSON formatter shared by the API and Worker processes.

    When use_context_vars=True (API process), reads request_id / exec_id /
    automation_name from contextvars set by RequestIdMiddleware.
    When False (Worker process), reads the same fields from LogRecord attributes.
    """

    def __init__(self, component: str, use_context_vars: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._component = component
        self._use_context_vars = use_context_vars

    def format(self, record: logging.LogRecord) -> str:
        # pylint: disable=import-outside-toplevel,relative-beyond-top-level
        from .security import (
            sanitize_log_payload,
        )

        if self._use_context_vars:
            from .middleware import (
                automation_name_var,
                exec_id_var,
                request_id_var,
            )

            automation_name = automation_name_var.get("")
            exec_id = exec_id_var.get("")
            request_id = getattr(record, "request_id", request_id_var.get("SYSTEM"))
        else:
            automation_name = getattr(record, "automation_name", "")
            exec_id = getattr(record, "correlation_id", "")
            request_id = getattr(record, "request_id", "SYSTEM")

        doc = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "component": self._component,
            "environment": os.environ.get("ENVIRONMENT", "PRD"),
            "automation_name": automation_name,
            "exec_id": exec_id,
            "request_id": request_id,
            "message": sanitize_log_payload(record.getMessage()),
        }

        if hasattr(record, "context"):
            doc["context"] = sanitize_log_payload(record.context)

        if record.exc_info:
            doc["exception"] = sanitize_log_payload(
                self.formatException(record.exc_info)
            )

        return json.dumps(doc)


def setup_json_logger(
    name: str,
    log_file: str,
    component: str,
    use_context_vars: bool = False,
    configure_root: bool = False,
) -> logging.Logger:
    """Create or retrieve a named logger with rotating JSON + console handlers.

    Args:
        name: Logger name (e.g. "orchestrator", "worker").
        log_file: Absolute path to the rotating log file.
        component: Value for the "component" JSON field.
        use_context_vars: If True, read context from FastAPI contextvars (API process).
        configure_root: If True, also apply handlers to the root logger (Worker pattern).
    """
    json_handler = RotatingFileHandler(
        log_file, maxBytes=50 * 1024 * 1024, backupCount=7, encoding="utf-8"
    )
    json_handler.setFormatter(
        OrchestratorJsonFormatter(
            component=component,
            use_context_vars=use_context_vars,
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    if configure_root:
        logging.root.setLevel(logging.INFO)
        logging.root.addHandler(json_handler)
        logging.root.addHandler(console_handler)

    logger = logging.getLogger(name)
    if not configure_root:
        logger.setLevel(logging.INFO)
        logger.addHandler(json_handler)
        logger.addHandler(console_handler)

    return logger

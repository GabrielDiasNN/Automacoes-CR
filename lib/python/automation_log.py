"""Logging das automacoes de dominio.

Contrato unico: docs/log-event.schema.json e docs/logging-standard.md.

Duas modalidades, decididas pela env `HUB_LOG_STRUCTURED`:

* **estruturada** (`HUB_LOG_STRUCTURED=1`, exportada pelo `run.ps1` da automacao
  ja migrada): cada chamada de `log(...)` emite UMA linha JSON em **stdout**,
  no envelope do schema. Nada vai para stderr por padrao.
* **legada** (env ausente): mantem o comportamento historico -- linha humana
  `[ts] [tag] [LEVEL] [ExecId:...] msg` em **stderr**. Preserva as automacoes
  ainda nao migradas sem nenhuma alteracao de saida.

`make_logger` continua com a mesma assinatura de chamada usada hoje
(`log(msg, level, exec_id)`); os parametros `step`/`event`/`**fields` sao
aditivos.
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from log_masking import mask_sensitive

_LEVELS = {"INFO", "WARN", "ERRO", "DEBUG"}
_ALLOWED_EVENTS = {
    "execution.start",
    "execution.end",
    "step.start",
    "step.end",
    "retry.attempt",
    "log",
}


def ensure_utf8_streams() -> None:
    """Reconfigura stdout/stderr para UTF-8 quando o objeto suportar.

    `hasattr(..., "reconfigure")` e a guarda correta: verifica exatamente o
    metodo que sera chamado. Chamar antes de qualquer escrita em stdout/stderr.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def structured_logging_enabled() -> bool:
    return os.environ.get("HUB_LOG_STRUCTURED", "").strip() in {"1", "true", "True"}


def _now_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_level(level: str) -> str:
    up = (level or "INFO").upper()
    if up in {"ERROR", "ERRO"}:
        return "ERRO"
    if up in {"WARN", "WARNING"}:
        return "WARN"
    if up == "DEBUG":
        return "DEBUG"
    return "INFO" if up not in _LEVELS else up


def new_trace_id(slug: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{slug}-{stamp}-{random.randint(0, 0xFFFF):04x}"


def resolve_trace_id(slug: str) -> str:
    inherited = os.environ.get("HUB_TRACE_ID", "").strip()
    return inherited or new_trace_id(slug)


def emit_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    event: str,
    level: str,
    message: str,
    *,
    automation: str,
    exec_id: str,
    trace_id: str,
    step: str | None = None,
    step_name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emite um evento JSON no envelope do schema em stdout."""
    if event not in _ALLOWED_EVENTS:
        event = "log"
    evt: dict[str, Any] = {
        "ts": _now_ts(),
        "level": _normalize_level(level),
        "component": "python_domain",
        "event": event,
        "automation": automation,
        "exec_id": exec_id,
        "trace_id": trace_id,
        "message": mask_sensitive(message),
    }
    if step:
        evt["step"] = step
    if step_name:
        evt["step_name"] = step_name
    if extra:
        evt.update(extra)
    sys.stdout.write(json.dumps(evt, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def make_logger(tag: str) -> Callable[..., None]:
    """Retorna `log(message, level="INFO", exec_id=None, *, step=None, event="log", **fields)`.

    `tag` continua sendo o rotulo curto (ex.: "ORB-EXTRACT"): usado no rastro
    humano legado e como fallback do nome da automacao quando `HUB_AUTOMATION`
    nao esta no ambiente.
    """
    structured = structured_logging_enabled()
    automation = os.environ.get("HUB_AUTOMATION", "").strip() or tag
    env_exec_id = os.environ.get("HUB_EXEC_ID", "").strip()
    env_step = os.environ.get("HUB_STEP", "").strip() or None
    trace_id = resolve_trace_id(tag.lower())

    def log(
        message: str,
        level: str = "INFO",
        exec_id: str | None = None,
        *,
        step: str | None = None,
        event: str = "log",
        **fields: Any,
    ) -> None:
        resolved_exec_id = exec_id or env_exec_id or "manual"
        resolved_step = step or env_step
        if structured:
            emit_event(
                event,
                level,
                message,
                automation=automation,
                exec_id=resolved_exec_id,
                trace_id=trace_id,
                step=resolved_step,
                extra=fields or None,
            )
        else:
            ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            sys.stderr.write(
                f"[{ts}] [{tag}] [{level}] [ExecId:{resolved_exec_id}] {message}\n"
            )
            sys.stderr.flush()

    return log

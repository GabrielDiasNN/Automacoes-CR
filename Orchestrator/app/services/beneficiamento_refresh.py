# pylint: disable=broad-exception-caught
"""Disparo isolado do refresh do Beneficiamento.

Executa o runner do domínio em subprocesso (Oracle nunca é aberto no processo
web do Orquestrador), reaproveitando o entrypoint testado. Usado tanto pelos
jobs de refresh ao vivo do scheduler quanto pelo endpoint POST /refresh.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Any

from ..runtime import get_project_root  # pylint: disable=relative-beyond-top-level

logger = logging.getLogger("orchestrator")

_ENTRYPOINT_REL = os.path.join(
    "Produção Beneficimento", "analise_producao_diaria_beneficiamento.py"
)

# O runner tem orçamento interno de ~19s (wall-clock) + corte do Oracle em ~20s.
# A folga cobre apenas startup do interpretador e escrita atômica do snapshot.
_SUBPROCESS_TIMEOUT_SECONDS = 45


def _runner_python() -> str:
    return os.environ.get("BENEFICIAMENTO_PYTHON") or sys.executable


def _parse_runner_output(raw_text: str | None) -> dict[str, Any] | None:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return None
    for line in reversed(raw_text.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{"):
            try:
                parsed: Any = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def run_beneficiamento_refresh(period: str) -> dict[str, Any]:
    """Roda o runner para o período e devolve o payload JSON do runner.

    Em falha, devolve ``{"status": "error", "period": ..., "detail": ...}``.
    """
    root = get_project_root()
    entrypoint = os.path.join(root, _ENTRYPOINT_REL)

    try:
        proc = subprocess.run(
            [_runner_python(), entrypoint, "--period", period],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Refresh do beneficiamento (%s) excedeu %ss.",
            period,
            _SUBPROCESS_TIMEOUT_SECONDS,
        )
        return {
            "status": "error",
            "period": period,
            "detail": f"Refresh excedeu {_SUBPROCESS_TIMEOUT_SECONDS}s.",
        }
    except Exception as exc:
        logger.error(
            "Falha ao disparar refresh do beneficiamento (%s): %s", period, exc
        )
        return {"status": "error", "period": period, "detail": str(exc)}

    payload = _parse_runner_output(proc.stdout) or _parse_runner_output(proc.stderr)
    if payload is None:
        detail = (proc.stderr or proc.stdout or "Saída vazia do runner.").strip()[:500]
        logger.error(
            "Refresh do beneficiamento (%s) sem JSON válido: %s", period, detail
        )
        return {"status": "error", "period": period, "detail": detail}

    logger.info(
        "Refresh do beneficiamento (%s): status=%s",
        period,
        payload.get("status"),
    )
    return payload

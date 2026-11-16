"""Convenção de ids dos jobs do APScheduler (``job_<automation_id>_...``).

Fica fora de ``scheduler_runtime`` para que os coletores de diagnóstico possam
usar o parser sem importar o agendador inteiro (evita ciclo de import).
"""

from __future__ import annotations


def extract_automation_id_from_job(job_id: str) -> int | None:
    if not job_id.startswith("job_"):
        return None
    parts = job_id.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None

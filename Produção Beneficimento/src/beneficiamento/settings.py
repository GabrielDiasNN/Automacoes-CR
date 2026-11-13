"""Configuracoes centrais do dominio Beneficiamento."""

# pylint: disable=missing-class-docstring

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path

logger = logging.getLogger(__name__)

DOMAIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = DOMAIN_ROOT.parent
# Biblioteca compartilhada (`oracle_session`), resolvida pelo próprio pacote.
LIB_PYTHON_DIR = REPO_ROOT / "lib" / "python"
# SQL de RUNTIME: o runner lê `bnf_producao_beneficiamento_detalhado.sql` daqui.
# O acervo de consultas de referência vive em `docs/oracle-schema/consultas/` e
# não é lido pelo runner. Mudar o nome do arquivo exige ajustar `_PERIOD_CONFIGS`
# (protegido por `test_beneficiamento_sql_template_unit.py`).
SQL_TEMPLATE_DIR = DOMAIN_ROOT / "sql" / "templates"
SNAPSHOT_DIR = DOMAIN_ROOT / "snapshots" / "latest"
SNAPSHOT_ARCHIVE_DIR = DOMAIN_ROOT / "snapshots" / "archive"

PERIOD_ORDER = ("diario", "mensal")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Valor inválido em %s=%r; usando padrão %s.", name, raw, default)
        return default
    if value <= 0:
        logger.warning(
            "Valor não positivo em %s=%r; usando padrão %s.", name, raw, default
        )
        return default
    return value


ORACLE_CALL_TIMEOUT_MS = _int_env("BENEFICIAMENTO_ORACLE_TIMEOUT_MS", 18000)
WALL_CLOCK_BUDGET_SECONDS = _int_env("BENEFICIAMENTO_WALL_CLOCK_SECONDS", 19)
FETCH_ARRAY_SIZE = _int_env("BENEFICIAMENTO_FETCH_ARRAY_SIZE", 1000)
FETCH_BATCH_SIZE = _int_env("BENEFICIAMENTO_FETCH_BATCH_SIZE", 5000)


@dataclass(frozen=True)
class PeriodConfig:
    key: str
    label: str
    sql_template: str
    max_age_minutes: int


_INTERVAL_ENV_BY_PERIOD: dict[str, tuple[str, int]] = {
    # Mantém paridade com os defaults de `scheduler_runtime.register_beneficiamento_live_jobs`.
    "diario": ("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", 90),
    "mensal": ("BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS", 600),
}

_PERIOD_CONFIGS = {
    # A validade efetiva (`max_age_minutes`) é recalculada em `get_period_config` a
    # partir de BENEFICIAMENTO_LIVE_INTERVAL_SECONDS e
    # BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS com folga mínima de 15 min (ou ~1/12
    # do intervalo): para 1800 s (30 min) resulta em 45 min; para 86400 s (24 h),
    # resulta em 1560 min (26 h).
    "diario": PeriodConfig(
        key="diario",
        label="Diario",
        sql_template="bnf_producao_beneficiamento_detalhado.sql",
        max_age_minutes=45,
    ),
    "mensal": PeriodConfig(
        key="mensal",
        label="Mensal",
        sql_template="bnf_producao_beneficiamento_detalhado.sql",
        max_age_minutes=1560,
    ),
}


def _compute_max_age_minutes(period: str) -> int:
    env_name, default_seconds = _INTERVAL_ENV_BY_PERIOD[period]
    interval_seconds = _int_env(env_name, default_seconds)
    interval_minutes = math.ceil(interval_seconds / 60)
    margin_minutes = max(15, math.ceil(interval_minutes / 12))
    return interval_minutes + margin_minutes


def get_period_config(period: str) -> PeriodConfig:
    normalized = period.strip().lower()
    try:
        base = _PERIOD_CONFIGS[normalized]
    except KeyError as exc:
        raise ValueError(f"Periodo de Beneficiamento invalido: {period}") from exc
    return replace(base, max_age_minutes=_compute_max_age_minutes(normalized))

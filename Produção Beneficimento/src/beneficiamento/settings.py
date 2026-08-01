"""Configuracoes centrais do dominio Beneficiamento."""

# pylint: disable=missing-class-docstring

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = DOMAIN_ROOT.parent
SQL_TEMPLATE_DIR = DOMAIN_ROOT / "sql" / "templates"
SNAPSHOT_DIR = DOMAIN_ROOT / "snapshots" / "latest"
SNAPSHOT_ARCHIVE_DIR = DOMAIN_ROOT / "snapshots" / "archive"

PERIOD_ORDER = ("diario", "mensal")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


ORACLE_CALL_TIMEOUT_MS = _int_env("BENEFICIAMENTO_ORACLE_TIMEOUT_MS", 18000)
WALL_CLOCK_BUDGET_SECONDS = _int_env("BENEFICIAMENTO_WALL_CLOCK_SECONDS", 19)
FETCH_ARRAY_SIZE = _int_env("BENEFICIAMENTO_FETCH_ARRAY_SIZE", 1000)
FETCH_BATCH_SIZE = _int_env("BENEFICIAMENTO_FETCH_BATCH_SIZE", 5000)


@dataclass(frozen=True)
class PeriodConfig:
    key: str
    label: str
    sql_template: str
    refresh_minutes: int
    max_age_minutes: int


_PERIOD_CONFIGS = {
    # Cadência ao vivo: o diário é reprocessado em loop curto (~90s) pelo
    # Orquestrador, então a idade operacional aceitável é baixa.
    "diario": PeriodConfig(
        key="diario",
        label="Diario",
        sql_template="detalhado.sql",
        refresh_minutes=2,
        max_age_minutes=5,
    ),
    "mensal": PeriodConfig(
        key="mensal",
        label="Mensal",
        sql_template="detalhado.sql",
        refresh_minutes=10,
        max_age_minutes=30,
    ),
}


def get_period_config(period: str) -> PeriodConfig:
    normalized = period.strip().lower()
    try:
        return _PERIOD_CONFIGS[normalized]
    except KeyError as exc:
        raise ValueError(f"Periodo de Beneficiamento invalido: {period}") from exc

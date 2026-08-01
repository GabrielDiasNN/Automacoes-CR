"""Repositorio de SQLs parametrizadas do Beneficiamento."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .settings import PERIOD_ORDER, SQL_TEMPLATE_DIR, get_period_config


def load_sql_template(period: str, sql_dir: Path = SQL_TEMPLATE_DIR) -> str:
    config = get_period_config(period)
    path = sql_dir / config.sql_template
    if not path.exists():
        raise FileNotFoundError(f"Template SQL nao encontrado: {path}")
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def period_window(period: str, reference: date | None = None) -> tuple[date, date]:
    current = reference or date.today()
    normalized = period.strip().lower()
    if normalized == "diario":
        return current, current + timedelta(days=1)
    if normalized == "semanal":
        start = current - timedelta(days=current.weekday())
        return start, start + timedelta(days=7)
    if normalized == "mensal":
        start = current.replace(day=1)
        end = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, end
    if normalized == "anual":
        return date(current.year, 1, 1), date(current.year + 1, 1, 1)
    if normalized not in PERIOD_ORDER:
        raise ValueError(f"Periodo de Beneficiamento invalido: {period}")
    raise ValueError(f"Janela nao configurada para periodo: {period}")


def bind_parameters(period: str, reference: date | None = None) -> dict[str, Any]:
    start, end = period_window(period, reference)
    return {
        "dt_inicio": datetime.combine(start, time.min),
        "dt_fim": datetime.combine(end, time.min),
    }


def apply_rownum_limit(sql: str, max_rows: int | None) -> str:
    """Envelopa a query com limite de linhas.

    `sql` vem de `load_sql_template`, que lê um arquivo de `SQL_TEMPLATE_DIR`
    escolhido por `get_period_config` — nome fixo por período validado, não
    caminho de request. `max_rows` é coagido a `int`. Nenhuma das duas partes
    é entrada de usuário.
    """
    if not max_rows or max_rows <= 0:
        return sql
    return f"SELECT * FROM (\n{sql}\n) WHERE ROWNUM <= {int(max_rows)}"  # nosec B608


def validate_static_sql(sql: str) -> list[str]:
    issues: list[str] = []
    upper_sql = sql.upper()
    if "SELECT *" in upper_sql:
        issues.append("SELECT * nao permitido em template operacional.")
    if "TRUNC(SYSDATE" in upper_sql:
        issues.append(
            "Janela hardcoded com SYSDATE encontrada; use binds :dt_inicio/:dt_fim."
        )
    if ":DT_INICIO" not in upper_sql or ":DT_FIM" not in upper_sql:
        issues.append("Template deve possuir binds :dt_inicio e :dt_fim.")
    return issues

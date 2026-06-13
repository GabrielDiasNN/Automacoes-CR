"""Coercoes de tipo seguras e deterministas do dominio Beneficiamento.

Fonte unica para conversoes que antes eram reimplementadas em analytics.py,
historico_db.py, overview_v1.py e quality.py. Todas sao tolerantes a None e a
valores malformados (nunca levantam excecao).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Sentinela usada em chaves de agrupamento quando o valor e ausente/vazio.
MISSING_TEXT = "SEM_VALOR"


def to_float(value: Any) -> float:
    """Converte para float aceitando virgula decimal; retorna 0.0 se invalido."""
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def safe_text(value: Any) -> str:
    """Texto normalizado para chaves de agrupamento; ausente vira ``SEM_VALOR``."""
    if value is None:
        return MISSING_TEXT
    text = str(value).strip()
    return text or MISSING_TEXT


def safe_strip(value: Any) -> str:
    """Strip tolerante a None; ausente vira string vazia."""
    if value is None:
        return ""
    return str(value).strip()


def parse_iso_date(value: Any) -> date | None:
    """Extrai uma data ISO (YYYY-MM-DD) dos 10 primeiros caracteres; None se invalido."""
    if not value:
        return None
    raw = str(value).strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def round_or_zero(value: float | int | None, digits: int = 2) -> float:
    """Arredonda com fallback 0.0 para None."""
    if value is None:
        return 0.0
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0

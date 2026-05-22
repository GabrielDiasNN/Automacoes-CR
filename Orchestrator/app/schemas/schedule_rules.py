# pylint: disable=all
# mypy: ignore-errors
"""Regras compartilhadas para horários de agenda."""

from datetime import datetime, timedelta
from typing import Any


def parse_hhmm(value: str) -> tuple[int, int]:
    """Valida e quebra um horário no formato HH:MM."""
    if not isinstance(value, str):
        raise ValueError("Horário deve ser texto no formato HH:MM.")
    parts = value.split(":")
    if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
        raise ValueError("Horário deve estar no formato HH:MM.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Horário deve estar entre 00:00 e 23:59.")
    return hour, minute


def normalize_hhmm(
    value: Any,
    field_name: str,
    strict: bool,
    logger: Any,
) -> str | None:
    """Normaliza campo HH:MM opcional respeitando modo estrito/tolerante."""
    if not value:
        return None
    try:
        parse_hhmm(value)
        return value
    except Exception as exc:
        if strict:
            raise ValueError(f"{field_name} deve estar no formato HH:MM.") from exc
        logger.warning("%s inválido (%s). Ignorando campo.", field_name, value)
        return None


def first_interval_candidate(
    now: datetime,
    step_minutes: int,
    anchor_time: str | None = None,
) -> datetime:
    """Calcula o primeiro disparo futuro para agenda de intervalo."""
    if step_minutes < 1:
        step_minutes = 1

    if not anchor_time:
        return now + timedelta(minutes=step_minutes)

    try:
        hour, minute = parse_hhmm(anchor_time)
    except Exception:
        return now + timedelta(minutes=step_minutes)

    anchor_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if anchor_dt > now:
        return anchor_dt

    step_seconds = step_minutes * 60
    diff_seconds = (now - anchor_dt).total_seconds()
    multiples = int(diff_seconds // step_seconds) + 1
    return anchor_dt + timedelta(minutes=multiples * step_minutes)


def ui_day_to_python_weekday(day: int) -> int:
    """Converte dia da semana da UI (0=Dom, 1=Seg ... 6=Sab) para datetime (0=Seg ... 6=Dom)."""
    return (int(day) + 6) % 7

"""Testes unitários de app/services/execution_runtime.py (funções puras)."""

from datetime import timedelta

from app.services.execution_runtime import cooldown_remaining_minutes
from app.timezone import get_now_local

NOW = get_now_local()


def test_cooldown_remaining_minutes_sem_cooldown_configurado_retorna_none() -> None:
    assert cooldown_remaining_minutes(NOW - timedelta(minutes=1), None, NOW) is None
    assert cooldown_remaining_minutes(NOW - timedelta(minutes=1), 0, NOW) is None


def test_cooldown_remaining_minutes_sem_reference_time_retorna_none() -> None:
    assert cooldown_remaining_minutes(None, 15, NOW) is None


def test_cooldown_remaining_minutes_ainda_em_cooldown_retorna_minutos_restantes() -> (
    None
):
    reference = NOW - timedelta(minutes=5)
    assert cooldown_remaining_minutes(reference, 15, NOW) == 10.0


def test_cooldown_remaining_minutes_no_limiar_exato_retorna_none() -> None:
    reference = NOW - timedelta(minutes=15)
    assert cooldown_remaining_minutes(reference, 15, NOW) is None


def test_cooldown_remaining_minutes_ja_expirado_retorna_none() -> None:
    reference = NOW - timedelta(minutes=20)
    assert cooldown_remaining_minutes(reference, 15, NOW) is None

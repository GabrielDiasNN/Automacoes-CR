"""Testes unitários do tracking de saturação do pool de workers (worker.py)."""

# pylint: disable=protected-access

from unittest.mock import patch

import worker


def test_set_pool_saturation_atualiza_stats(reset_worker_globals: None) -> None:
    del reset_worker_globals
    worker.set_pool_saturation(42.5)
    assert worker.stats["pool_saturated_seconds"] == 42.5


def test_track_pool_saturation_inicia_streak_quando_saturado(
    reset_worker_globals: None,
) -> None:
    del reset_worker_globals
    with patch("worker.time.time", side_effect=[100.0, 100.0, 105.0]):
        started_at = worker._track_pool_saturation(True, None)
        assert started_at == 100.0
        assert worker.stats["pool_saturated_seconds"] == 0.0

        started_at = worker._track_pool_saturation(True, started_at)
        assert started_at == 100.0
        assert worker.stats["pool_saturated_seconds"] == 5.0


def test_track_pool_saturation_reseta_quando_deixa_de_saturar(
    reset_worker_globals: None,
) -> None:
    del reset_worker_globals
    worker.set_pool_saturation(30.0)
    started_at = worker._track_pool_saturation(False, 100.0)
    assert started_at is None
    assert worker.stats["pool_saturated_seconds"] == 0.0


def test_track_pool_saturation_nao_saturado_sem_streak_previo_nao_reseta_a_toa(
    reset_worker_globals: None,
) -> None:
    """Sem streak anterior (None), não há necessidade de zerar de novo."""
    del reset_worker_globals
    with patch("worker.set_pool_saturation") as mock_set:
        started_at = worker._track_pool_saturation(False, None)
    assert started_at is None
    mock_set.assert_not_called()

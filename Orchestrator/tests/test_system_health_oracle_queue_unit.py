"""Testes da sonda de saúde da fila Oracle: payload degradado e cache curto (D3)."""

import logging
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import psutil
import pytest
from app.schemas import WorkerStatus
from app.services import oracle_queue_health as oqh, system_runtime
from sqlalchemy.orm import Session

# Chaves do snapshot normal de oracle_queue (check_worker_liveness + "enabled").
CHAVES_SNAPSHOT_NORMAL = {
    "enabled",
    "alive",
    "reachable",
    "source",
    "age_seconds",
    "state",
    "oracle_ok",
    "version",
    "machine",
    "req_id",
    "pending_requests",
    "active_procs",
}
SNAPSHOT_SAUDAVEL: dict[str, Any] = {
    "enabled": True,
    "alive": True,
    "reachable": True,
    "source": "heartbeat",
    "oracle_ok": True,
}


@pytest.fixture(autouse=True)
def _cache_oracle_limpo() -> Iterator[None]:
    oqh.reset_oracle_queue_health_cache()
    yield
    oqh.reset_oracle_queue_health_cache()


def _sonda_que_falha() -> dict[str, Any]:
    raise ImportError("oracle_queue indisponivel")


def test_collect_oracle_queue_health_degrada_quando_sonda_levanta(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda_que_falha)

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        payload = oqh.collect_oracle_queue_health()

    assert payload["alive"] is False
    assert payload["enabled"] is True
    assert "ImportError" in payload["error"]
    assert "oracle_queue indisponivel" in payload["error"]
    assert set(payload) >= CHAVES_SNAPSHOT_NORMAL
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_collect_oracle_queue_health_degradado_fora_do_modo_queue_fica_desabilitado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda_que_falha)

    payload = oqh.collect_oracle_queue_health()

    # Sem modo queue a falha da sonda não pode virar "worker fora do ar".
    assert payload["enabled"] is False
    assert set(payload) >= CHAVES_SNAPSHOT_NORMAL


def test_collect_oracle_queue_health_nao_engole_erro_fora_das_falhas_de_sonda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _defeito() -> dict[str, Any]:
        raise KeyError("bug no chamador")

    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _defeito)

    # Só import/I/O viram degradado; defeito de programação continua visível.
    with pytest.raises(KeyError):
        oqh.collect_oracle_queue_health()


def test_build_health_payload_nao_levanta_quando_sonda_falha(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _sonda_smb_offline() -> dict[str, Any]:
        raise OSError("SMB offline")

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda_smb_offline)
    monkeypatch.setattr(system_runtime, "scheduler", MagicMock(running=True))
    monkeypatch.setattr(system_runtime, "get_db_size_mb", lambda: 1.0)
    monkeypatch.setattr(system_runtime, "get_wal_size_mb", lambda: 0.1)
    monkeypatch.setattr(psutil, "cpu_percent", lambda: 5.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MagicMock(percent=40.0))

    payload = system_runtime.build_health_payload(
        db_session, WorkerStatus(is_alive=True)
    )

    assert payload.status == "degraded"
    worker_payload = payload.oracle_queue_worker or {}
    assert worker_payload.get("alive") is False
    assert "OSError" in str(worker_payload.get("error"))


def test_collect_oracle_queue_health_cache_evita_nova_sonda_dentro_do_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def _sonda() -> dict[str, Any]:
        chamadas.append(1)
        return dict(SNAPSHOT_SAUDAVEL)

    relogio = [1000.0]
    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda)
    monkeypatch.setattr(oqh, "time", SimpleNamespace(monotonic=lambda: relogio[0]))

    assert oqh.collect_oracle_queue_health()["alive"] is True
    relogio[0] += 5.0
    assert oqh.collect_oracle_queue_health()["alive"] is True
    assert len(chamadas) == 1

    # Passado o TTL, a sonda roda de novo.
    relogio[0] += oqh.HEALTH_TTL_SECONDS
    oqh.collect_oracle_queue_health()
    assert len(chamadas) == 2


def test_collect_oracle_queue_health_use_cache_false_sonda_de_novo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def _sonda() -> dict[str, Any]:
        chamadas.append(1)
        return dict(SNAPSHOT_SAUDAVEL)

    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda)

    oqh.collect_oracle_queue_health()
    assert len(chamadas) == 1
    oqh.collect_oracle_queue_health(use_cache=False)
    assert len(chamadas) == 2


def test_reset_oracle_queue_health_cache_descarta_resultado_anterior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def _sonda() -> dict[str, Any]:
        chamadas.append(1)
        return dict(SNAPSHOT_SAUDAVEL)

    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda)

    oqh.collect_oracle_queue_health()
    oqh.reset_oracle_queue_health_cache()
    oqh.collect_oracle_queue_health()
    assert len(chamadas) == 2

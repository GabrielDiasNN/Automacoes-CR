"""Testes da sonda de saúde da fila Oracle: payload degradado e cache curto (D3)."""

import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import psutil
import pytest
from app.schemas import WorkerStatus
from app.services import oracle_queue_health as oqh, system_runtime
from sqlalchemy.orm import Session

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
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    oq = oqh.load_oracle_queue_module()
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DIR", str(tmp_path))
    snap_referencia = oq.collect_worker_health_snapshot()

    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda_que_falha)

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        payload = oqh.collect_oracle_queue_health()

    assert payload["alive"] is False
    assert payload["reachable"] is False
    assert payload["source"] == "error"
    assert payload["enabled"] is True
    assert "ImportError" in payload["error"]
    assert "oracle_queue indisponivel" in payload["error"]
    assert set(snap_referencia) <= set(payload)
    assert set(payload) - set(snap_referencia) <= {"error"}
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_collect_oracle_queue_health_degradado_fora_do_modo_queue_fica_desabilitado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oq = oqh.load_oracle_queue_module()
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    snap_referencia = oq.collect_worker_health_snapshot()

    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda_que_falha)

    payload = oqh.collect_oracle_queue_health()

    # Sem modo queue a falha da sonda não pode virar "worker fora do ar".
    assert payload["enabled"] is False
    assert payload["alive"] is None
    assert payload["reachable"] is None
    assert payload["source"] == "disabled"
    assert payload["error"] is None
    assert set(snap_referencia) <= set(payload)
    for chave in ("enabled", "alive", "reachable", "source"):
        assert payload[chave] == snap_referencia[chave]


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


def test_collect_oracle_queue_health_use_cache_false_nao_bloqueia_leitores_em_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relogio = [1000.0]
    probe_iniciada = threading.Event()
    liberar_probe = threading.Event()
    primeira = [True]

    def _sonda() -> dict[str, Any]:
        if primeira[0]:
            primeira[0] = False
            return dict(SNAPSHOT_SAUDAVEL, version="1.0")
        relogio[0] += 2.0  # tempo gasto dentro da sonda lenta
        probe_iniciada.set()
        assert liberar_probe.wait(timeout=3.0)
        return dict(SNAPSHOT_SAUDAVEL, version="2.0")

    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda)
    monkeypatch.setattr(oqh, "time", SimpleNamespace(monotonic=lambda: relogio[0]))

    assert oqh.collect_oracle_queue_health()["version"] == "1.0"

    resultado_bg: list[dict[str, Any]] = []
    t = threading.Thread(
        target=lambda: resultado_bg.append(
            oqh.collect_oracle_queue_health(use_cache=False)
        )
    )
    t.start()
    assert probe_iniciada.wait(timeout=2.0)

    # Leitor em cache não fica bloqueado enquanto `use_cache=False` executa a sonda.
    leitura_em_cache = oqh.collect_oracle_queue_health(use_cache=True)
    assert leitura_em_cache["version"] == "1.0"

    liberar_probe.set()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert resultado_bg[0]["version"] == "2.0"

    # Cache foi atualizado com timestamp pós-sonda (1002.0) e novo payload.
    assert oqh.collect_oracle_queue_health(use_cache=True)["version"] == "2.0"
    assert oqh._cache[oqh._CACHE_KEY][0] == 1002.0  # pylint: disable=protected-access


def test_collect_oracle_queue_health_usa_ttl_curto_para_payload_degradado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def _sonda_falha() -> dict[str, Any]:
        chamadas.append(1)
        raise OSError("SMB offline")

    relogio = [1000.0]
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setattr(oqh, "probe_oracle_queue_health", _sonda_falha)
    monkeypatch.setattr(oqh, "time", SimpleNamespace(monotonic=lambda: relogio[0]))

    assert oqh.collect_oracle_queue_health()["alive"] is False
    assert len(chamadas) == 1

    # Dentro do TTL curto, mantém cache.
    relogio[0] += oqh.DEGRADED_HEALTH_TTL_SECONDS - 0.5
    assert oqh.collect_oracle_queue_health()["alive"] is False
    assert len(chamadas) == 1

    # Após o TTL curto (bem antes de HEALTH_TTL_SECONDS=15s), sonda de novo.
    relogio[0] += 0.5
    assert oqh.collect_oracle_queue_health()["alive"] is False
    assert len(chamadas) == 2

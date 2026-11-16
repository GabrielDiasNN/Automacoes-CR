"""Testes de robustez da fila Oracle: prazos com worker vivo, relógio do SMB, heartbeat
truncado, cache de vivacidade, header --#timeout e snapshot de saúde.

Sem rede real: tudo roda em `tmp_path`, com `monkeypatch` nas sondas de SMB e de vivacidade.
"""

import json
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "lib" / "python"))

import oracle_queue
from carregadores_modulos import acessar_privado
from oracle_queue import (
    OracleQueueTimeoutError,
    OracleQueueWorkerOfflineError,
    QueueRequestOptions,
    build_queue_payload,
    execute_query,
)

pytestmark = pytest.mark.unitario

RESPOSTA_OK = b"UM,TXT\r\nnumber,string\r\n1,a\r\n#fim,1,7,3,2,2.4.0\r\n"
VIVO: dict[str, Any] = {"alive": True, "reachable": True, "source": "heartbeat"}
MORTO: dict[str, Any] = {
    "alive": False,
    "reachable": True,
    "source": "heartbeat",
    "age_seconds": 120.0,
}


@pytest.fixture(autouse=True)
def _estado_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zera caches de módulo e variáveis de prazo antes de cada teste."""
    acessar_privado(oracle_queue, "_reset_liveness_cache")()
    monkeypatch.setattr(oracle_queue, "_last_sweep", {})
    monkeypatch.setattr(oracle_queue, "_clock_skew_cache", {})
    monkeypatch.delenv("ORACLE_QUEUE_DEADLINE_EPOCH", raising=False)
    monkeypatch.delenv("ORACLE_QUEUE_CLAIM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(oracle_queue, "_check_unc_port_reachable", lambda *_a: True)


def _sequencia_de_vivacidade(*respostas: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    """Devolve uma resposta por chamada; a última se repete."""
    fila = list(respostas)

    def falsa(*_a: Any, **_k: Any) -> dict[str, Any]:
        return fila.pop(0) if len(fila) > 1 else fila[0]

    return falsa


def _worker(
    pasta: Path, parar: threading.Event, atraso_claim: float, responde: bool
) -> None:
    """Reivindica o primeiro `req_*.sql` depois de `atraso_claim` s (.sql -> .proc)
    e, se `responde`, publica `res_<id>.csv`."""
    inicio = time.monotonic()
    while not parar.is_set():
        reqs = list(pasta.glob("req_*.sql"))
        if reqs and time.monotonic() - inicio >= atraso_claim:
            req_id = reqs[0].stem[len("req_") :]
            reqs[0].replace(pasta / f"req_{req_id}.proc")
            if responde:
                tmp = pasta / f"res_{req_id}.tmp"
                tmp.write_bytes(RESPOSTA_OK)
                tmp.replace(pasta / f"res_{req_id}.csv")
            return
        time.sleep(0.01)


# ------------------------------------------------------------------ B: prazos


def test_worker_vivo_apos_claim_deadline_continua_esperando(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker vivo e ocupado: o prazo de reivindicação (0,1 s) não pode abortar o pedido
    que só é reivindicado em 0,4 s e respondido depois."""
    monkeypatch.setenv("ORACLE_QUEUE_CLAIM_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setattr(oracle_queue, "check_worker_liveness", _sequencia_de_vivacidade(VIVO))
    parar = threading.Event()
    threading.Thread(
        target=_worker, args=(tmp_path, parar, 0.4, True), daemon=True
    ).start()
    try:
        r = execute_query(
            "SELECT 1 AS UM, 'a' AS TXT FROM DUAL",
            timeout_seconds=3,
            queue_dir=str(tmp_path),
        )
    finally:
        parar.set()
    assert r.rows == [(1, "a")]


def test_worker_vivo_sem_resposta_no_fim_levanta_timeout_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_CLAIM_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setattr(oracle_queue, "check_worker_liveness", _sequencia_de_vivacidade(VIVO))
    with pytest.raises(OracleQueueTimeoutError) as exc:
        execute_query("SELECT 1 FROM DUAL", timeout_seconds=0.5, queue_dir=str(tmp_path))
    assert isinstance(exc.value, TimeoutError)
    assert not isinstance(exc.value, OracleQueueWorkerOfflineError)
    assert not list(tmp_path.glob("req_*")), "pedido não atendido deve ser apagado"


def test_worker_morto_no_claim_deadline_levanta_worker_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pré-checagem viva, depois morto: o prazo de reivindicação vence sem worker."""
    monkeypatch.setenv("ORACLE_QUEUE_CLAIM_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setattr(
        oracle_queue,
        "check_worker_liveness",
        _sequencia_de_vivacidade(VIVO, MORTO),
    )
    with pytest.raises(OracleQueueWorkerOfflineError):
        execute_query("SELECT 1 FROM DUAL", timeout_seconds=5, queue_dir=str(tmp_path))


def test_worker_morto_no_fim_do_prazo_levanta_worker_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        oracle_queue,
        "check_worker_liveness",
        _sequencia_de_vivacidade(VIVO, MORTO),
    )
    with pytest.raises(OracleQueueWorkerOfflineError):
        execute_query("SELECT 1 FROM DUAL", timeout_seconds=0.2, queue_dir=str(tmp_path))


# ------------------------------------------------------------------ C: --#timeout


def test_build_queue_payload_nao_injeta_timeout_automatico() -> None:
    """Sem `command_timeout_seconds`, nada de `--#timeout` (antes impunha teto de 120 s)."""
    payload = build_queue_payload("SELECT 1 FROM DUAL", 300.0)
    assert "--#timeout:" not in payload
    assert "--#ttl:" in payload


def test_build_queue_payload_timeout_explicito_prevalece_e_e_limitado() -> None:
    explicito = build_queue_payload(
        "SELECT 1 FROM DUAL",
        300.0,
        options=QueueRequestOptions(command_timeout_seconds=45),
    )
    assert "--#timeout:45\n" in explicito

    acima_do_teto = build_queue_payload(
        "SELECT 1 FROM DUAL",
        300.0,
        options=QueueRequestOptions(command_timeout_seconds=500),
    )
    assert "--#timeout:120\n" in acima_do_teto


# ------------------------------------------------------------------ D: relógio do SMB


def test_server_now_aplica_o_skew_medido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: 1000.0)
    antes = time.time()
    agora_servidor = acessar_privado(oracle_queue, "_server_now")(str(tmp_path))
    depois = time.time()
    assert antes - 1000.0 - 1 <= agora_servidor <= depois - 1000.0 + 1


def test_server_now_cacheia_o_skew_por_pasta_e_expira_em_600s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[str] = []

    def medir(base: str) -> float:
        chamadas.append(base)
        return 5.0

    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", medir)
    acessar_privado(oracle_queue, "_server_now")(str(tmp_path))
    acessar_privado(oracle_queue, "_server_now")(str(tmp_path))
    assert len(chamadas) == 1

    expirado = time.monotonic() - oracle_queue.CLOCK_SKEW_TTL_SECONDS - 1
    monkeypatch.setattr(
        oracle_queue, "_clock_skew_cache", {str(tmp_path): (expirado, 5.0)}
    )
    acessar_privado(oracle_queue, "_server_now")(str(tmp_path))
    assert len(chamadas) == 2


def test_medir_skew_com_pasta_inexistente_devolve_none(tmp_path: Path) -> None:
    medir = acessar_privado(oracle_queue, "_medir_skew_relogio")
    assert medir(str(tmp_path / "nao_existe")) is None


def test_falha_na_primeira_medicao_nao_e_cacheada_e_a_proxima_mede_de_novo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = str(tmp_path)
    respostas: list[float | None] = [None, 7.0]
    chamadas: list[str] = []

    def medir(pasta: str) -> float | None:
        chamadas.append(pasta)
        return respostas.pop(0)

    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", medir)

    # Falha na 1a medicao: sem skew anterior, usa 0.0 e nao grava no cache.
    antes = time.time()
    agora = acessar_privado(oracle_queue, "_server_now")(base)
    assert antes <= agora <= time.time()
    assert base not in acessar_privado(oracle_queue, "_clock_skew_cache")
    assert len(chamadas) == 1

    # A 2a chamada mede de novo (nao ficou presa ao 0.0) e grava o skew real.
    acessar_privado(oracle_queue, "_server_now")(base)
    assert len(chamadas) == 2
    assert acessar_privado(oracle_queue, "_clock_skew_cache")[base][1] == 7.0


def test_falha_apos_medicao_boa_reaproveita_o_skew_antigo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = str(tmp_path)
    respostas: list[float | None] = [1000.0, None]
    monkeypatch.setattr(
        oracle_queue, "_medir_skew_relogio", lambda _b: respostas.pop(0)
    )

    acessar_privado(oracle_queue, "_server_now")(base)  # medicao boa: grava skew 1000.0
    instante, skew = acessar_privado(oracle_queue, "_clock_skew_cache")[base]
    expirado = (instante - oracle_queue.CLOCK_SKEW_TTL_SECONDS - 1, skew)
    monkeypatch.setitem(acessar_privado(oracle_queue, "_clock_skew_cache"), base, expirado)

    # Cache expirado e sonda falhando: reaproveita o skew antigo (1000.0), sem regravar.
    agora = acessar_privado(oracle_queue, "_server_now")(base)
    assert abs(agora - (time.time() - 1000.0)) < 1
    assert acessar_privado(oracle_queue, "_clock_skew_cache")[base] == expirado
    assert not respostas


def test_heartbeat_usa_relogio_do_servidor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Servidor 1000 s atrás da estação: heartbeat recém-escrito tem mtime 1000 s no passado
    na escala local. Com o skew medido ele continua vivo; sem skew, pareceria morto."""
    hb = tmp_path / "_worker_heartbeat.json"
    hb.write_text(json.dumps({"version": "2.6.1", "state": "idle"}), encoding="utf-8")
    mtime = time.time() - 1000.0
    os.utime(hb, (mtime, mtime))

    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: 1000.0)
    info = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert info["alive"] is True
    assert info["age_seconds"] < 5

    acessar_privado(oracle_queue, "_reset_liveness_cache")()
    monkeypatch.setattr(oracle_queue, "_clock_skew_cache", {})
    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: 0.0)
    sem_skew = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert sem_skew["alive"] is False


def test_varredura_usa_relogio_do_servidor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Servidor 2000 s adiantado: arquivo com 3700 s de idade no servidor é órfão
    (limite 3600 s). Sem o skew, a idade local (1700 s) o manteria."""
    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: -2000.0)
    res = tmp_path / "res_velha.csv"
    res.write_bytes(b"x")
    mtime = time.time() + 2000.0 - 3700.0
    os.utime(res, (mtime, mtime))
    acessar_privado(oracle_queue, "_sweep_orphans")(str(tmp_path))
    assert not res.exists()


def test_sweep_mantem_arquivo_recente_no_relogio_do_servidor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: -2000.0)
    res = tmp_path / "res_recente.csv"
    res.write_bytes(b"x")
    mtime = time.time() + 2000.0 - 600.0
    os.utime(res, (mtime, mtime))
    acessar_privado(oracle_queue, "_sweep_orphans")(str(tmp_path))
    assert res.exists()


def test_orphan_max_age_folga_para_pedidos_longos() -> None:
    assert oracle_queue.ORPHAN_MAX_AGE_SECONDS == 3600.0


# ------------------------------------------------------------------ E: heartbeat truncado


def test_heartbeat_truncado_usa_mtime_e_nao_e_descartado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: 0.0)
    hb = tmp_path / "_worker_heartbeat.json"
    hb.write_text('{"version": "2.6', encoding="utf-8")

    fresco = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert fresco["source"] == "heartbeat"
    assert fresco["alive"] is True
    assert fresco["state"] is None

    antigo = time.time() - 120.0
    os.utime(hb, (antigo, antigo))
    velho = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert velho["source"] == "heartbeat"
    assert velho["alive"] is False


def test_heartbeat_truncado_com_proc_usa_limite_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_medir_skew_relogio", lambda _b: 0.0)
    hb = tmp_path / "_worker_heartbeat.json"
    hb.write_text("{", encoding="utf-8")
    antigo = time.time() - 120.0
    os.utime(hb, (antigo, antigo))
    (tmp_path / "req_123_abc.proc").write_text("SELECT 1 FROM DUAL", encoding="utf-8")

    info = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert info["source"] == "heartbeat"
    assert info["active_procs"] == 1
    assert info["alive"] is True


def test_heartbeat_com_stat_falho_devolve_false(tmp_path: Path) -> None:
    def _stat_falho() -> None:
        raise OSError("stat falhou")

    entrada = SimpleNamespace(path=str(tmp_path / "_worker_heartbeat.json"), stat=_stat_falho)
    resultado: dict[str, Any] = {}
    assert (
        acessar_privado(oracle_queue, "_apply_heartbeat_entry")(
            str(tmp_path), entrada, 45.0, 0, resultado
        )
        is False
    )


# ------------------------------------------------------------------ F: cache de vivacidade


def test_vivacidade_viva_fica_em_cache_por_15_segundos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[str] = []

    def falsa(base: str, **_k: Any) -> dict[str, Any]:
        chamadas.append(base)
        return dict(VIVO)

    relogio = [1000.0]
    monkeypatch.setattr(oracle_queue, "check_worker_liveness", falsa)
    monkeypatch.setattr(
        oracle_queue,
        "time",
        SimpleNamespace(monotonic=lambda: relogio[0], time=time.time, sleep=time.sleep),
    )
    acessar_privado(oracle_queue, "_ensure_worker_alive_or_raise")(str(tmp_path))
    acessar_privado(oracle_queue, "_ensure_worker_alive_or_raise")(str(tmp_path))
    assert len(chamadas) == 1

    relogio[0] += oracle_queue.LIVENESS_CACHE_SECONDS + 1
    acessar_privado(oracle_queue, "_ensure_worker_alive_or_raise")(str(tmp_path))
    assert len(chamadas) == 2


def test_vivacidade_offline_nao_e_cacheada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[str] = []

    def falsa(base: str, **_k: Any) -> dict[str, Any]:
        chamadas.append(base)
        return dict(MORTO)

    monkeypatch.setattr(oracle_queue, "check_worker_liveness", falsa)
    for _ in range(2):
        with pytest.raises(OracleQueueWorkerOfflineError):
            acessar_privado(oracle_queue, "_ensure_worker_alive_or_raise")(str(tmp_path))
    assert len(chamadas) == 2


# ------------------------------------------------------------------ G: snapshot sob pytest


def test_snapshot_consulta_a_fila_mesmo_sob_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem o atalho `PYTEST_CURRENT_TEST`: em modo queue, o snapshot usa a sonda (aqui mockada)."""
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.delenv("ORACLE_QUEUE_DIR", raising=False)
    monkeypatch.setattr(
        oracle_queue,
        "check_worker_liveness",
        lambda *_a, **_k: {"alive": True, "reachable": True, "source": "heartbeat"},
    )
    info = oracle_queue.collect_worker_health_snapshot()
    assert info["enabled"] is True
    assert info["alive"] is True
    assert info["source"] == "heartbeat"

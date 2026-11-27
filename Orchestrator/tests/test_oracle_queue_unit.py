"""Testes unitários do cliente da fila Oracle via SMB (`ORACLE_DRIVER_MODE=queue`).

Usam uma pasta temporária no lugar do share e um "worker" falso em thread: não
tocam o TSplus nem o Oracle. Cobrem o contrato que a revisão de 08/11/2026 fixou:
falha transitória entra no retry, resposta órfã é limpa, SQL nunca é alterado em
silêncio e binds ambíguos são recusados.
"""

import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "lib" / "python"))
_SRC_BENEF = _REPO / "Produção Beneficimento" / "src"
if str(_SRC_BENEF) not in sys.path:
    sys.path.insert(0, str(_SRC_BENEF))

import oracle_extract
import oracle_queue
from beneficiamento import (
    oracle as benef_oracle,
)
from carregadores_modulos import acessar_privado
from oracle_queue import (
    OracleQueueBlockedError,
    OracleQueueError,
    OracleQueueTransientError,
    QueueRequestOptions,
    QueueResult,
    build_queue_payload,
    execute_query,
)
from oracle_retry import (
    make_oracle_retry,
)

pytestmark = pytest.mark.unitario

RESPOSTA_OK = b"UM,TXT\r\nnumber,string\r\n1,a\r\n#fim,1,7,3,2,2.4.0\r\n"


def _worker_falso(pasta: Path, resposta: bytes, parar: threading.Event) -> list[str]:
    """Responde ao primeiro `req_*.sql` com `resposta`; devolve o texto recebido."""
    recebidos: list[str] = []

    def laco() -> None:
        while not parar.is_set():
            for req in pasta.glob("req_*.sql"):
                recebidos.append(req.read_text(encoding="cp1252"))
                req_id = req.stem[len("req_") :]
                req.unlink()
                tmp = pasta / f"res_{req_id}.tmp"
                tmp.write_bytes(resposta)
                tmp.replace(pasta / f"res_{req_id}.csv")
                return
            time.sleep(0.01)

    threading.Thread(target=laco, daemon=True).start()
    return recebidos


def test_execute_query_ida_e_volta_com_binds(tmp_path: Path) -> None:
    parar = threading.Event()
    recebidos = _worker_falso(tmp_path, RESPOSTA_OK, parar)
    try:
        r = execute_query(
            "SELECT 1 AS UM, :TXT AS TXT FROM DUAL",
            timeout_seconds=5,
            queue_dir=str(tmp_path),
            params={"txt": "ação"},
        )
    finally:
        parar.set()
    assert r.columns == ["UM", "TXT"] and r.rows == [(1, "a")] and r.worker == "2.4.0"
    assert "--#param:TXT=s:a%u00E7%u00E3o\n" in recebidos[0]
    assert recebidos[0].index("--#ttl:") < recebidos[0].index("--#param:")
    assert not list(tmp_path.iterdir()), "fila deve ficar limpa"


def test_timeout_remove_pedido_nao_atendido(tmp_path: Path) -> None:
    with pytest.raises(oracle_queue.OracleQueueWorkerOfflineError):
        execute_query(
            "SELECT 1 FROM DUAL", timeout_seconds=0.1, queue_dir=str(tmp_path)
        )
    assert not list(tmp_path.glob("req_*")), "pedido não atendido deve ser apagado"


def test_timeout_quando_reivindicado_sem_resposta_levanta_timeout_error(
    tmp_path: Path,
) -> None:
    parar = threading.Event()

    def reivindicar_sem_responder() -> None:
        while not parar.is_set():
            for req in tmp_path.glob("req_*.sql"):
                req.replace(req.with_suffix(".proc"))
                return
            time.sleep(0.01)

    threading.Thread(target=reivindicar_sem_responder, daemon=True).start()
    try:
        with pytest.raises(TimeoutError):
            execute_query(
                "SELECT 1 FROM DUAL", timeout_seconds=0.15, queue_dir=str(tmp_path)
            )
    finally:
        parar.set()


def test_res_orfa_velha_e_apagada_e_recente_preservada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_last_sweep", {})
    velha = tmp_path / "res_velha.csv"
    recente = tmp_path / "res_recente.csv"
    velha.write_bytes(b"x")
    recente.write_bytes(b"x")
    antigo = time.time() - oracle_queue.ORPHAN_MAX_AGE_SECONDS - 60
    os.utime(velha, (antigo, antigo))
    acessar_privado(oracle_queue, "_sweep_orphans")(str(tmp_path))
    assert not velha.exists() and recente.exists()


def test_pasta_inexistente_em_raiz_alcancavel_e_erro_de_config(tmp_path: Path) -> None:
    with pytest.raises(OracleQueueError) as exc:
        execute_query("SELECT 1 FROM DUAL", queue_dir=str(tmp_path / "nao_existe"))
    assert exc.value.kind == "config"
    assert not isinstance(exc.value, OracleQueueTransientError)


def test_raiz_inalcancavel_e_transitoria(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "isdir", lambda _: False)
    with pytest.raises(OracleQueueTransientError) as exc:
        execute_query("SELECT 1 FROM DUAL", queue_dir=r"\\servidor\share\fila")
    assert exc.value.kind == "smb"


def test_queue_dir_vazio_no_ambiente_usa_o_padrao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_DIR", "  ")
    assert oracle_queue.get_queue_dir() == oracle_queue.DEFAULT_QUEUE_DIR
    monkeypatch.setenv("ORACLE_QUEUE_DIR", " fila_configurada ")
    assert oracle_queue.get_queue_dir() == "fila_configurada"


def test_varredura_roda_no_maximo_uma_vez_por_intervalo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_last_sweep", {})
    velha = tmp_path / "res_velha.csv"
    antigo = time.time() - oracle_queue.ORPHAN_MAX_AGE_SECONDS - 60
    acessar_privado(oracle_queue, "_sweep_orphans")(str(tmp_path))
    velha.write_bytes(b"x")
    os.utime(velha, (antigo, antigo))
    acessar_privado(oracle_queue, "_sweep_orphans")(str(tmp_path))
    assert velha.exists(), "segunda varredura dentro do intervalo não deve rodar"


def test_sql_fora_do_cp1252_falha_alto_sem_gravar(tmp_path: Path) -> None:
    with pytest.raises(OracleQueueError) as exc:
        execute_query(
            "SELECT '≥' FROM DUAL", timeout_seconds=1, queue_dir=str(tmp_path)
        )
    assert exc.value.kind == "request"
    assert not isinstance(exc.value, OracleQueueTransientError)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("resposta", "classe", "kind"),
    [
        (b"#ERRO,worker,falha interna\r\n", OracleQueueError, "worker"),
        (b"#ERRO,oracle,ORA-00942\r\n", OracleQueueError, "oracle"),
        (b"#ERRO,blocked,DELETE\r\n", OracleQueueBlockedError, "blocked"),
        (b"UM\r\nnumber\r\n1\r\n", OracleQueueTransientError, "worker"),
        (b"UM\r\nnumber\r\n1\r\n#fim,2\r\n", OracleQueueTransientError, "worker"),
        (b"UM\r\nnumber\r\nabc\r\n#fim,1\r\n", OracleQueueError, "worker"),
    ],
)
def test_classificacao_dos_erros(
    resposta: bytes, classe: type[OracleQueueError], kind: str
) -> None:
    with pytest.raises(classe) as exc:
        acessar_privado(oracle_queue, "_parse_response")(resposta)
    assert exc.value.kind == kind
    if classe is OracleQueueError:
        assert not isinstance(exc.value, OracleQueueTransientError)


@pytest.mark.parametrize(
    ("serial", "esperado"),
    [
        ("0", datetime(1899, 12, 30)),
        ("1.25", datetime(1899, 12, 31, 6)),
        ("-1.25", datetime(1899, 12, 29, 6)),
        ("-1", datetime(1899, 12, 29)),
        ("46334.7118055556", datetime(2026, 11, 8, 17, 5)),
    ],
)
def test_serial_ole_segue_a_especificacao_nos_dois_sentidos(
    serial: str, esperado: datetime
) -> None:
    assert acessar_privado(oracle_queue, "_to_datetime")(serial) == esperado
    codificado = acessar_privado(oracle_queue, "_encode_param")("D", esperado).split(
        "=d:"
    )[1]
    assert abs(float(codificado) - float(serial)) < 1e-9


def test_binds_que_colidem_na_caixa_sao_recusados() -> None:
    with pytest.raises(ValueError, match="repetidos"):
        acessar_privado(oracle_queue, "_encode_params")({"a": 1, "A": 2})


def test_datetime_com_fuso_e_recusado() -> None:
    with pytest.raises(TypeError, match="fuso"):
        acessar_privado(oracle_queue, "_encode_param")(
            "D", datetime(2026, 1, 1, tzinfo=UTC)
        )


def test_prazo_da_extracao_vem_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(oracle_queue.QUEUE_TIMEOUT_ENV, raising=False)
    assert (
        oracle_queue.get_queue_timeout()
        == oracle_queue.DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    )
    monkeypatch.setenv(oracle_queue.QUEUE_TIMEOUT_ENV, "45")
    assert oracle_queue.get_queue_timeout() == 45.0
    monkeypatch.setenv(oracle_queue.QUEUE_TIMEOUT_ENV, "0")
    with pytest.raises(ValueError):
        oracle_queue.get_queue_timeout()


def test_share_fora_do_ar_na_espera_vira_falha_transitoria(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Share que cai depois do envio não pode girar até o prazo e virar TimeoutError."""

    def sem_share(_path: str) -> bytes | None:
        raise OSError("rede indisponivel")

    monkeypatch.setattr(oracle_queue, "_try_take", sem_share)
    monkeypatch.setattr(oracle_queue, "SMB_OUTAGE_GRACE_SECONDS", 0.05)
    inicio = time.monotonic()
    with pytest.raises(OracleQueueTransientError) as erro:
        execute_query("SELECT 1 FROM DUAL", timeout_seconds=30, queue_dir=str(tmp_path))
    assert erro.value.kind == "smb"
    assert time.monotonic() - inicio < 5, "não deve esperar o prazo inteiro"


def test_soluco_de_rede_na_espera_nao_derruba_a_consulta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = acessar_privado(oracle_queue, "_try_take")
    falhas = iter([OSError("solucao"), OSError("solucao")])

    def instavel(path: str) -> bytes | None:
        falha = next(falhas, None)
        if falha is not None:
            raise falha
        resultado: bytes | None = original(path)
        return resultado

    monkeypatch.setattr(oracle_queue, "_try_take", instavel)
    parar = threading.Event()
    _worker_falso(tmp_path, RESPOSTA_OK, parar)
    try:
        r = execute_query(
            "SELECT 1 FROM DUAL", timeout_seconds=5, queue_dir=str(tmp_path)
        )
    finally:
        parar.set()
    assert r.rows == [(1, "a")]


def test_fetch_all_na_fila_usa_prazo_configurado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    capturado: dict[str, Any] = {}

    def falso(sql: str, timeout_seconds: float, params: Any = None) -> QueueResult:
        capturado.update(sql=sql, timeout=timeout_seconds, params=params)
        return QueueResult(columns=["X"], types=["number"], rows=[(1,)])

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv(oracle_queue.QUEUE_TIMEOUT_ENV, "600")
    monkeypatch.setattr(oracle_queue, "execute_query", falso)
    creds = oracle_extract.OracleCredentials(
        user="", password="", dsn="dbprd", client_lib="", tns_admin=None
    )
    cols, rows = oracle_extract.fetch_all(
        creds, "SELECT 1 X FROM DUAL", "exec", lambda *_: None, params={"P": 1}
    )
    assert (cols, rows) == (["X"], [(1,)])
    assert capturado["timeout"] == 600.0 and capturado["params"] == {"P": 1}


def test_retry_das_extracoes_repete_falha_transitoria_da_fila() -> None:
    chamadas: list[int] = []

    @make_oracle_retry(attempts=3, wait_initial=0, wait_max=0, wait_jitter=0)
    def extrair() -> str:
        chamadas.append(1)
        if len(chamadas) < 2:
            raise OracleQueueTransientError("smb", "share caiu")
        return "ok"

    assert extrair() == "ok" and len(chamadas) == 2


def test_retry_das_extracoes_nao_repete_erro_de_sql() -> None:
    chamadas: list[int] = []

    @make_oracle_retry(attempts=3, wait_initial=0, wait_max=0, wait_jitter=0)
    def extrair() -> str:
        chamadas.append(1)
        raise OracleQueueError("oracle", "ORA-00942")

    with pytest.raises(OracleQueueError):
        extrair()
    assert len(chamadas) == 1


def test_init_thick_mode_registra_modo_queue(monkeypatch: pytest.MonkeyPatch) -> None:

    mensagens: list[str] = []
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    creds = oracle_extract.OracleCredentials(
        user="", password="", dsn="dbprd", client_lib="", tns_admin=None
    )
    oracle_extract.init_thick_mode(creds, lambda msg, *_: mensagens.append(msg), "exec")
    assert mensagens and "queue" in mensagens[0]


def test_beneficiamento_repete_falha_transitoria_da_fila(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def falso(*_: Any, **__: Any) -> Any:
        chamadas.append(1)
        if len(chamadas) < 2:
            raise OracleQueueTransientError("smb", "share caiu")
        return benef_oracle.QueryResult(
            columns=["X"], rows=[(1,)], duplicate_columns=[], metadata={}
        )

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setattr(benef_oracle, "_execute_once_queue", falso)
    result = benef_oracle.execute_query(
        "SELECT 1 X FROM DUAL", wall_clock_budget_seconds=30
    )
    assert result.metadata["attempts"] == 2


def test_check_worker_liveness_le_heartbeat_fresco_e_velho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_check_unc_port_reachable", lambda *_a: True)
    hb = tmp_path / "_worker_heartbeat.json"
    hb.write_text(
        json.dumps({"version": "2.6.1", "state": "idle", "oracle_ok": True}),
        encoding="utf-8",
    )
    fresco = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert fresco["alive"] is True
    assert fresco["version"] == "2.6.1"
    assert fresco["oracle_ok"] is True

    antigo = time.time() - 120.0
    os.utime(hb, (antigo, antigo))
    velho = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert velho["alive"] is False


def test_execute_query_falha_rapido_quando_heartbeat_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        oracle_queue,
        "check_worker_liveness",
        lambda *_a, **_k: {
            "reachable": True,
            "alive": False,
            "source": "heartbeat",
            "age_seconds": 120.0,
            "state": "idle",
        },
    )
    with pytest.raises(oracle_queue.OracleQueueWorkerOfflineError):
        execute_query(
            "SELECT 1 FROM DUAL",
            timeout_seconds=10,
            queue_dir=str(tmp_path),
        )
    assert not list(tmp_path.iterdir())


def test_strip_sql_comments_preserva_hints_e_literais_unicode() -> None:
    sql = "-- cabeçalho ≥\n/* comentário → */\nSELECT /*+ INDEX(T IDX) */ '-- manter' FROM DUAL"
    limpo = oracle_queue.strip_sql_comments(sql)
    assert "≥" not in limpo
    assert "→" not in limpo
    assert "/*+ INDEX(T IDX) */" in limpo
    assert "'-- manter'" in limpo


def test_classify_oracle_exit_code_mapeia_worker_timeout_bloqueio() -> None:

    assert (
        oracle_extract.classify_oracle_exit_code(
            oracle_queue.OracleQueueWorkerOfflineError("worker", "offline")
        )
        == 6
    )
    # Prazo da fila com worker vivo: 7. TimeoutError genérico (thick/auto): 1.
    assert (
        oracle_extract.classify_oracle_exit_code(
            oracle_queue.OracleQueueTimeoutError("timeout fila")
        )
        == 7
    )
    assert oracle_extract.classify_oracle_exit_code(TimeoutError("timeout fila")) == 1
    assert (
        oracle_extract.classify_oracle_exit_code(
            oracle_queue.OracleQueueBlockedError("blocked", "DELETE")
        )
        == 5
    )
    assert oracle_extract.classify_oracle_exit_code(RuntimeError("outro")) == 1


def test_cleanup_requests_for_exec_id_remove_somente_correspondentes(
    tmp_path: Path,
) -> None:
    alvo = tmp_path / "req_123_abc.sql"
    alvo.write_text("--#meta:exec_id=EXEC_99\nSELECT 1 FROM DUAL", encoding="utf-8")
    outro = tmp_path / "req_124_def.sql"
    outro.write_text("--#meta:exec_id=EXEC_OTHER\nSELECT 1 FROM DUAL", encoding="utf-8")

    removidos = oracle_queue.cleanup_requests_for_exec_id("EXEC_99", str(tmp_path))
    assert removidos == 1
    assert not alvo.exists()
    assert outro.exists()


def test_get_queue_timeout_deadline_expirado_e_restante_curto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(oracle_queue.QUEUE_TIMEOUT_ENV, raising=False)
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() - 5))
    with pytest.raises(
        oracle_queue.OracleQueueTimeoutError, match="ORACLE_QUEUE_DEADLINE_EPOCH"
    ):
        oracle_queue.get_queue_timeout()

    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() + 1.2))
    restante = oracle_queue.get_queue_timeout()
    assert 0.5 <= restante <= 1.3


def test_apply_queue_deadline_sem_env_devolve_o_mesmo_valor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORACLE_QUEUE_DEADLINE_EPOCH", raising=False)
    assert oracle_queue.apply_queue_deadline(42.0) == 42.0


def test_apply_queue_deadline_futuro_menor_limita(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() + 10))
    restante = oracle_queue.apply_queue_deadline(300.0)
    assert 9.0 < restante <= 10.0


def test_apply_queue_deadline_futuro_maior_nao_aumenta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() + 1000))
    assert oracle_queue.apply_queue_deadline(5.0) == 5.0


def test_apply_queue_deadline_vencido_levanta_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() - 5))
    with pytest.raises(
        oracle_queue.OracleQueueTimeoutError, match="ORACLE_QUEUE_DEADLINE_EPOCH"
    ):
        oracle_queue.apply_queue_deadline(300.0)


@pytest.mark.parametrize("valor", ["abc", "nan", "inf"])
def test_apply_queue_deadline_invalido_e_ignorado(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", valor)
    assert oracle_queue.apply_queue_deadline(42.0) == 42.0


def test_get_queue_timeout_mantem_comportamento_com_e_sem_prazo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(oracle_queue.QUEUE_TIMEOUT_ENV, raising=False)
    monkeypatch.delenv("ORACLE_QUEUE_DEADLINE_EPOCH", raising=False)
    assert oracle_queue.get_queue_timeout(default=7.0) == 7.0

    monkeypatch.setenv(oracle_queue.QUEUE_TIMEOUT_ENV, "45")
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() + 1000))
    assert oracle_queue.get_queue_timeout() == 45.0

    monkeypatch.setenv(oracle_queue.QUEUE_TIMEOUT_ENV, "-1")
    with pytest.raises(ValueError):
        oracle_queue.get_queue_timeout()


def test_fetch_all_queue_respeita_deadline_expirado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", str(time.time() - 5))
    monkeypatch.setattr(
        oracle_queue,
        "execute_query",
        lambda *_a, **_k: pytest.fail("execute_query não deve rodar após deadline"),
    )
    creds = oracle_extract.OracleCredentials(
        user="", password="", dsn="dbprd", client_lib="", tns_admin=None
    )
    with pytest.raises(oracle_queue.OracleQueueTimeoutError):
        oracle_extract.fetch_all(creds, "SELECT 1 FROM DUAL", "exec", lambda *_: None)


def test_check_worker_liveness_heartbeat_expirado_nao_mascarado_por_proc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_queue, "_check_unc_port_reachable", lambda *_a: True)
    hb = tmp_path / "_worker_heartbeat.json"
    hb.write_text(
        json.dumps({"version": "2.6.2", "state": "busy", "oracle_ok": True}),
        encoding="utf-8",
    )
    antigo = time.time() - (oracle_queue.BUSY_HEARTBEAT_MAX_AGE_SECONDS + 30.0)
    os.utime(hb, (antigo, antigo))
    (tmp_path / "req_123_abc.proc").write_text("SELECT 1 FROM DUAL", encoding="utf-8")

    info = oracle_queue.check_worker_liveness(str(tmp_path), probe_signal_seconds=0.0)
    assert info["source"] == "heartbeat"
    assert info["active_procs"] == 1
    assert info["alive"] is False


def test_cleanup_requests_for_exec_id_muitos_binds_colisao_e_fallback_exec_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HUB_EXEC_ID", raising=False)
    monkeypatch.delenv("HUB_AUTOMATION", raising=False)
    monkeypatch.setenv("EXEC_ID", "EXEC_9")

    muitos_params = {f"P{i}": i for i in range(70)}
    payload_9 = build_queue_payload(
        "SELECT 1 FROM DUAL",
        60.0,
        muitos_params,
        QueueRequestOptions(ttl_seconds=60),
    )
    assert payload_9.startswith("--#meta:exec_id=EXEC_9\n")
    assert payload_9.index("--#meta:") < payload_9.index("--#param:")

    req_9 = tmp_path / "req_100_aaa.sql"
    req_9.write_text(payload_9, encoding="cp1252")
    req_99 = tmp_path / "req_101_bbb.sql"
    req_99.write_text("--#meta:exec_id=EXEC_99\nSELECT 1 FROM DUAL", encoding="cp1252")

    removidos = oracle_queue.cleanup_requests_for_exec_id("EXEC_9", str(tmp_path))
    assert removidos == 1
    assert not req_9.exists()
    assert req_99.exists()


def test_strip_sql_comments_preserva_q_quote() -> None:
    sql = "SELECT q'[texto -- ; /* literal */]' AS A, nq'!outro -- /* !' AS B FROM DUAL -- fim"
    limpo = oracle_queue.strip_sql_comments(sql)
    assert "q'[texto -- ; /* literal */]'" in limpo
    assert "nq'!outro -- /* !'" in limpo
    assert "-- fim" not in limpo


def test_build_queue_payload_emite_max_rows_no_topo() -> None:
    com_limite = build_queue_payload(
        "SELECT 1 FROM DUAL",
        30.0,
        {"A": 1},
        QueueRequestOptions(meta="exec_id=T1", max_rows=15),
    )
    assert "--#max_rows:15\n" in com_limite
    assert com_limite.index("--#max_rows:15") < com_limite.index("--#param:A=")

    sem_limite = build_queue_payload(
        "SELECT 1 FROM DUAL", 30.0, options=QueueRequestOptions(max_rows=0)
    )
    assert "--#max_rows:" not in sem_limite


def test_build_queue_payload_rejeita_vazio_ttl_invalido_e_diretiva_no_sql() -> None:
    with pytest.raises(ValueError, match="vazio"):
        build_queue_payload("   \n\t ", 30.0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        QueueRequestOptions(ttl_seconds=0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        QueueRequestOptions(ttl_seconds=-5)
    # Clamping superior em 900 s
    payload_clamp = build_queue_payload(
        "SELECT 1 FROM DUAL", 30.0, options=QueueRequestOptions(ttl_seconds=5000)
    )
    assert "--#ttl:900\n" in payload_clamp

    with pytest.raises(ValueError, match="--#"):
        build_queue_payload("SELECT 1 FROM DUAL\n--#action:explain", 30.0)
    with pytest.raises(ValueError, match="--#"):
        build_queue_payload("  --#param:X=s:1\nSELECT 1 FROM DUAL", 30.0)

    for nao_finito in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ValueError, match="Decimal"):
            acessar_privado(oracle_queue, "_encode_param")("X", nao_finito)


def test_convert_rows_converte_overflow_em_oracle_queue_error() -> None:
    with pytest.raises(OracleQueueError, match="malformada") as exc:
        acessar_privado(oracle_queue, "_convert_rows")(["datetime"], [["999999999999"]])
    assert exc.value.kind == "worker"
    assert not isinstance(exc.value, OracleQueueTransientError)


def test_smb_offline_no_fim_do_prazo_abaixo_de_grace_vira_transitorio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        oracle_queue,
        "_try_take",
        lambda _p: (_ for _ in ()).throw(OSError("share caiu no fim")),
    )
    monkeypatch.setattr(oracle_queue, "SMB_OUTAGE_GRACE_SECONDS", 30.0)
    with pytest.raises(OracleQueueTransientError) as erro:
        execute_query(
            "SELECT 1 FROM DUAL", timeout_seconds=0.15, queue_dir=str(tmp_path)
        )
    assert erro.value.kind == "smb"

"""Testes unitários do cliente da fila Oracle via SMB (`ORACLE_DRIVER_MODE=queue`).

Usam uma pasta temporária no lugar do share e um "worker" falso em thread: não
tocam o TSplus nem o Oracle. Cobrem o contrato que a revisão de 08/11/2026 fixou:
falha transitória entra no retry, resposta órfã é limpa, SQL nunca é alterado em
silêncio e binds ambíguos são recusados.
"""

import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "lib" / "python"))
_SRC_BENEF = _REPO / "Produção Beneficimento" / "src"
if str(_SRC_BENEF) not in sys.path:
    sys.path.insert(0, str(_SRC_BENEF))

import oracle_queue  # noqa: E402  pylint: disable=wrong-import-position
from beneficiamento import (  # noqa: E402  pylint: disable=wrong-import-position
    oracle as benef_oracle,
)
from oracle_queue import (  # noqa: E402  pylint: disable=wrong-import-position
    OracleQueueBlockedError,
    OracleQueueError,
    OracleQueueTransientError,
    QueueResult,
    execute_query,
)
from oracle_retry import (  # noqa: E402  pylint: disable=wrong-import-position
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
    assert recebidos[0].startswith("--#param:TXT=s:a%u00E7%u00E3o\n")
    assert not list(tmp_path.iterdir()), "fila deve ficar limpa"


def test_timeout_remove_pedido_nao_atendido(tmp_path: Path) -> None:
    with pytest.raises(TimeoutError):
        execute_query(
            "SELECT 1 FROM DUAL", timeout_seconds=0.1, queue_dir=str(tmp_path)
        )
    assert not list(tmp_path.glob("req_*")), "pedido não atendido deve ser apagado"


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
    oracle_queue._sweep_orphans(str(tmp_path))  # pylint: disable=protected-access
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
    oracle_queue._sweep_orphans(str(tmp_path))  # pylint: disable=protected-access
    velha.write_bytes(b"x")
    os.utime(velha, (antigo, antigo))
    oracle_queue._sweep_orphans(str(tmp_path))  # pylint: disable=protected-access
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
        oracle_queue._parse_response(resposta)  # pylint: disable=protected-access
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
    # pylint: disable-next=protected-access
    assert oracle_queue._to_datetime(serial) == esperado
    # pylint: disable-next=protected-access
    codificado = oracle_queue._encode_param("D", esperado).split("=d:")[1]
    assert abs(float(codificado) - float(serial)) < 1e-9


def test_binds_que_colidem_na_caixa_sao_recusados() -> None:
    with pytest.raises(ValueError, match="repetidos"):
        # pylint: disable-next=protected-access
        oracle_queue._encode_params({"a": 1, "A": 2})


def test_datetime_com_fuso_e_recusado() -> None:
    with pytest.raises(TypeError, match="fuso"):
        # pylint: disable-next=protected-access
        oracle_queue._encode_param("D", datetime(2026, 1, 1, tzinfo=UTC))


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


def test_fetch_all_na_fila_usa_prazo_configurado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import oracle_extract  # pylint: disable=import-outside-toplevel

    capturado: dict[str, Any] = {}

    def falso(sql: str, timeout_seconds: float, params: Any = None) -> QueueResult:
        capturado.update(sql=sql, timeout=timeout_seconds, params=params)
        return QueueResult(columns=["X"], types=["number"], rows=[(1,)], row_count=1)

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
    import oracle_extract  # pylint: disable=import-outside-toplevel

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

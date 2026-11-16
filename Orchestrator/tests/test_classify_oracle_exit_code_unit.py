"""Testes unitários do mapeamento de exit codes Oracle (`classify_oracle_exit_code`).

Contrato consumido pelo `Invoke-OraclePythonScript` (lib/Lib-Oracle.psm1):
- 1: falha transitória, repetida com espera (30/60/120 s), inclusive o
  `TimeoutError` genérico (timeout do Oracle Bridge ou do connect thick/auto);
- 5, 6 e 7: não repetíveis (saem na primeira tentativa). O 7 é reservado ao
  `OracleQueueTimeoutError`, isto é, o prazo global da fila estourado.

Queda de sessão Oracle (ORA-03113 etc.) é transitória e deve dar 1, mesmo quando
chega pelo worker como `OracleQueueError` genérico.
"""

# lib/python entra no sys.path pelo `pythonpath` do pytest.ini.
import pytest
from oracle_extract import classify_oracle_exit_code, enforce_queue_deadline
from oracle_queue import (
    OracleQueueBlockedError,
    OracleQueueError,
    OracleQueueTimeoutError,
    OracleQueueTransientError,
    OracleQueueWorkerOfflineError,
)


def test_worker_offline_sai_com_6() -> None:
    """Worker offline não é repetido pelo PowerShell: sai com 6."""
    exc = OracleQueueWorkerOfflineError("worker_offline", "heartbeat expirado")
    assert classify_oracle_exit_code(exc) == 6


def test_prazo_da_fila_sai_com_7() -> None:
    """Prazo global da fila estourado sai com 7 (não repetível)."""
    exc = OracleQueueTimeoutError("prazo", "prazo global atingido")
    assert classify_oracle_exit_code(exc) == 7


def test_timeout_do_bridge_sai_com_1() -> None:
    """Timeout do Oracle Bridge Node é repetível: sai com 1, não com 7."""
    assert classify_oracle_exit_code(TimeoutError("Oracle Bridge excedeu 60s.")) == 1


def test_timeout_de_connect_sai_com_1() -> None:
    """Timeout de connect dos modos thick/auto é repetível: sai com 1."""
    assert classify_oracle_exit_code(TimeoutError("connect_within excedeu")) == 1


def test_bloqueio_sai_com_5_mesmo_com_texto_de_queda_de_sessao() -> None:
    """Bloqueio do validador sai com 5 sempre, mesmo que o texto cite ORA-03113."""
    exc = OracleQueueBlockedError("blocked", "ORA-03113: end-of-file on communication")
    assert classify_oracle_exit_code(exc) == 5


def test_erro_oracle_deterministico_sai_com_5() -> None:
    """Erro ORA determinístico reportado pelo worker sai com 5."""
    exc = OracleQueueError("worker", "ORA-01722: invalid number")
    assert classify_oracle_exit_code(exc) == 5


def test_queda_de_sessao_reportada_pelo_worker_sai_com_1() -> None:
    """Queda de sessão reportada pelo worker é transitória: sai com 1."""
    exc = OracleQueueError("worker", "ORA-03113: end-of-file on communication channel")
    assert classify_oracle_exit_code(exc) == 1


def test_erro_transitorio_da_fila_sai_com_1() -> None:
    """Falha transitória de transporte da fila sai com 1 (repetível)."""
    exc = OracleQueueTransientError("smb", "share inalcançável")
    assert classify_oracle_exit_code(exc) == 1


def test_runtime_error_sai_com_1() -> None:
    """Exceção genérica sai com 1 (repetível)."""
    assert classify_oracle_exit_code(RuntimeError("falha qualquer")) == 1


def test_prazo_global_estourado_em_enforce_queue_deadline_sai_com_7(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deadline global já vencido levanta OracleQueueTimeoutError, que sai com 7."""
    monkeypatch.setenv("ORACLE_QUEUE_DEADLINE_EPOCH", "1")
    with pytest.raises(OracleQueueTimeoutError) as info:
        enforce_queue_deadline("teste")
    assert classify_oracle_exit_code(info.value) == 7

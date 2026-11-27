"""Testes unitários da falha transitória da fila no validador (sem tocar a fila).

Cobrem o `OracleQueueTransientError`: propaga do estágio de fila e é repetido por
`_oracle_stage_with_retry` com a mesma espera da queda de sessão. Erro comum da fila
continua sendo `parse: fail`, sem repetir.
"""

from pathlib import Path
from typing import Any

import pytest
from oracle_queue import (
    OracleQueueBlockedError,
    OracleQueueError,
    OracleQueueTransientError,
)
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

vs = _carregar("validar_sql_oracle")
_oracle_stage_with_retry = _priv(vs, "_oracle_stage_with_retry")
_oracle_stage_queue = _priv(vs, "_oracle_stage_queue")

pytestmark = pytest.mark.unitario

SQL = "select 1 from dual"


def _opcoes(execute: bool = False, tentativas: int = vs.MAX_ATTEMPTS) -> Any:
    return vs.RunOptions(
        timeout=120,
        execute=execute,
        explicit_binds={},
        guard=Path("guard_sql.py"),
        attempts=tentativas,
    )


@pytest.fixture(name="dormidas")
def _dormidas(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Registra as esperas do retry em vez de dormir de verdade."""
    esperas: list[float] = []
    monkeypatch.setattr(vs.time, "sleep", esperas.append)
    return esperas


def _explicar_falso(
    monkeypatch: pytest.MonkeyPatch, respostas: list[Exception | float]
) -> list[int]:
    """Troca `explicar_plano_fila`: cada chamada levanta a exceção ou devolve o tempo."""
    chamadas: list[int] = []

    def falso(*_args: Any, **_kwargs: Any) -> tuple[list[str], float]:
        chamadas.append(1)
        resposta = respostas[len(chamadas) - 1]
        if isinstance(resposta, Exception):
            raise resposta
        return ["plano"], resposta

    monkeypatch.setattr(vs, "explicar_plano_fila", falso)
    return chamadas


def _com_sentinela_da_fila(sql: str, options: Any) -> dict[str, Any]:
    resultado: dict[str, Any] = _oracle_stage_with_retry(
        sql, 0, vs.QUEUE_MODE_SENTINEL, options
    )
    return resultado


def test_transitorio_da_fila_propaga_do_estagio_de_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _explicar_falso(monkeypatch, [OracleQueueTransientError("smb", "share caiu")])

    with pytest.raises(OracleQueueTransientError):
        _oracle_stage_queue(SQL, 0, _opcoes())


def test_transitorio_do_smoke_propaga(monkeypatch: pytest.MonkeyPatch) -> None:
    _explicar_falso(monkeypatch, [1.0])
    monkeypatch.setattr(vs, "verificar_objetos_fila", lambda *_a, **_k: None)

    def falso_execucao(*_args: Any, **_kwargs: Any) -> None:
        raise OracleQueueTransientError("worker", "resposta incompleta")

    monkeypatch.setattr(vs, "executar_consulta_fila", falso_execucao)

    with pytest.raises(OracleQueueTransientError):
        _oracle_stage_queue(SQL, 0, _opcoes(execute=True))


def test_erro_comum_da_fila_continua_parse_fail_sem_repetir(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _explicar_falso(
        monkeypatch, [OracleQueueError("oracle", "ORA-00942: tabela inexistente")]
    )

    resultado = _oracle_stage_queue(SQL, 0, _opcoes())

    assert resultado["parse"] == "fail"
    assert resultado["status"] == "oracle_error"
    assert len(chamadas) == 1
    assert dormidas == []


def test_transitorio_repete_com_espera_crescente_ate_o_sucesso(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _explicar_falso(
        monkeypatch,
        [
            OracleQueueTransientError("smb", "share caiu"),
            OracleQueueTransientError("worker", "sem #fim"),
            0.8,
        ],
    )

    resultado = _com_sentinela_da_fila(SQL, _opcoes())

    assert len(chamadas) == 3
    assert dormidas == [5, 10]
    assert resultado["status"] == "parse_ok"
    assert resultado["attempts"] == 3
    assert "network_inconclusive" not in resultado


def test_transitorio_esgotado_vira_timeout_inconclusivo_nao_parse_fail(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _explicar_falso(
        monkeypatch,
        [OracleQueueTransientError("smb", "share caiu")] * vs.MAX_ATTEMPTS,
    )

    resultado = _com_sentinela_da_fila(SQL, _opcoes())

    assert len(chamadas) == vs.MAX_ATTEMPTS
    assert dormidas == [5, 10, 15, 20]
    assert resultado["status"] == "timeout"
    assert resultado.get("parse") != "fail"
    assert resultado["attempts"] == vs.MAX_ATTEMPTS
    assert resultado["network_inconclusive"] is True


def test_prazo_da_fila_nao_e_repetido_pelo_retry(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _explicar_falso(monkeypatch, [TimeoutError("prazo")])

    resultado = _com_sentinela_da_fila(SQL, _opcoes())

    assert len(chamadas) == 1
    assert dormidas == []
    assert resultado["status"] == "timeout"
    assert "network_inconclusive" not in resultado


def test_transitorio_e_subclasse_de_oracle_queue_error() -> None:
    """Premissa dos `except`: a subclasse precisa vir antes da classe base."""
    assert issubclass(OracleQueueTransientError, OracleQueueError)


def test_bloqueio_da_fila_vira_blocked_guard_sem_repetir(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _explicar_falso(
        monkeypatch, [OracleQueueBlockedError("blocked", "DML proibido")]
    )

    resultado = _com_sentinela_da_fila(SQL, _opcoes())

    assert resultado["status"] == "blocked_guard"
    assert len(chamadas) == 1
    assert dormidas == []


def test_bloqueio_da_fila_no_smoke_vira_blocked_guard(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    _explicar_falso(monkeypatch, [1.0])
    monkeypatch.setattr(vs, "verificar_objetos_fila", lambda *_a, **_k: None)

    def falso_exec(*_a: Any, **_k: Any) -> Any:
        raise OracleQueueBlockedError("blocked", "DML proibido")

    monkeypatch.setattr(vs, "executar_consulta_fila", falso_exec)

    resultado = _com_sentinela_da_fila(SQL, _opcoes(execute=True))

    assert resultado["status"] == "blocked_guard"
    assert dormidas == []

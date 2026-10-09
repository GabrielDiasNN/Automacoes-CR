"""Testes unitários do retry de `_oracle_stage_with_retry` e do clamp de `--attempts`
em Tools/oracle/validar_sql_oracle.py (sem tocar o Oracle)."""

import sys
from pathlib import Path
from typing import Any

import pytest
from tests.carregadores_modulos import (
    acessar_privado as _priv,
    carregar_tool_oracle as _carregar,
)

vs = _carregar("validar_sql_oracle")
_oracle_stage_with_retry = _priv(vs, "_oracle_stage_with_retry")

pytestmark = pytest.mark.unitario

SQL = "select 1 from dual"
# Marcador real de queda de sessão (oracle_session.SESSION_DROP_MARKERS).
QUEDA = "DatabaseError: ORA-00028: sua sessao foi eliminada"
# Erro de SQL: não é queda de rede e não deve ser repetido.
ERRO_SQL = "DatabaseError: ORA-00942: tabela ou view nao existe"
# Prazo de conexão estourado (`connect_within`): não é queda e não deve ser repetido.
TIMEOUT_CONEXAO = "TimeoutError: Conexão Oracle excedeu 120s."


def _fila(
    monkeypatch: pytest.MonkeyPatch, respostas: list[dict[str, Any]]
) -> list[int]:
    """Troca `_oracle_stage` por uma fila de respostas; devolve o contador de chamadas."""
    chamadas: list[int] = []

    def falso(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        chamadas.append(1)
        return dict(respostas[len(chamadas) - 1])

    monkeypatch.setattr(vs, "_oracle_stage", falso)
    return chamadas


@pytest.fixture(name="dormidas")
def _dormidas(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Registra as esperas do retry em vez de dormir de verdade."""
    esperas: list[float] = []
    monkeypatch.setattr(vs.time, "sleep", esperas.append)
    return esperas


def _opcoes(tentativas: int = vs.MAX_ATTEMPTS) -> Any:
    return vs.RunOptions(
        timeout=120,
        execute=True,
        explicit_binds={},
        guard=Path("guard_sql.py"),
        attempts=tentativas,
    )


def test_sucesso_na_primeira_tentativa_nao_repete_nem_dorme(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _fila(monkeypatch, [{"status": "validated", "smoke": "pass", "rows": 1}])

    resultado = _oracle_stage_with_retry(SQL, 0, None, _opcoes())

    assert len(chamadas) == 1
    assert dormidas == []
    assert resultado["status"] == "validated"
    assert resultado["attempts"] == 1
    assert "network_inconclusive" not in resultado


def test_queda_de_sessao_repete_com_espera_crescente_ate_o_sucesso(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _fila(
        monkeypatch,
        [
            {"status": "oracle_error", "error": QUEDA},
            {"status": "oracle_error", "error": QUEDA},
            {"status": "validated", "smoke": "pass", "rows": 1},
        ],
    )

    resultado = _oracle_stage_with_retry(SQL, 0, None, _opcoes())

    assert len(chamadas) == 3
    assert dormidas == [5, 10]
    assert resultado["status"] == "validated"
    assert resultado["attempts"] == 3
    assert "network_inconclusive" not in resultado


def test_queda_em_todas_as_tentativas_marca_resultado_inconclusivo(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    """Contrato com MAX_ATTEMPTS = 5: cinco chamadas e quatro esperas (nenhuma após a última)."""
    chamadas = _fila(monkeypatch, [{"status": "oracle_error", "error": QUEDA}] * 5)

    resultado = _oracle_stage_with_retry(SQL, 0, None, _opcoes())

    assert len(chamadas) == 5
    assert dormidas == [5, 10, 15, 20]
    assert resultado["attempts"] == 5
    assert resultado["network_inconclusive"] is True


def test_erro_de_sql_real_nao_repete_nem_marca_queda(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _fila(monkeypatch, [{"status": "oracle_error", "error": ERRO_SQL}])

    resultado = _oracle_stage_with_retry(SQL, 0, None, _opcoes())

    assert len(chamadas) == 1
    assert dormidas == []
    assert resultado["attempts"] == 1
    assert "network_inconclusive" not in resultado


@pytest.mark.parametrize(
    "resposta",
    [
        {"status": "timeout", "error": TIMEOUT_CONEXAO},
        {"status": "parse_ok_smoke_timeout", "parse": "pass", "smoke": "timeout"},
    ],
    ids=["conexao", "execucao"],
)
def test_timeout_de_conexao_ou_execucao_nao_repete(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float], resposta: dict[str, Any]
) -> None:
    """Timeout de conexão (sessão travada) e de execução (consulta lenta), sem
    marcador de queda, não é queda de rede: não é repetido.

    Repetir multiplicaria o pior caso por arquivo (ver `DEFAULT_TIMEOUT`).
    """
    chamadas = _fila(monkeypatch, [resposta])

    resultado = _oracle_stage_with_retry(SQL, 0, None, _opcoes())

    assert len(chamadas) == 1
    assert dormidas == []
    assert resultado["attempts"] == 1
    assert "network_inconclusive" not in resultado


def test_uma_tentativa_roda_uma_vez_sem_dormir(
    monkeypatch: pytest.MonkeyPatch, dormidas: list[float]
) -> None:
    chamadas = _fila(monkeypatch, [{"status": "oracle_error", "error": QUEDA}])

    resultado = _oracle_stage_with_retry(SQL, 0, None, _opcoes(tentativas=1))

    assert len(chamadas) == 1
    assert dormidas == []
    assert resultado["attempts"] == 1
    assert resultado["network_inconclusive"] is True


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [("0", 1), ("-3", 1), ("1", 1), ("3", 3)],
)
def test_attempts_do_cli_tem_no_minimo_uma_tentativa(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pedido: str,
    esperado: int,
) -> None:
    """`main()` aplica `max(1, --attempts)`; conexão e validação são substituídas."""
    raiz = tmp_path.resolve()
    sql = raiz / "q.sql"
    sql.write_text(SQL + "\n", encoding="utf-8")
    capturadas: list[int] = []

    def valida_falsa(path: Path, _creds: Any, options: Any) -> dict[str, Any]:
        capturadas.append(options.attempts)
        return {"file": path.name, "status": "validated"}

    monkeypatch.setattr(vs, "ROOT", raiz)
    monkeypatch.setattr(vs, "load_dotenv", lambda *_a, **_k: False)
    monkeypatch.setattr(vs, "resolve_guard", lambda: raiz / "guard_sql.py")
    monkeypatch.setattr(vs, "resolve_oracle_credentials", lambda *_a, **_k: object())
    monkeypatch.setattr(vs, "init_thick_mode", lambda *_a, **_k: None)
    monkeypatch.setattr(vs, "_validate_one", valida_falsa)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validar_sql_oracle.py",
            "--root",
            str(raiz),
            "--file",
            str(sql),
            f"--attempts={pedido}",
            "--out",
            str(raiz / "saida.json"),
        ],
    )

    assert vs.main() == 0
    assert capturadas == [esperado]

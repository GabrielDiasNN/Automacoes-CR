"""Testes unitários de lib/python/oracle_retry.py (circuit breaker + retry Oracle)."""

import json
import os
import sys
import time
from collections.abc import Iterator

import oracledb
import pytest
import stamina.instrumentation

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "python"
    ),
)

from oracle_retry import (  # noqa: E402  pylint: disable=wrong-import-position
    CircuitBreakerError,
    make_oracle_retry,
)


@pytest.fixture(autouse=True)
def _reset_stamina_hooks() -> Iterator[None]:
    """`make_oracle_retry` registra um hook global no stamina; restaura o default
    ao fim de cada teste para não vazar entre casos/arquivos."""
    yield
    stamina.instrumentation.set_on_retry_hooks(None)


def test_circuit_breaker_abre_apos_n_falhas_consecutivas() -> None:
    # pybreaker converte para CircuitBreakerError a propria falha que atinge o
    # fail_max (nao apenas as chamadas seguintes): fail_max=2 -> 1 erro real,
    # 2a chamada ja abre o circuito e vira CircuitBreakerError.
    decorator = make_oracle_retry(
        fail_max=2, reset_timeout=60, attempts=1, wait_initial=0
    )

    @decorator
    def sempre_falha() -> None:
        raise oracledb.DatabaseError("erro simulado")

    with pytest.raises(oracledb.DatabaseError):
        sempre_falha()

    with pytest.raises(CircuitBreakerError):
        sempre_falha()

    with pytest.raises(CircuitBreakerError):
        sempre_falha()  # circuito ja aberto: nem chega a invocar a funcao


def test_circuit_breaker_half_open_permite_tentativa() -> None:
    decorator = make_oracle_retry(
        fail_max=1, reset_timeout=0.05, attempts=1, wait_initial=0
    )
    estado = {"falhar": True}

    @decorator
    def instavel() -> str:
        if estado["falhar"]:
            raise oracledb.DatabaseError("boom")
        return "ok"

    with pytest.raises(CircuitBreakerError):
        instavel()  # fail_max=1: abre na propria 1a falha

    time.sleep(0.1)  # aguarda reset_timeout: circuito vai para half-open
    estado["falhar"] = False

    assert instavel() == "ok"


def test_circuit_breaker_fecha_apos_sucesso_em_half_open() -> None:
    decorator = make_oracle_retry(
        fail_max=2, reset_timeout=0.05, attempts=1, wait_initial=0
    )
    estado = {"falhar": True}

    @decorator
    def instavel() -> str:
        if estado["falhar"]:
            raise oracledb.DatabaseError("boom")
        return "ok"

    with pytest.raises(oracledb.DatabaseError):
        instavel()
    with pytest.raises(CircuitBreakerError):
        instavel()  # atinge fail_max=2: abre

    time.sleep(0.1)
    estado["falhar"] = False
    assert instavel() == "ok"  # half-open -> sucesso -> fecha totalmente

    # Se o circuito fechou de fato (contador resetado), uma falha isolada volta
    # a propagar como erro real (nao CircuitBreakerError) - fail_max=2 exige
    # 2 falhas consecutivas para abrir de novo.
    estado["falhar"] = True
    with pytest.raises(oracledb.DatabaseError):
        instavel()
    estado["falhar"] = False
    assert instavel() == "ok"


def test_stamina_retry_tenta_multiplas_vezes_antes_de_suceder() -> None:
    decorator = make_oracle_retry(
        fail_max=5,
        reset_timeout=60,
        attempts=3,
        wait_initial=0.01,
        wait_max=0.01,
        wait_jitter=0,
    )
    chamadas = {"n": 0}

    @decorator
    def instavel() -> str:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise oracledb.DatabaseError("transiente")
        return "ok"

    resultado = instavel()

    assert resultado == "ok"
    assert chamadas["n"] == 3


def test_stamina_bridge_emite_retry_attempt_estruturado(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1: a retentativa interna do Oracle (stamina) vira evento `retry.attempt`
    no envelope do schema — não a chave crua `stamina.retry_scheduled` que o
    `LoggingOnRetryHook` default do stamina despejava em WARNING."""
    monkeypatch.setenv("HUB_LOG_STRUCTURED", "1")
    monkeypatch.setenv("HUB_AUTOMATION", "OBs Restricao Branco")
    monkeypatch.setenv("HUB_EXEC_ID", "CRON_6_teste")
    monkeypatch.setenv("HUB_TRACE_ID", "orb-20260101T000000Z-0000")
    monkeypatch.setenv("HUB_STEP", "extract")

    decorator = make_oracle_retry(
        fail_max=5,
        reset_timeout=60,
        attempts=3,
        wait_initial=0.01,
        wait_max=0.01,
        wait_jitter=0,
    )
    chamadas = {"n": 0}

    @decorator
    def instavel() -> str:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise oracledb.DatabaseError("transiente")
        return "ok"

    assert instavel() == "ok"

    out = capsys.readouterr().out
    assert "stamina.retry_scheduled" not in out
    eventos = [json.loads(linha) for linha in out.splitlines() if linha.strip()]
    retries = [e for e in eventos if e.get("event") == "retry.attempt"]
    assert len(retries) == 2  # 2 falhas transientes -> 2 retentativas agendadas
    for evt in retries:
        assert evt["component"] == "python_domain"
        assert evt["step"] == "extract"
        assert evt["automation"] == "OBs Restricao Branco"
        assert evt["trace_id"] == "orb-20260101T000000Z-0000"
        assert evt["level"] == "WARN"
        assert evt["max_attempts"] == 3
        assert 1 <= evt["attempt"] <= 3


def test_stamina_bridge_modo_legado_escreve_linha_humana_em_stderr(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem `HUB_LOG_STRUCTURED` o bridge cai numa linha `[RETRY]` legível em
    stderr — nunca a chave crua do stamina."""
    monkeypatch.delenv("HUB_LOG_STRUCTURED", raising=False)

    decorator = make_oracle_retry(
        fail_max=5, reset_timeout=60, attempts=2, wait_initial=0.01, wait_jitter=0
    )
    chamadas = {"n": 0}

    @decorator
    def instavel() -> str:
        chamadas["n"] += 1
        if chamadas["n"] < 2:
            raise oracledb.DatabaseError("transiente")
        return "ok"

    assert instavel() == "ok"
    captured = capsys.readouterr()
    assert "stamina.retry_scheduled" not in (captured.out + captured.err)
    assert "[RETRY]" in captured.err


def test_stamina_retry_nao_intercepta_excecoes_fora_do_contrato() -> None:
    decorator = make_oracle_retry(
        fail_max=5, reset_timeout=60, attempts=3, wait_initial=0.01
    )
    chamadas = {"n": 0}

    @decorator
    def falha_generica() -> None:
        chamadas["n"] += 1
        raise ValueError("nao deveria ser retentado")

    with pytest.raises(ValueError):
        falha_generica()

    assert chamadas["n"] == 1


def test_dois_decoradores_com_attempts_distintos_reportam_o_proprio_limite(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`set_on_retry_hooks` e estado global do processo. Fixar `max_attempts` no
    closure do hook fazia a ULTIMA chamada de `make_oracle_retry` reescrever o
    limite reportado por todas as funcoes ja decoradas: um extrator com
    attempts=2 logava "retentativa 2/5" depois que outro registrasse attempts=5.
    O limite vive num registro por callable, entao cada uma reporta o seu.
    """
    monkeypatch.delenv("HUB_LOG_STRUCTURED", raising=False)

    dec_curto = make_oracle_retry(
        fail_max=9, reset_timeout=60, attempts=2, wait_initial=0.01, wait_jitter=0
    )

    @dec_curto
    def extracao_curta() -> str:
        raise oracledb.DatabaseError("transiente")

    # Segundo decorador, limite MAIOR, registrado depois — era o que sequestrava
    # o hook global e contaminava `extracao_curta`.
    dec_longo = make_oracle_retry(
        fail_max=9, reset_timeout=60, attempts=5, wait_initial=0.01, wait_jitter=0
    )

    @dec_longo
    def extracao_longa() -> str:
        raise oracledb.DatabaseError("transiente")

    with pytest.raises(oracledb.DatabaseError):
        extracao_curta()
    err_curta = capsys.readouterr().err
    assert "/2 " in err_curta, f"esperado limite 2, veio: {err_curta}"
    assert "/5 " not in err_curta

    with pytest.raises(oracledb.DatabaseError):
        extracao_longa()
    err_longa = capsys.readouterr().err
    assert "/5 " in err_longa, f"esperado limite 5, veio: {err_longa}"


def test_retry_de_terceiro_nao_inventa_max_attempts(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um `stamina.retry` que nao passou por `make_oracle_retry` nao esta no
    registro; o hook cai no rastro humano em vez de emitir um envelope com
    `max_attempts` inventado (que violaria o contrato do schema)."""
    monkeypatch.setenv("HUB_LOG_STRUCTURED", "1")
    make_oracle_retry(attempts=3, wait_initial=0.01)  # instala o hook global

    @stamina.retry(on=ValueError, attempts=2, wait_initial=0.01, wait_jitter=0)
    def alheia() -> None:
        raise ValueError("x")

    with pytest.raises(ValueError):
        alheia()

    captured = capsys.readouterr()
    assert "[RETRY]" in captured.err
    assert "retry.attempt" not in captured.out

"""Testes unitários de lib/python/oracle_retry.py (circuit breaker + retry Oracle)."""

import os
import sys
import time

import oracledb
import pytest

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

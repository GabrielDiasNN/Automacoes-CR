"""E2E da fila Oracle: estação -> oracle_queue.execute_query -> fila SMB -> worker (TSplus) -> Oracle.

Uso:
    C:\\Automacoes\\.venv\\Scripts\\python.exe Tools\\oracle\\teste_e2e_fila_oracle.py [--bench]

Só consultas leves (DUAL e dicionário). Os casos de bloqueio nunca chegam ao banco.
`--bench` acrescenta latência (mediana de 30) e volume (20 mil e 100 mil linhas).
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib" / "python"))
from oracle_queue import (  # noqa: E402
    OracleQueueBlockedError,
    OracleQueueError,
    QueueResult,
    execute_query,
    get_queue_dir,
)

TIMEOUT = 110
VERSAO_ESPERADA = os.environ.get("WORKER_VERSAO", "2.5.6")
resultados: list[tuple[str, bool]] = []


def caso(nome: str) -> Callable[[Callable[[], Any]], None]:
    def deco(fn: Callable[[], Any]) -> None:
        t0 = time.time()
        try:
            detalhe, passou = fn() or "", True
        except AssertionError as e:
            detalhe, passou = f"assert: {e}", False
        # O roteiro registra qualquer falha do caso e segue para o próximo.
        except Exception as e:  # noqa: BLE001  pylint: disable=broad-exception-caught
            detalhe, passou = f"{type(e).__name__}: {e}", False
        resultados.append((nome, passou))
        print(
            f"{'ok   ' if passou else 'FALHA'} {nome}: {detalhe} ({time.time() - t0:.1f}s)",
            flush=True,
        )

    return deco


def q(sql: str, params: dict[str, Any] | None = None) -> QueueResult:
    return execute_query(sql, timeout_seconds=TIMEOUT, params=params)


def espera(sql: str, exc: type[OracleQueueError], kind: str) -> str:
    try:
        q(sql)
    except exc as e:
        assert e.kind == kind, (e.kind, e.message)
        return e.message[:90]
    raise AssertionError("esperava erro, veio resultado")


print("Fila:", get_queue_dir())
try:
    _arquivos_previos = {
        f for f in os.listdir(get_queue_dir()) if f.lower().startswith(("req_", "res_"))
    }
except OSError:
    _arquivos_previos = set()


@caso(f"worker v{VERSAO_ESPERADA} respondendo")
def _() -> str:
    r = q("SELECT 1 AS UM FROM DUAL")
    assert r.worker == VERSAO_ESPERADA, r.worker
    return f"worker={r.worker}"


@caso("tipos nativos: int, texto com acento e euro, float, datetime, None")
def _() -> str:
    r = q(
        "SELECT 1 AS UM, 'a\u00e7\u00e3o \u20ac' AS TXT, 1.5 AS NUM, SYSDATE AS DT, NULL AS NULO FROM DUAL"
    )
    assert r.columns == ["UM", "TXT", "NUM", "DT", "NULO"], r.columns
    um, txt, num, dt, nulo = r.rows[0]
    assert (
        um == 1 and txt == "a\u00e7\u00e3o \u20ac" and num == 1.5 and nulo is None
    ), r.rows
    assert (
        isinstance(dt, datetime) and abs((datetime.now() - dt).total_seconds()) < 600
    ), dt
    return f"types={r.types} linha={r.rows[0]}"


@caso("data exata (DATE com segundos) e numero negativo/fracionario")
def _() -> str:
    r = q(
        "SELECT TO_DATE('2026-11-08 17:05:09','YYYY-MM-DD HH24:MI:SS') AS DT, -1234.5678 AS N FROM DUAL"
    )
    assert r.rows == [(datetime(2026, 11, 8, 17, 5, 9), -1234.5678)], r.rows
    return str(r.rows[0])


@caso("virgula, aspas, barra e quebra de linha no texto")
def _() -> str:
    r = q("SELECT 'a,\"b\" \\ x' || CHR(13) || CHR(10) || 'y' AS X FROM DUAL")
    assert r.rows == [('a,"b" \\ x\r\ny',)], r.rows
    return repr(r.rows[0][0])


@caso("consulta sem linhas")
def _() -> None:
    r = q("SELECT 1 AS X FROM DUAL WHERE 1 = 0")
    assert not r.rows and r.row_count == 0 and r.columns == ["X"]


@caso("SOMENTE LEITURA: consulta roda dentro de transacao aberta pelo worker")
def _() -> str:
    r = q("SELECT DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AS TX FROM DUAL")
    assert r.rows[0][0], "sem transacao: SET TRANSACTION READ ONLY nao foi aplicado"
    return f"transacao={r.rows[0][0]}"


@caso("erro Oracle -> OracleQueueError(kind=oracle)")
def _() -> str:
    return espera(
        "SELECT * FROM TABELA_INEXISTENTE_E2E_XYZ", OracleQueueError, "oracle"
    )


@caso("bloqueio DELETE -> OracleQueueBlockedError")
def _() -> str:
    return espera(
        "DELETE FROM TABELA_INEXISTENTE_E2E_XYZ", OracleQueueBlockedError, "blocked"
    )


@caso("bloqueio truque '--' + WITH FUNCTION")
def _() -> str:
    sql = "WITH FUNCTION f RETURN NUMBER IS v VARCHAR2(9):='--'; BEGIN RETURN 1; END;\nSELECT f FROM DUAL"
    return espera(sql, OracleQueueBlockedError, "blocked")


@caso("bloqueio FOR UPDATE")
def _() -> str:
    return espera("SELECT * FROM DUAL FOR UPDATE", OracleQueueBlockedError, "blocked")


@caso("requisicao vazia -> kind=request")
def _() -> str:
    return espera("", OracleQueueError, "request")


@caso("comentarios no inicio do SQL (-- e /* */) e binds n/s/d/None")
def _() -> str:
    r = q("-- titulo\n/* bloco */\nSELECT 1 AS X FROM DUAL -- fim")
    assert r.rows == [(1,)], r.rows
    dt = datetime(2026, 11, 8, 17, 5, 9)
    r = q(
        "SELECT :N AS N, :S AS S, :D AS D, :Z AS Z FROM DUAL",
        {"N": -1.5, "S": 'ação, "x"', "D": dt, "Z": None},
    )
    assert r.rows == [(-1.5, 'ação, "x"', dt, None)], r.rows
    return str(r.rows[0])


@caso("comentario '--' no meio com LF (derrubava o OraOLEDB) e LF dentro de texto")
def _() -> str:
    r = q(
        "WITH\n-- 1. primeira CTE\nA AS (SELECT 1 AS X FROM DUAL), -- fim\n"
        "B AS (SELECT 'l1\nl2' AS T FROM DUAL)\nSELECT A.X, B.T -- colunas\nFROM A, B\n"
    )
    assert r.rows == [(1, "l1\nl2")], r.rows
    return repr(r.rows[0])


@caso("8 requisicoes simultaneas, cada uma com seu resultado")
def _() -> str:
    def um(i: int) -> tuple[int, Any]:
        return i, q("SELECT :ID AS ID FROM DUAL", {"ID": i}).rows

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(um, range(1, 9)))
    erradas = [(i, r) for i, r in res if r != [(i,)]]
    assert not erradas, erradas
    return "8/8 corretas"


SQL_VOLUME = (
    "SELECT LEVEL AS N, 'texto da linha ' || LEVEL AS TXT, LEVEL / 3 AS FRAC, "
    "SYSDATE - LEVEL / 1440 AS DT FROM DUAL CONNECT BY LEVEL <= :N"
)

if "--bench" in sys.argv:

    @caso("latencia de 1 linha (30 amostras)")
    def _() -> str:
        lat = []
        for _ in range(30):
            t0 = time.perf_counter()
            q("SELECT 1 AS UM FROM DUAL")
            lat.append((time.perf_counter() - t0) * 1000)
        lat.sort()
        return f"p50={statistics.median(lat):.0f}ms p90={lat[26]:.0f}ms max={lat[-1]:.0f}ms"

    def _bench_volume(n: int) -> str:
        medidas: list[tuple[float, QueueResult]] = []
        for _ in range(3):
            t0 = time.perf_counter()
            r = q(SQL_VOLUME, {"N": n})
            medidas.append((time.perf_counter() - t0, r))
            assert (
                r.row_count == n
                and r.rows[-1][0] == n
                and isinstance(r.rows[-1][3], datetime)
            )
        dt, r = min(medidas, key=lambda m: m[0])
        return (
            f"{dt:.2f}s ponta a ponta | worker {r.elapsed_ms} ms "
            f"(banco {r.raw_meta['db_ms']}, formatar {r.raw_meta['format_ms']}) | {n / dt:,.0f} linhas/s"
        )

    for volume in (20000, 100000):
        caso(f"volume {volume} linhas (melhor de 3)")(partial(_bench_volume, volume))


@caso("fila limpa ao final (sem req_/res_ novos sobrando)")
def _() -> None:
    time.sleep(1.5)
    sobra = sorted(
        f
        for f in os.listdir(get_queue_dir())
        if f.lower().startswith(("req_", "res_")) and f not in _arquivos_previos
    )
    assert not sobra, sobra


ok = sum(1 for _, o in resultados if o)
print(f"\nRESULTADO: {ok}/{len(resultados)} ok")
sys.exit(0 if ok == len(resultados) else 1)

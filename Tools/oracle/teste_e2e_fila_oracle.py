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
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib" / "python"))
from oracle_queue import (
    OracleQueueBlockedError,
    OracleQueueError,
    QueueRequestOptions,
    QueueResult,
    execute_query,
    get_queue_dir,
    strip_sql_comments,
)

TIMEOUT = 110
VERSAO_ESPERADA = os.environ.get("WORKER_VERSAO", "2.6.2")
SQL_VOLUME = (
    "SELECT LEVEL AS N, 'texto da linha ' || LEVEL AS TXT, LEVEL / 3 AS FRAC, "
    "SYSDATE - LEVEL / 1440 AS DT FROM DUAL CONNECT BY LEVEL <= :N"
)


_CasoFn = Callable[[Callable[[], Any]], None]


_CasoRegistrador = Callable[[str], _CasoFn]


@dataclass
class _ClienteFila:
    """Consulta pela fila com a marca do E2E e guarda os ids (req_<id>) gerados:
    só as respostas desses ids entram na conferência de fila limpa."""

    e2e_tag: str
    ids: set[str] = field(default_factory=set)

    def __call__(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        max_rows: int | None = None,
        strip_comments: bool = False,
    ) -> QueueResult:
        resultado = execute_query(
            sql,
            timeout_seconds=TIMEOUT,
            params=params,
            options=QueueRequestOptions(
                meta=f"exec_id={self.e2e_tag}",
                max_rows=max_rows,
                strip_comments=strip_comments,
            ),
        )
        if resultado.req_id:
            self.ids.add(resultado.req_id)
        return resultado


_EsperaFn = Callable[[str, type[OracleQueueError], str], str]


def _executar_caso(resultados: list[tuple[str, bool]], nome: str) -> _CasoFn:
    def deco(fn: Callable[[], Any]) -> None:
        t0 = time.time()
        try:
            detalhe, passou = fn() or "", True
        except AssertionError as e:
            detalhe, passou = f"assert: {e}", False
        # Residual: o roteiro e2e registra qualquer falha do caso (inclusive erro de
        # Oracle ou de fila, de tipos variados) e segue para o proximo, sem abortar a
        # bateria. Estreitar mudaria o relatorio para uma falha sem registro.
        except Exception as e:  # pylint: disable=broad-exception-caught
            detalhe, passou = f"{type(e).__name__}: {e}", False
        resultados.append((nome, passou))
        print(
            f"{'ok   ' if passou else 'FALHA'} {nome}: {detalhe} ({time.time() - t0:.1f}s)",
            flush=True,
        )

    return deco


def _executar_casos_basicos(caso: _CasoRegistrador, q: _ClienteFila) -> None:
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
            isinstance(dt, datetime)
            and abs((datetime.now() - dt).total_seconds()) < 600
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


def _executar_casos_seguranca(
    caso: _CasoRegistrador, q: _ClienteFila, espera: _EsperaFn
) -> None:
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
        return espera(
            "SELECT * FROM DUAL FOR UPDATE", OracleQueueBlockedError, "blocked"
        )

    @caso("requisicao vazia -> kind=request")
    def _() -> str:
        return espera("", OracleQueueError, "request")

    @caso("bloqueia @dblink e pacotes perigosos (ex.: DBMS_LOCK)")
    def _() -> str:
        for sql_perigoso in (
            "SELECT * FROM DUAL@OUTRO_BANCO",
            "SELECT DBMS_LOCK.SLEEP(1) FROM DUAL",
        ):
            try:
                q(sql_perigoso)
            except OracleQueueBlockedError:
                continue
            raise AssertionError(f"Esperado bloqueio para: {sql_perigoso}")
        return "dblink + pacote perigoso bloqueados"


def _executar_casos_sintaxe_e_concorrencia(
    caso: _CasoRegistrador, q: _ClienteFila, espera: _EsperaFn, e2e_tag: str
) -> None:
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

    @caso("ponto-e-virgula final com comentario apos ';' funciona (v2.6.1+)")
    def _() -> str:
        r = q("SELECT 42 AS RESPOSTA FROM DUAL; -- comentario final")
        assert r.rows == [(42,)], r.rows
        return str(r.rows[0])

    @caso("max_rows limita linhas retornadas pelo worker")
    def _() -> str:
        r = q("SELECT LEVEL AS N FROM DUAL CONNECT BY LEVEL <= 5", max_rows=2)
        assert r.row_count == 2 and r.rows == [(1,), (2,)], r.rows
        return f"row_count={r.row_count}"

    @caso("literal q'[...]' preservado em strip_sql_comments e bloqueado no worker")
    def _() -> str:
        sql = "SELECT q'[texto -- ; /* literal */]' AS Q FROM DUAL -- comentario"
        limpo = strip_sql_comments(sql).strip()
        assert limpo == "SELECT q'[texto -- ; /* literal */]' AS Q FROM DUAL", limpo
        msg = espera(limpo, OracleQueueBlockedError, "blocked")
        assert "Literal q'...'" in msg, msg
        return msg

    @caso("action explain com placeholder :P retorna DBMS_XPLAN")
    def _() -> str:
        r = execute_query(
            "SELECT 1 AS X FROM DUAL WHERE 1 = :P",
            timeout_seconds=TIMEOUT,
            options=QueueRequestOptions(
                action="explain", meta=f"exec_id={e2e_tag};tool=explain"
            ),
        )
        linhas = "\n".join(str(row[0]) for row in r.rows if row)
        assert "PLAN_TABLE_OUTPUT" in r.columns or "Plan hash value" in linhas, linhas
        assert "Plan hash value" in linhas or "FAST DUAL" in linhas, linhas
        return f"{r.row_count} linha(s) de plano"

    @caso("8 requisicoes simultaneas, cada uma com seu resultado")
    def _() -> str:
        def um(i: int) -> tuple[int, Any]:
            return i, q("SELECT :ID AS ID FROM DUAL", {"ID": i}).rows

        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(um, range(1, 9)))
        erradas = [(i, r) for i, r in res if r != [(i,)]]
        assert not erradas, erradas
        return "8/8 corretas"


def _executar_bench(caso: _CasoRegistrador, q: _ClienteFila) -> None:
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


def _verificar_fila_limpa(
    queue_dir: str,
    arquivos_previos: set[str],
    inicio_ts: float,
    e2e_tag: str,
    ids_do_teste: set[str],
) -> None:
    """Confere sobras só das requisições deste teste.

    `req_*` é do teste quando traz o `e2e_tag` no cabeçalho. `res_<id>.csv` é do teste
    quando `<id>` está em `ids_do_teste` (ids devolvidos por `execute_query`). Respostas
    de outros consumidores da pasta compartilhada nunca contam.
    """
    time.sleep(1.5)
    sobra: list[str] = []
    agora = time.time()
    for entry in os.scandir(queue_dir):
        nome_l = entry.name.lower()
        if not nome_l.startswith(("req_", "res_")) or entry.name in arquivos_previos:
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        if st.st_mtime < inicio_ts - 1.0:
            continue
        if nome_l.startswith("req_"):
            try:
                head = (
                    Path(entry.path)
                    .read_bytes()[:1024]
                    .decode("cp1252", errors="ignore")
                )
            except OSError:
                continue
            if e2e_tag in head:
                sobra.append(entry.name)
        elif (
            entry.name[4:-4] in ids_do_teste
            and nome_l.endswith(".csv")
            and agora - st.st_mtime >= 1.0
        ):
            sobra.append(entry.name)
    assert not sobra, sorted(sobra)


def main() -> int:
    resultados: list[tuple[str, bool]] = []
    caso = partial(_executar_caso, resultados)
    e2e_tag = f"E2E_{os.getpid()}_{int(time.time())}"
    inicio_ts = time.time()
    q = _ClienteFila(e2e_tag)

    def espera(sql: str, exc: type[OracleQueueError], kind: str) -> str:
        try:
            q(sql)
        except exc as e:
            assert e.kind == kind, (e.kind, e.message)
            return e.message[:90]
        raise AssertionError("esperava erro, veio resultado")

    queue_dir = get_queue_dir()
    print("Fila:", queue_dir)
    try:
        arquivos_previos = {
            f for f in os.listdir(queue_dir) if f.lower().startswith(("req_", "res_"))
        }
    except OSError:
        arquivos_previos = set()

    _executar_casos_basicos(caso, q)
    _executar_casos_seguranca(caso, q, espera)
    _executar_casos_sintaxe_e_concorrencia(caso, q, espera, e2e_tag)
    if "--bench" in sys.argv:
        _executar_bench(caso, q)
    caso("fila limpa ao final (sem req_/res_ do E2E sobrando)")(
        lambda: _verificar_fila_limpa(
            queue_dir, arquivos_previos, inicio_ts, e2e_tag, q.ids
        )
    )

    ok = sum(1 for _, o in resultados if o)
    print(f"\nRESULTADO: {ok}/{len(resultados)} ok")
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())

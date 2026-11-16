"""Adaptador compartilhado do modo `queue` para as ferramentas de `Tools/oracle/`.

Permite que `mcp_server.py`, `validar_sql_oracle.py`, `medir_sql_oracle.py` e
`oracle_catalog.py` executem consultas read-only, verificações de objetos e
`EXPLAIN PLAN` via fila SMB (TSplus) quando `ORACLE_DRIVER_MODE=queue` está ativo,
sem depender de acesso TCP direto ao Oracle nem de Instant Client local.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any

from guard_sql import motivo_objetos_executaveis
from oracle_client import DRIVER_MODE_QUEUE, get_driver_mode
from oracle_queue import (
    OracleQueueError,
    QueueRequestOptions,
    QueueResult,
    apply_queue_deadline,
    check_worker_liveness,
    execute_query,
    get_queue_dir,
    strip_sql_comments,
)

# Token usado pelos CLIs em modo queue no lugar de `OracleCredentials`, sem colidir
# com dubles de teste que passam `creds=None` para caminhos diretos mockados.
QUEUE_MODE_SENTINEL: Any = object()

_RE_TRAILING_SEMI = re.compile(r";+\s*$")

# Falhas que uma consulta pela fila pode levantar (contrato de `execute_query`): erro
# do worker/Oracle/validador (OracleQueueError), share SMB ou prazo esgotado (OSError,
# que inclui TimeoutError) e bind ou opção inválida (ValueError).
ERROS_FILA: tuple[type[Exception], ...] = (OracleQueueError, OSError, ValueError)


def usar_fila_oracle() -> bool:
    """Retorna True quando o ambiente está configurado com ORACLE_DRIVER_MODE=queue."""
    return get_driver_mode() == DRIVER_MODE_QUEUE


def preparar_sql_fila(sql: str) -> str:
    """Remove comentários e ponto-e-vírgula final antes de submeter à fila."""
    sem_comentarios = strip_sql_comments(sql).strip()
    return _RE_TRAILING_SEMI.sub("", sem_comentarios).strip()


def _effective_timeout(timeout: float) -> float:
    """Prazo pedido pelo chamador, limitado só pelo prazo global (ORACLE_QUEUE_DEADLINE_EPOCH)."""
    return apply_queue_deadline(max(1.0, float(timeout)))


def _format_meta(exec_id_padrao: str, meta: Mapping[str, Any] | None = None) -> str:
    """`exec_id` puro, ou JSON com `exec_id` primeiro quando há outros campos.

    A chave `exec_id` de `meta`, se houver, substitui `exec_id_padrao`.
    """
    campos = dict(meta or {})
    exec_id = str(campos.pop("exec_id", exec_id_padrao))
    if not campos:
        return exec_id
    payload = {"exec_id": exec_id, **campos}
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def verificar_objetos_fila(
    consulta: str | None,
    timeout: float = 30.0,
    exec_id: str = "TOOLS_GUARD",
) -> str | None:
    """Executa a `consulta_verificacao` do guard_sql via fila e retorna o bloqueio, se houver."""
    if consulta is None:
        return None
    res = execute_query(
        consulta,
        timeout_seconds=_effective_timeout(timeout),
        options=QueueRequestOptions(
            strip_comments=True,
            meta=_format_meta(exec_id, {"tool": "guard_check"}),
        ),
    )
    motivo = motivo_objetos_executaveis(list(res.rows))
    return str(motivo) if motivo is not None else None


def executar_consulta_fila(
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
    meta: Mapping[str, Any] | None = None,
    max_rows: int | None = None,
) -> QueueResult:
    """Executa SQL read-only via fila SMB removendo comentários e `;` final.

    `meta` identifica o pedido na fila: a chave `exec_id` (padrão `TOOLS_SQL`) e os
    demais campos (por exemplo `tool`) vão no cabeçalho `--#meta`.
    """
    sql_limpo = preparar_sql_fila(sql)
    return execute_query(
        sql_limpo,
        params=params,
        timeout_seconds=_effective_timeout(timeout),
        options=QueueRequestOptions(
            meta=_format_meta("TOOLS_SQL", meta), max_rows=max_rows
        ),
    )


def explicar_plano_fila(
    sql: str,
    *,
    timeout: float = 60.0,
    exec_id: str = "TOOLS_EXPLAIN",
) -> tuple[list[str], float]:
    """Solicita `--#action:explain` ao worker Oracle e devolve `(linhas, duracao_ms)`."""
    sql_limpo = preparar_sql_fila(sql)
    started = time.perf_counter()
    res = execute_query(
        sql_limpo,
        timeout_seconds=_effective_timeout(timeout),
        options=QueueRequestOptions(
            action="explain", meta=_format_meta(exec_id, {"tool": "explain"})
        ),
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    linhas = [str(row[0]) for row in res.rows if row]
    return linhas, elapsed_ms


def status_fila_diagnostico() -> dict[str, Any]:
    """Snapshot leve de saúde da fila e do worker TSplus para check_connection."""
    info = check_worker_liveness(probe_signal_seconds=0.0)
    info["queue_dir"] = get_queue_dir()
    return info

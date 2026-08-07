"""Núcleo compartilhado de extração Oracle: credenciais, fetch, serialização e idempotência.

Extrai o padrão repetido nos 4 scripts de extração (Receitas Emitidas, OBs
Paradas Fase, Montagem de Terceirizados, Receitas Bloqueadas): resolver
credenciais do ambiente, conectar via Thick Mode, buscar linhas em lotes,
normalizar valores (datetime -> isoformat, strings -> strip) e calcular hash
sha256 para idempotência via state.json.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import oracledb
from oracle_client import init_oracle_thick_mode

LogFn = Callable[..., None]


@dataclass(frozen=True)
class OracleCredentials:
    user: str
    password: str
    dsn: str
    client_lib: str
    tns_admin: str | None


def resolve_oracle_credentials(
    log: LogFn,
    exec_id: str,
    *,
    default_dsn: str = "dbprd",
    require_tns_admin: bool = False,
    force_dsn: str | None = None,
) -> OracleCredentials | None:
    """Le e valida as credenciais Oracle do ambiente. Retorna None (e loga o motivo) se invalidas.

    `force_dsn` ignora ORACLE_CONNECT_STRING e usa sempre o valor informado
    (contrato de scripts que resolvem DSN via TNS alias fixo, ex.: Montagem
    de Terceirizados usa sempre "dbprd" independente do .env).
    """
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = (
        force_dsn
        if force_dsn is not None
        else os.environ.get("ORACLE_CONNECT_STRING", default_dsn)
    )
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get(
        "ORACLE_CLIENT_PATH"
    )
    tns_admin = os.environ.get("TNS_ADMIN")

    if not user or not password:
        log("Credenciais Oracle ausentes no ambiente.", "ERROR", exec_id)
        return None
    if not client_lib or not os.path.exists(client_lib):
        log("ORACLE_CLIENT_LIB_DIR invalido.", "ERROR", exec_id)
        return None
    if require_tns_admin and not tns_admin:
        log("TNS_ADMIN ausente no ambiente.", "ERROR", exec_id)
        return None

    return OracleCredentials(
        user=user,
        password=password,
        dsn=dsn,
        client_lib=client_lib,
        tns_admin=tns_admin,
    )


def init_thick_mode(creds: OracleCredentials, log: LogFn, exec_id: str) -> None:
    init_oracle_thick_mode(
        creds.client_lib,
        creds.tns_admin,
        lambda msg, lvl="INFO": log(msg, lvl, exec_id),
    )


def fetch_all(  # pylint: disable=too-many-arguments
    creds: OracleCredentials,
    sql: str,
    exec_id: str,
    log: LogFn,
    *,
    batch_size: int = 5000,
    cursor_arraysize: int | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[list[str], list[Any]]:
    """Conecta, executa a query e retorna (colunas, linhas) buscadas em lotes.

    Sem decorator de retry proprio: cada script decora a chamada com o
    make_oracle_retry() configurado para o seu proprio perfil de resiliencia.

    `params` sao bind variables passadas ao cursor. Valores SEMPRE via bind —
    nunca interpolados na string SQL.
    """
    log(f"Conectando ao Oracle (DSN: {creds.dsn})...", "INFO", exec_id)
    with oracledb.connect(
        user=creds.user, password=creds.password, dsn=creds.dsn
    ) as connection:
        cursor = connection.cursor()
        # Sem isto, o driver mantém o arraysize padrão (100) independente do
        # batch_size pedido: um fetchmany(5000) ainda exige ~50 round-trips de
        # rede ao Oracle para preencher um único lote em memória, em vez de 1.
        cursor.arraysize = (
            cursor_arraysize if cursor_arraysize is not None else batch_size
        )
        cursor.execute(sql, params or {})
        if not cursor.description:
            return [], []
        columns = [col[0] for col in cursor.description]
        rows: list[Any] = []
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            rows.extend(batch)
        log(
            f"Query executada com sucesso. Linhas retornadas: {len(rows)}",
            "INFO",
            exec_id,
        )
        return columns, rows


def serialize_rows(
    columns: list[str],
    rows: list[Any],
    *,
    sort_key: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    """Converte linhas Oracle em dicts, normalizando datetime (isoformat) e strings (strip)."""
    data: list[dict[str, Any]] = []
    for row in rows:
        # `strict=True`: colunas e valores vêm do mesmo cursor e devem ter o
        # mesmo tamanho. Divergência indica cursor corrompido — melhor falhar
        # alto que gerar registros silenciosamente truncados.
        record: dict[str, Any] = dict(zip(columns, row, strict=True))
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()
            elif isinstance(value, str) and value:
                record[key] = value.strip()
        data.append(record)
    if sort_key is not None:
        data.sort(key=sort_key)
    return data


def compute_hash(data: Any) -> str:
    """Calcula o sha256 hex de `data` serializado como JSON deterministico (sort_keys)."""
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_last_hash(state_path: str) -> str:
    """Le o last_hash do state.json existente. Retorna string vazia se ausente/invalido."""
    if not os.path.exists(state_path):
        return ""
    try:
        with open(state_path, encoding="utf-8") as f:
            return str(json.load(f).get("last_hash", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def write_state_tmp(state_path: str, current_hash: str) -> None:
    """Escreve state.json.tmp com o hash atual. O commit final e responsabilidade do run.ps1."""
    state_tmp_path = state_path + ".tmp"
    with open(state_tmp_path, "w", encoding="utf-8") as f:
        json.dump(
            {"last_hash": current_hash, "updated_at": datetime.now().isoformat()},
            f,
            ensure_ascii=False,
        )

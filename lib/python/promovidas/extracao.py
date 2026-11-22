"""Extracao Oracle somente leitura para consultas promovidas."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from oracle_extract import (
    fetch_all,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from oracle_retry import make_oracle_retry


def _carregar_guard(raiz: Path) -> Any:
    caminho = raiz / "lib" / "vendor" / "oracle-sql-guard" / "guard_sql.py"
    spec = importlib.util.spec_from_file_location("oracle_guard_canonico", str(caminho))
    if spec is None or spec.loader is None:
        raise ImportError(f"Guard SQL nao encontrado em {caminho}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _classificar_sql(raiz: Path, sql: str) -> dict[str, Any]:
    """Classifica o SQL via guard canonico; levanta ValueError se bloqueado."""
    guard = _carregar_guard(raiz)
    resultado: dict[str, Any] = guard.classificar(sql, exigir_limite=False)
    if not bool(resultado.get("permitido", False)):
        motivos = resultado.get("motivos") or ["SQL bloqueado pelo guard"]
        raise ValueError(
            f"SQL bloqueado pelo guard somente leitura: {'; '.join(motivos)}"
        )
    return resultado


def validar_sql_somente_leitura(raiz: Path, sql: str) -> None:
    """Passa o SQL pelo guard canonico (estatico); levanta ValueError se bloqueado."""
    _classificar_sql(raiz, sql)


@make_oracle_retry(attempts=3)
def _fetch_com_retry(
    creds: Any,
    sql: str,
    *,
    exec_id: str,
    log_fn: Any,
    automacao: str,
) -> tuple[list[str], list[Any]]:
    return fetch_all(
        creds,
        sql,
        log=log_fn,
        exec_id=exec_id,
        automacao=automacao,
    )


def executar_consulta_promovida(
    raiz: Path,
    sql_path: Path,
    *,
    automacao: str,
    exec_id: str,
    log_fn: Any,
) -> list[dict[str, Any]]:
    """Valida e executa ``consulta.sql`` pela fila/driver configurado no ``.env``."""
    load_dotenv(str(raiz / ".env"), override=True)
    sql = sql_path.read_text(encoding="utf-8-sig").strip()
    if not sql:
        raise ValueError(f"Arquivo SQL vazio: {sql_path}")

    analise = _classificar_sql(raiz, sql)

    creds = resolve_oracle_credentials(log_fn, exec_id)
    if creds is None:
        raise RuntimeError("Credenciais Oracle ausentes ou invalidas no .env.")
    init_thick_mode(creds, log_fn, exec_id)

    consulta_verif = analise.get("consulta_verificacao")
    if isinstance(consulta_verif, str) and consulta_verif.strip():
        _, verif_rows = _fetch_com_retry(
            creds,
            consulta_verif,
            exec_id=exec_id,
            log_fn=log_fn,
            automacao=automacao,
        )
        if verif_rows:
            raise ValueError(
                "Consulta bloqueada: objeto(s) nao-tabela detectado(s) "
                f"({verif_rows[:5]})."
            )

    cols, raw_rows = _fetch_com_retry(
        creds,
        sql,
        exec_id=exec_id,
        log_fn=log_fn,
        automacao=automacao,
    )
    return list(serialize_rows(cols, raw_rows))

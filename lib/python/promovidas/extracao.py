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


def _carregar_guard(raiz: Path) -> Any:
    caminho = raiz / "lib" / "vendor" / "oracle-sql-guard" / "guard_sql.py"
    spec = importlib.util.spec_from_file_location("oracle_guard_canonico", str(caminho))
    if spec is None or spec.loader is None:
        raise ImportError(f"Guard SQL nao encontrado em {caminho}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validar_sql_somente_leitura(raiz: Path, sql: str) -> None:
    """Passa o SQL pelo guard canonico (estatico); levanta ValueError se bloqueado."""
    guard = _carregar_guard(raiz)
    resultado = guard.classificar(sql, exigir_limite=False)
    if not bool(resultado.get("permitido", False)):
        motivos = resultado.get("motivos") or ["SQL bloqueado pelo guard"]
        raise ValueError(
            f"SQL bloqueado pelo guard somente leitura: {'; '.join(motivos)}"
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

    validar_sql_somente_leitura(raiz, sql)

    creds = resolve_oracle_credentials(log_fn, exec_id)
    if creds is None:
        raise RuntimeError("Credenciais Oracle ausentes ou invalidas no .env.")
    init_thick_mode(creds, log_fn, exec_id)
    cols, raw_rows = fetch_all(
        creds,
        sql,
        log=log_fn,
        exec_id=exec_id,
        automacao=automacao,
    )
    return list(serialize_rows(cols, raw_rows))

"""guard_sql.py local do Hub de Automações.

Wrapper para o guard_sql canônico da skill oracle-sql que estende o analisador
para reconhecer Common Table Expressions (CTEs) recursivas ANSI com listas de
colunas (ex.: WITH NomeCte (col1, col2) AS (...)).

É o guard padrão dos validadores (`validar_sql_oracle.resolve_guard`). A cadeia é
validador -> este wrapper -> guard canônico (fora do repositório, na skill
oracle-sql). Importar o módulo não tem efeito colateral: o canônico só é
carregado em `main()`.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any

CANONICAL_MODULE_NAME = "guard_sql_canonico"


def _dotenv_value(name: str) -> str | None:
    """Lê `name` do `.env` da raiz quando o wrapper roda direto (sem validador pai)."""
    try:
        from dotenv import dotenv_values  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    value = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get(name)
    return value or None


def canonical_guard_file() -> Path:
    """Caminho do guard canônico da skill oracle-sql.

    `ORACLE_SQL_GUARD_CANONICAL` (no `.env`) tem precedência; sem ela, o local
    padrão de instalação da skill no perfil do usuário.
    """
    configured = os.environ.get("ORACLE_SQL_GUARD_CANONICAL") or _dotenv_value(
        "ORACLE_SQL_GUARD_CANONICAL"
    )
    if configured:
        return Path(configured)
    return (
        Path(os.environ.get("USERPROFILE", "~")).expanduser()
        / ".gemini"
        / "antigravity"
        / "skills"
        / "oracle-sql"
        / "scripts"
        / "guard_sql.py"
    )


def load_canonical() -> Any:
    """Carrega o guard canônico por caminho, sob nome próprio (evita colidir com
    este wrapper, que também se chama `guard_sql`)."""
    path = canonical_guard_file()
    spec = importlib.util.spec_from_file_location(CANONICAL_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"guard_sql canônico não carregável: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[CANONICAL_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


# CTEs recursivas ANSI no Oracle 11g+/12c exigem lista explícita de colunas:
# "nome_cte (col1, col2) AS (". O guard original considera qualquer
# "identificador(" como chamada de função do usuário. Esta normalização
# preserva a semântica da CTE sem disparar falso positivo de função.
_CTE_COLUMN_LIST = re.compile(
    r"([A-Za-z_][\w$#]*)\s*\([^)]*\)\s+AS\s*\(", flags=re.IGNORECASE
)


def normalize_cte_column_lists(sql: str) -> str:
    return _CTE_COLUMN_LIST.sub(r"\1 AS (", sql)


def patch_canonical(canonical: Any) -> Any:
    original = canonical.classificar

    def patched(sql: str, exigir_limite: bool = False) -> dict[str, Any]:
        resultado: dict[str, Any] = original(
            normalize_cte_column_lists(sql), exigir_limite
        )
        return resultado

    canonical.classificar = patched
    return canonical


def main() -> int:
    try:
        canonical = patch_canonical(load_canonical())
    except (ImportError, OSError) as exc:
        print(
            f"[ERRO] Não foi possível importar o guard_sql canônico em "
            f"{canonical_guard_file()}: {exc}"
        )
        return 1
    result: int = canonical.main()
    return result


if __name__ == "__main__":
    sys.exit(main())

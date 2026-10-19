"""guard_sql.py local do Hub de Automações.

Wrapper para o guard_sql canônico da skill oracle-sql que estende o analisador
para reconhecer Common Table Expressions (CTEs) recursivas ANSI com listas de
colunas (ex.: WITH NomeCte (col1, col2) AS (...)).

É o guard padrão dos validadores (`validar_sql_oracle.resolve_guard`). A cadeia é
validador -> este wrapper -> guard canônico (cópia versionada em
`lib/vendor/oracle-sql-guard/`, espelho da skill oracle-sql). Importar o módulo não
tem efeito colateral: o canônico só é carregado em `main()`.

Também é a fonte única de duas regras que todo executor de SQL do repositório
segue: o que conta como "só chamada de função" (`so_chamada_de_funcao`) e a
verificação no catálogo antes da primeira execução (`verificar_objetos`).
"""

from __future__ import annotations

import importlib.util
import json
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


COPIA_VERSIONADA = (
    Path(__file__).resolve().parents[2]
    / "lib"
    / "vendor"
    / "oracle-sql-guard"
    / "guard_sql.py"
)


def canonical_guard_file() -> Path:
    """Caminho do guard canônico da skill oracle-sql.

    Ordem: `ORACLE_SQL_GUARD_CANONICAL` (ambiente ou `.env`); a cópia versionada em
    `lib/vendor/oracle-sql-guard/`; e o local de instalação da skill no perfil do
    usuário. A cópia versionada vem antes do perfil: a trava de leitura precisa ser a
    mesma que o CI testa, e o perfil não é versionado. Sem nenhum dos três, devolve o
    caminho do perfil, e o validador falha fechado com o caminho na mensagem.
    """
    configured = os.environ.get("ORACLE_SQL_GUARD_CANONICAL") or _dotenv_value(
        "ORACLE_SQL_GUARD_CANONICAL"
    )
    if configured:
        return Path(configured)
    if COPIA_VERSIONADA.is_file():
        return COPIA_VERSIONADA
    return (
        Path(os.environ.get("USERPROFILE", "~")).expanduser()
        / ".gemini"
        / "antigravity"
        / "skills"
        / "oracle-sql"
        / "scripts"
        / "guard_sql.py"
    )


# Classe do veredito quando o único bloqueio é chamada de função/pacote/tipo. Fonte
# única da regra "só função": o texto dos motivos muda, a classe é o contrato.
CLASSE_CHAMADA_FUNCAO = "chamada_funcao"


def ler_veredito(saida: str) -> dict[str, Any]:
    """Veredito JSON impresso pelo guard. ValueError se não for um objeto JSON."""
    veredito = json.loads(saida)
    if not isinstance(veredito, dict):
        raise ValueError("saída do guard não é um objeto JSON")
    return veredito


def so_chamada_de_funcao(veredito: dict[str, Any]) -> bool:
    """True se o guard bloqueou só por chamada de função (classe `chamada_funcao`)."""
    return veredito.get("classe") == CLASSE_CHAMADA_FUNCAO


def motivo_objetos_executaveis(linhas: list[Any]) -> str | None:
    """Motivo do bloqueio a partir das linhas da `consulta_verificacao`; None se vazia."""
    if not linhas:
        return None
    nomes = ", ".join(f"{owner}.{nome} ({tipo})" for owner, nome, tipo in linhas)
    return f"a consulta referencia função/pacote/procedimento/tipo: {nomes}"


def verificar_objetos(cursor: Any, consulta: str | None) -> str | None:
    """Roda a `consulta_verificacao` do guard (só leitura) no cursor dado.

    O guard só vê o texto: `SELECT PKG.FN FROM DUAL` parece coluna e executa a função.
    Esta consulta ao catálogo tira a dúvida e precisa rodar antes da primeira execução
    do SQL. Devolve o motivo do bloqueio, ou None se nenhum nome é executável. Erro do
    banco propaga: quem chama não executa o SQL (fail-closed).
    """
    if consulta is None:
        return None
    cursor.execute(consulta)
    return motivo_objetos_executaveis(list(cursor.fetchall()))


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

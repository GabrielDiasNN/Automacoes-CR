"""CLI de consulta ao catalogo local do schema Oracle SGTPRD.

Le `docs/oracle-schema/schema.db` (gerado por `Tools/oracle/build_oracle_catalog.py`)
para responder "qual tabela / qual coluna / qual join" sem gastar tokens de
sessao e sem ir ao Oracle a cada pergunta.

Subcomandos offline (so leem o catalogo local):
    table <NOME>              Ficha completa da tabela/view
    cols <TABELA> [--like P]  Colunas que casam com um padrao
    find <TEXTO>              Busca textual (FTS) em objetos/colunas/comentarios
    path <DE> <PARA>          Menor caminho de FK entre duas tabelas
    neighbors <TABELA>        Vizinhanca de FK de uma tabela
    view <NOME>               Fonte SQL de uma view
    usage                     Cruza os .sql do repo com o catalogo (drift)

Subcomandos online (abrem 1 conexao Oracle — SELECT-only, LIMIT obrigatorio,
timeout, retry — nunca escrevem no banco):
    distinct <TABELA> <COLUNA>   Valores distintos de uma coluna de codigo
    sample <TABELA>              Amostra de ate 100 linhas
    check <ARQUIVO.sql>          Valida sintaxe/nomes sem executar
    explain <ARQUIVO.sql>        Plano de execucao sem executar

Uso:
    .venv\\Scripts\\python Tools\\oracle\\oracle_catalog.py table OB
    .venv\\Scripts\\python Tools\\oracle\\oracle_catalog.py find "receita bloqueada"
    .venv\\Scripts\\python Tools\\oracle\\oracle_catalog.py path OB ITENSPEDIDOGRADE
    .venv\\Scripts\\python Tools\\oracle\\oracle_catalog.py distinct CLASSIFICACAO_COR CODIGO --with-desc
    .venv\\Scripts\\python Tools\\oracle\\oracle_catalog.py check meu_arquivo.sql
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib" / "python"))

try:
    from dotenv import load_dotenv
    from oracle_extract import (
        OracleCredentials,
        init_thick_mode,
        resolve_oracle_credentials,
    )
    from oracle_session import is_session_drop, run_with_cancel
except ImportError as exc:
    print(f"[ERRO] Nao foi possivel importar dependencias: {exc}")
    print(
        "       Rode com o venv do projeto: .venv\\Scripts\\python Tools\\oracle\\oracle_catalog.py"
    )
    sys.exit(1)

CATALOG_PATH = ROOT / "docs" / "oracle-schema" / "schema.db"
MAX_SAMPLE_ROWS = 100
DEFAULT_SAMPLE_ROWS = 20
DEFAULT_DISTINCT_ROWS = 50
DEFAULT_TIMEOUT_SECONDS = 20
EXEC_ID = "oracle-catalog-cli"

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|CALL)\b",
    re.IGNORECASE,
)
_DESC_COLUMN_HINTS = ("DESCRICAO", "DESCRIC", "NOME", "DESC")


class GuardError(ValueError):
    """SQL rejeitado pelos guardrails (nao e SELECT/WITH, tem DML/DDL, etc.)."""


def _connect_catalog() -> sqlite3.Connection:
    if not CATALOG_PATH.exists():
        print(f"[ERRO] Catalogo nao encontrado em {CATALOG_PATH}.")
        print(
            "       Rode antes: .venv\\Scripts\\python Tools\\oracle\\build_oracle_catalog.py"
        )
        sys.exit(1)
    conn = sqlite3.connect(f"file:{CATALOG_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _catalog_owner(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'owner'").fetchone()
    return str(row["value"]) if row else "SGTPRD"


# ─────────────────────────── table ────────────────────────────────────────────


def _print_table_columns(conn: sqlite3.Connection, table: str) -> None:
    rows = conn.execute(
        "SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, "
        "is_virtual, comment FROM columns WHERE table_name = ? ORDER BY position",
        (table,),
    ).fetchall()
    print(f"\nColunas ({len(rows)}):")
    for row in rows:
        tipo = row["data_type"]
        if row["data_precision"] is not None:
            tipo += f"({row['data_precision']},{row['data_scale'] or 0})"
        elif row["data_length"] is not None and tipo in (
            "VARCHAR2",
            "CHAR",
            "NVARCHAR2",
        ):
            tipo += f"({row['data_length']})"
        flags = []
        if not row["nullable"]:
            flags.append("NOT NULL")
        if row["is_virtual"]:
            flags.append("VIRTUAL")
        flag_txt = f" [{', '.join(flags)}]" if flags else ""
        comment_txt = f" -- {row['comment']}" if row["comment"] else ""
        print(f"  {row['column_name']:<32} {tipo:<20}{flag_txt}{comment_txt}")


def _print_table_constraints(conn: sqlite3.Connection, table: str) -> None:
    cons = conn.execute(
        "SELECT constraint_name, constraint_type, ref_table FROM constraints WHERE table_name = ?",
        (table,),
    ).fetchall()
    for kind, label in (("P", "Chave primaria"), ("U", "Unique")):
        names = [c["constraint_name"] for c in cons if c["constraint_type"] == kind]
        for name in names:
            cols = conn.execute(
                "SELECT column_name FROM constraint_columns WHERE constraint_name = ? ORDER BY position",
                (name,),
            ).fetchall()
            col_list = ", ".join(c["column_name"] for c in cols)
            print(f"\n{label}: {name} ({col_list})")

    fks_out = [c for c in cons if c["constraint_type"] == "R"]
    if fks_out:
        print(f"\nFKs de saida ({len(fks_out)}):")
        for fk in fks_out:
            cols = conn.execute(
                "SELECT column_name FROM constraint_columns WHERE constraint_name = ? ORDER BY position",
                (fk["constraint_name"],),
            ).fetchall()
            col_list = ", ".join(c["column_name"] for c in cols)
            print(
                f"  {table}.({col_list}) -> {fk['ref_table']}  [{fk['constraint_name']}]"
            )

    fks_in = conn.execute(
        "SELECT table_name, constraint_name FROM constraints WHERE ref_table = ? AND constraint_type = 'R'",
        (table,),
    ).fetchall()
    if fks_in:
        print(f"\nReferenciada por ({len(fks_in)}):")
        for fk in fks_in:
            print(f"  {fk['table_name']}  [{fk['constraint_name']}]")


def cmd_table(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    name = args.name.upper()
    obj = conn.execute(
        "SELECT * FROM objects WHERE object_name = ?", (name,)
    ).fetchone()
    if obj is None:
        print(f"[ERRO] Objeto '{name}' nao encontrado no catalogo.")
        return 1

    print(f"{obj['object_name']} ({obj['object_type']}, {obj['status']})")
    if obj["comment"]:
        print(f"  {obj['comment']}")
    if obj["num_rows"] is not None:
        print(
            f"  Linhas (estimativa do dicionario): {obj['num_rows']:,}".replace(
                ",", "."
            )
        )

    _print_table_columns(conn, name)
    _print_table_constraints(conn, name)

    idx = conn.execute(
        "SELECT index_name, uniqueness FROM indexes WHERE table_name = ?", (name,)
    ).fetchall()
    if idx:
        print(f"\nIndices ({len(idx)}):")
        for i in idx:
            cols = conn.execute(
                "SELECT column_name FROM index_columns WHERE index_name = ? ORDER BY position",
                (i["index_name"],),
            ).fetchall()
            col_list = ", ".join(c["column_name"] for c in cols)
            unique_txt = "UNIQUE " if i["uniqueness"] == "UNIQUE" else ""
            print(f"  {unique_txt}{i['index_name']} ({col_list})")

    return 0


# ─────────────────────────── cols ─────────────────────────────────────────────


def cmd_cols(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    table = args.table.upper()
    pattern = f"%{args.like.upper()}%" if args.like else "%"
    rows = conn.execute(
        "SELECT column_name, data_type, nullable, comment FROM columns "
        "WHERE table_name = ? AND column_name LIKE ? ORDER BY position",
        (table, pattern),
    ).fetchall()
    if not rows:
        print(
            f"[AVISO] Nenhuma coluna encontrada em {table} para o padrao '{args.like}'."
        )
        return 1
    for row in rows:
        nn = "" if row["nullable"] else " NOT NULL"
        comment_txt = f" -- {row['comment']}" if row["comment"] else ""
        print(f"{row['column_name']:<32} {row['data_type']:<15}{nn}{comment_txt}")
    return 0


# ─────────────────────────── find ─────────────────────────────────────────────


def _sanitize_fts_query(text: str) -> str:
    # FTS5 trata alguns caracteres (- * : ^) como operadores; mantemos so
    # letras/numeros/acentos/espaco para evitar erro de sintaxe da query.
    cleaned = re.sub(r"[^\w\sáéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]", " ", text, flags=re.UNICODE)
    # Cada termo vai entre aspas: sem isso, um token como AND/OR/NOT/NEAR e
    # interpretado como operador do FTS5 (nao como palavra de busca) e quebra
    # a query com sqlite3.OperationalError.
    tokens = cleaned.split()
    return " ".join(f'"{t}"' for t in tokens)


def cmd_find(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    query = _sanitize_fts_query(args.text)
    if not query:
        print("[ERRO] Termo de busca vazio apos sanitizacao.")
        return 1
    rows = conn.execute(
        "SELECT object_name, column_name, comment FROM search_idx WHERE search_idx MATCH ? LIMIT ?",
        (query, args.limit),
    ).fetchall()
    if not rows:
        print(f"[AVISO] Nada encontrado para '{args.text}'.")
        return 1
    for row in rows:
        alvo = (
            row["object_name"]
            if not row["column_name"]
            else f"{row['object_name']}.{row['column_name']}"
        )
        comment_txt = f" -- {row['comment']}" if row["comment"] else ""
        print(f"{alvo:<48}{comment_txt}")
    return 0


# ─────────────────────────── path / neighbors (grafo de FK) ──────────────────


def _load_fk_edges(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Retorna (tabela_origem, tabela_destino, constraint_name) para toda FK valida."""
    rows = conn.execute(
        "SELECT table_name, ref_table, constraint_name FROM constraints "
        "WHERE constraint_type = 'R' AND ref_table IS NOT NULL"
    ).fetchall()
    return [(r["table_name"], r["ref_table"], r["constraint_name"]) for r in rows]


def _build_adjacency(
    edges: list[tuple[str, str, str]],
) -> dict[str, list[tuple[str, str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for src, dst, cons_name in edges:
        adjacency.setdefault(src, []).append((dst, cons_name))
        adjacency.setdefault(dst, []).append((src, cons_name))
    return adjacency


def _bfs_path(
    adjacency: dict[str, list[tuple[str, str]]], start: str, end: str, max_depth: int
) -> list[tuple[str, str, str]] | None:
    """BFS: retorna a lista de (de, para, constraint_name) do caminho, ou None."""
    if start == end:
        return []
    visited = {start}
    queue: deque[tuple[str, list[tuple[str, str, str]]]] = deque([(start, [])])
    while queue:
        node, trail = queue.popleft()
        if len(trail) >= max_depth:
            continue
        for neighbor, cons_name in adjacency.get(node, []):
            if neighbor in visited:
                continue
            new_trail = trail + [(node, neighbor, cons_name)]
            if neighbor == end:
                return new_trail
            visited.add(neighbor)
            queue.append((neighbor, new_trail))
    return None


def cmd_path(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    start, end = args.de.upper(), args.para.upper()
    adjacency = _build_adjacency(_load_fk_edges(conn))
    trail = _bfs_path(adjacency, start, end, args.max_depth)
    if trail is None:
        print(
            f"[AVISO] Nenhum caminho de FK entre {start} e {end} em ate {args.max_depth} saltos."
        )
        return 1
    if not trail:
        print(f"{start} == {end}")
        return 0
    print(f"Caminho ({len(trail)} salto(s)):")
    for src, dst, cons_name in trail:
        cols = conn.execute(
            "SELECT column_name FROM constraint_columns WHERE constraint_name = ? ORDER BY position",
            (cons_name,),
        ).fetchall()
        col_list = ", ".join(c["column_name"] for c in cols)
        print(f"  JOIN {dst} ON ({col_list}) -- via {cons_name} (a partir de {src})")
    return 0


def cmd_neighbors(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    table = args.table.upper()
    adjacency = _build_adjacency(_load_fk_edges(conn))
    visited = {table: 0}
    queue: deque[tuple[str, int]] = deque([(table, 0)])
    result: list[tuple[str, int, str]] = []
    while queue:
        node, depth = queue.popleft()
        if depth >= args.depth:
            continue
        for neighbor, cons_name in adjacency.get(node, []):
            if neighbor in visited:
                continue
            visited[neighbor] = depth + 1
            result.append((neighbor, depth + 1, cons_name))
            queue.append((neighbor, depth + 1))
    if not result:
        print(f"[AVISO] {table} nao tem FKs no catalogo (ou nao existe).")
        return 1
    for neighbor, depth, cons_name in sorted(result, key=lambda r: (r[1], r[0])):
        print(
            f"  {'  ' * (depth - 1)}{neighbor}  (profundidade {depth}, via {cons_name})"
        )
    return 0


# ─────────────────────────── view ─────────────────────────────────────────────


def cmd_view(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    name = args.name.upper()
    row = conn.execute(
        "SELECT text FROM view_source WHERE view_name = ?", (name,)
    ).fetchone()
    if row is None:
        exists = conn.execute(
            "SELECT 1 FROM objects WHERE object_name = ? AND object_type = 'VIEW'",
            (name,),
        ).fetchone()
        if exists:
            print(
                f"[AVISO] '{name}' e uma view, mas o catalogo foi gerado com --skip-view-source."
            )
        else:
            print(f"[ERRO] View '{name}' nao encontrada no catalogo.")
        return 1
    print(row["text"])
    return 0


# ─────────────────────────── usage (drift entre .sql do repo e o catalogo) ───

_SCHEMA_PREFIX_RE = re.compile(r"\bSGTPRD\.([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE)


def cmd_usage(_args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    known = {r["object_name"] for r in conn.execute("SELECT object_name FROM objects")}
    sql_files = sorted(ROOT.glob("**/*.sql"))
    sql_files = [
        f for f in sql_files if ".venv" not in f.parts and "node_modules" not in f.parts
    ]

    any_drift = False
    for path in sql_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        refs = {m.upper() for m in _SCHEMA_PREFIX_RE.findall(text)}
        if not refs:
            continue
        missing = sorted(refs - known)
        rel = path.relative_to(ROOT)
        print(f"{rel}: {len(refs)} objeto(s) referenciado(s)")
        if missing:
            any_drift = True
            print(f"  [DRIFT] nao encontrados no catalogo: {', '.join(missing)}")

    if any_drift:
        print(
            "\n[AVISO] Ha drift entre .sql do repo e o catalogo (objeto renomeado/removido, ou catalogo desatualizado)."
        )
        return 1
    print("\nSem drift detectado.")
    return 0


# ─────────────────────────── guardrails para comandos online ────────────────


def _skip_comment(sql: str, i: int) -> tuple[int, str]:
    """Consome o comentario que comeca em `i`; devolve (proximo indice, texto a
    manter no SQL executavel). Hints `/*+ ... */` sao mantidos: remove-los muda
    o plano e o `check` passaria a medir outra consulta."""
    if sql.startswith("--", i):
        end = sql.find("\n", i)
        return (len(sql) if end == -1 else end), " "
    end = sql.find("*/", i + 2)
    if end == -1:
        raise GuardError("Comentario /* sem fechamento.")
    kept = sql[i : end + 2] if sql.startswith("/*+", i) else " "
    return end + 2, kept


def _skip_quoted(sql: str, i: int) -> int:
    """Consome o literal ('...', com '' como escape) ou identificador ("...")
    que comeca em `i` e devolve o indice logo apos o fechamento."""
    quote = sql[i]
    j = i + 1
    while True:
        j = sql.find(quote, j)
        if j == -1:
            raise GuardError("Literal ou identificador entre aspas sem fechamento.")
        if quote == "'" and sql.startswith("''", j):
            j += 2
            continue
        return j + 1


_Q_CLOSERS = {"[": "]", "{": "}", "(": ")", "<": ">"}


def _q_quote_end(sql: str, i: int) -> int | None:
    """Se em `i` comeca um literal alternativo (`q'[..]'`, `Q'X..X'`, `nq'..'`),
    devolve o indice logo apos o fechamento; `None` se nao for q-quote.

    Literal q-quote sem fechamento levanta `GuardError`: tratar como fim do
    texto esconderia o resto do SQL (inclusive um `;` ou DML) da guarda.
    """
    if i > 0 and (sql[i - 1].isalnum() or sql[i - 1] in "_$#\"'"):
        return None
    start = i
    if sql[start] in "nN" and start + 1 < len(sql) and sql[start + 1] in "qQ":
        start += 1
    if sql[start] not in "qQ" or not sql.startswith("'", start + 1):
        return None
    delim_pos = start + 2
    if delim_pos >= len(sql):
        raise GuardError("Literal q'...' sem fechamento.")
    delim = sql[delim_pos]
    if delim.isspace():
        return None
    closer = _Q_CLOSERS.get(delim, delim) + "'"
    end = sql.find(closer, delim_pos + 1)
    if end == -1:
        raise GuardError("Literal q'...' sem fechamento.")
    return end + len(closer)


def _split_sql(sql: str) -> tuple[str, str]:
    """Devolve (executavel, guarda).

    - executavel: comentarios removidos, hints e literais preservados;
    - guarda: comentarios/hints removidos e literais trocados por '' — assim
      `';'` e palavras-chave dentro de literais nao disparam falso bloqueio,
      e DML escondido em comentario nao escapa da checagem.
    """
    executable: list[str] = []
    guard: list[str] = []
    i = 0
    while i < len(sql):
        q_end = _q_quote_end(sql, i) if sql[i] in "qQnN" else None
        if q_end is not None:
            executable.append(sql[i:q_end])
            guard.append("''")
            i = q_end
        elif sql.startswith(("--", "/*"), i):
            i, kept = _skip_comment(sql, i)
            executable.append(kept)
            guard.append(" ")
        elif sql[i] in "'\"":
            end = _skip_quoted(sql, i)
            executable.append(sql[i:end])
            guard.append("''" if sql[i] == "'" else sql[i:end])
            i = end
        else:
            executable.append(sql[i])
            guard.append(sql[i])
            i += 1
    return "".join(executable), "".join(guard)


def strip_sql_comments(sql: str) -> str:
    """Remove comentarios respeitando literais/identificadores; preserva hints.

    Reutilizado por `validar_sql_oracle.py`. Levanta `GuardError` em comentario
    ou literal sem fechamento.
    """
    return _split_sql(sql)[0]


def sql_guard_text(sql: str) -> str:
    """Texto de guarda: sem comentarios/hints e com literais trocados por ''.

    Util para achar `;` e `:bind` fora de literais. Levanta `GuardError` em
    comentario ou literal sem fechamento.
    """
    return _split_sql(sql)[1]


def _ensure_select_only(sql: str) -> str:
    """Valida `sql` e retorna a versao pronta para execucao (sem ';' final).

    A validacao roda sobre o texto de guarda de `_split_sql` (sem comentarios
    nem conteudo de literais). O texto retornado preserva hints e literais e
    descarta apenas comentarios — inclusive os que vem depois do `;` final,
    que o driver rejeitaria.
    """
    executable, guard = _split_sql(sql)
    stripped = guard.strip().rstrip(";").strip()
    if not stripped:
        raise GuardError("SQL vazio.")
    if ";" in stripped:
        raise GuardError(
            "Multiplos statements nao sao permitidos (';' no meio do SQL)."
        )
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        raise GuardError("Somente SELECT/WITH sao permitidos neste comando.")
    # `TRUNCATE` também é uma cláusula de leitura do LISTAGG
    # (`ON OVERFLOW TRUNCATE`), não uma instrução DDL nesse contexto.
    # Removemos apenas essa ocorrência estrutural antes de procurar DDL/DML,
    # mantendo o bloqueio para `TRUNCATE TABLE` e demais usos mutáveis.
    guard_text = re.sub(
        r"\bON\s+OVERFLOW\s+TRUNCATE\b", "ON OVERFLOW", stripped, flags=re.IGNORECASE
    )
    forbidden = _FORBIDDEN_KEYWORDS.search(guard_text)
    if forbidden:
        raise GuardError(f"Palavra-chave nao permitida: {forbidden.group(0).upper()}.")
    return executable.strip().rstrip(";").rstrip()


def _resolve_online_creds() -> OracleCredentials:
    load_dotenv(ROOT / ".env")
    creds = resolve_oracle_credentials(lambda *a, **k: None, EXEC_ID)
    if creds is None:
        print("[ERRO] Credenciais Oracle ausentes ou invalidas. Verifique .env.")
        sys.exit(1)
    init_thick_mode(creds, lambda *a, **k: None, EXEC_ID)
    return creds


def _run_with_timeout(
    fn: Any, timeout_seconds: int, holder: dict[str, Any] | None = None
) -> Any:
    """Executa `fn()` com um watchdog: cancela a conexao se estourar o prazo.

    O Oracle Client desta maquina (12.2) nao suporta `connection.call_timeout`
    (exige 18.1+), entao o timeout e emulado por thread + `connection.cancel()`.
    `fn` deve gravar a conexao aberta em `holder["connection"]` assim que
    conectar, para que o watchdog tenha o que cancelar.
    """
    expired = threading.Event()
    if holder is not None:
        holder["expired"] = expired
    outcome = run_with_cancel(
        fn,
        lambda: (holder or {}).get("connection"),
        timeout_seconds,
        owns_connection=True,
        abandoned_event=expired,
    )
    if outcome.timed_out:
        raise TimeoutError(f"Consulta excedeu {timeout_seconds}s e foi cancelada.")
    if outcome.error is not None:
        raise outcome.error
    return outcome.value


def _raise_if_expired(holder: dict[str, Any]) -> None:
    """Conexao que chegou depois do prazo nao executa: ninguem mais a vigia."""
    expired = holder.get("expired")
    if expired is not None and expired.is_set():
        raise TimeoutError("Conexao chegou depois do prazo; consulta nao executada.")


# Mesmo padrao dos 6 extratores de dominio e de `build_oracle_catalog.py`: a rede
# ate o Oracle desta maquina derruba conexoes continuas (ORA-00028/ORA-03113) com
# frequencia suficiente para exigir retry em toda chamada online.
# Retry so em queda de sessao (`is_session_drop`, fonte unica): erro de SQL
# falha na hora, e DPY-1001 (InterfaceError) tambem e repetido.
_MAX_ATTEMPTS = 3


def _run_guarded(fn: Any, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> Any:
    """Roda `fn(holder)` sob timeout/retry. `fn` grava a conexao em
    `holder["connection"]` assim que conectar, para o watchdog cancelar."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        holder: dict[str, Any] = {}
        try:
            return _run_with_timeout(
                lambda h=holder: fn(h), timeout_seconds, holder=holder
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if attempt >= _MAX_ATTEMPTS or not is_session_drop(exc):
                raise
    raise AssertionError("inalcancavel")


# ─────────────────────────── distinct [online] ────────────────────────────────


def _find_description_column(
    conn: sqlite3.Connection, table: str, skip: str
) -> str | None:
    for hint in _DESC_COLUMN_HINTS:
        row = conn.execute(
            "SELECT column_name FROM columns WHERE table_name = ? AND column_name != ? "
            "AND column_name LIKE ? ORDER BY position LIMIT 1",
            (table, skip, f"%{hint}%"),
        ).fetchone()
        if row:
            return str(row["column_name"])
    return None


def cmd_distinct(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    table, column = args.table.upper(), args.column.upper()
    col_exists = conn.execute(
        "SELECT 1 FROM columns WHERE table_name = ? AND column_name = ?",
        (table, column),
    ).fetchone()
    if not col_exists:
        print(
            f"[ERRO] {table}.{column} nao existe no catalogo. Rode 'cols {table}' para conferir."
        )
        return 1

    owner = _catalog_owner(conn)
    desc_col = _find_description_column(conn, table, column) if args.with_desc else None
    select_cols = f"{column}, {desc_col}" if desc_col else column
    limit = min(args.limit, DEFAULT_DISTINCT_ROWS * 4)
    sql = (
        f"SELECT DISTINCT {select_cols} FROM {owner}.{table} "  # nosec B608 - identificadores validados contra o catalogo, nunca texto livre do usuario
        f"WHERE {column} IS NOT NULL ORDER BY 1 FETCH FIRST {limit} ROWS ONLY"
    )

    creds = _resolve_online_creds()

    def _run(holder: dict[str, Any]) -> list[tuple[Any, ...]]:
        import oracledb  # pylint: disable=import-outside-toplevel

        # Fechada por `run_with_cancel` (owns_connection), nunca aqui.
        connection = oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        )
        holder["connection"] = connection
        _raise_if_expired(holder)
        cursor = connection.cursor()
        cursor.execute(sql)
        return list(cursor.fetchall())

    try:
        rows = _run_guarded(_run)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[ERRO] {exc}")
        return 1
    for row in rows:
        print(" | ".join(str(v) for v in row))
    return 0


# ─────────────────────────── sample [online] ──────────────────────────────────


def _resolve_sample_select_cols(
    conn: sqlite3.Connection, table: str, columns_arg: str | None
) -> str | None:
    """Retorna a clausula SELECT validada, ou None se alguma coluna pedida nao existir."""
    known_cols = {
        r["column_name"]
        for r in conn.execute(
            "SELECT column_name FROM columns WHERE table_name = ?", (table,)
        )
    }
    if not known_cols:
        return None
    if not columns_arg:
        return "*"
    requested = [c.strip().upper() for c in columns_arg.split(",")]
    invalid = [c for c in requested if c not in known_cols]
    if invalid:
        print(f"[ERRO] Colunas inexistentes em {table}: {', '.join(invalid)}")
        return None
    return ", ".join(requested)


def _resolve_sample_where_clause(where_arg: str | None) -> tuple[str | None, bool]:
    """Retorna (clausula ' WHERE ...' ou '', ok). ok=False se o guardrail rejeitou."""
    if not where_arg:
        return "", True
    if "--" in where_arg or "/*" in where_arg or "*/" in where_arg:
        # where_arg e concatenado antes do FETCH FIRST no SQL real (nao so na
        # sonda de validacao abaixo); um comentario aqui comentaria o FETCH
        # FIRST junto e anularia o limite obrigatorio de linhas.
        print(
            "[ERRO] --where rejeitado: comentarios SQL ('--', '/*', '*/') nao sao permitidos."
        )
        return None, False
    probe_sql = f"SELECT 1 FROM DUAL WHERE {where_arg}"  # nosec B608 - usado so para validacao, nunca executado
    try:
        _ensure_select_only(probe_sql)
    except GuardError as exc:
        print(f"[ERRO] --where rejeitado pelo guardrail: {exc}")
        return None, False
    return f" WHERE {where_arg}", True


def cmd_sample(args: argparse.Namespace) -> int:
    conn = _connect_catalog()
    table = args.table.upper()
    select_cols = _resolve_sample_select_cols(conn, table, args.columns)
    if select_cols is None:
        print(f"[ERRO] Tabela '{table}' nao existe no catalogo (ou colunas invalidas).")
        return 1
    where_clause, ok = _resolve_sample_where_clause(args.where)
    if not ok:
        return 1

    owner = _catalog_owner(conn)
    max_rows = min(args.max_rows, MAX_SAMPLE_ROWS)
    sql = (
        f"SELECT {select_cols} FROM {owner}.{table}{where_clause} "  # nosec B608 - tabela/colunas validadas contra o catalogo; --where documentado como guardrail parcial
        f"FETCH FIRST {max_rows} ROWS ONLY"
    )

    creds = _resolve_online_creds()

    def _run(holder: dict[str, Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
        import oracledb  # pylint: disable=import-outside-toplevel

        # Fechada por `run_with_cancel` (owns_connection), nunca aqui.
        connection = oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        )
        holder["connection"] = connection
        _raise_if_expired(holder)
        cursor = connection.cursor()
        cursor.execute(sql)
        cols = [d[0] for d in (cursor.description or [])]
        return cols, list(cursor.fetchall())

    try:
        cols, rows = _run_guarded(_run)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[ERRO] {exc}")
        return 1
    print(" | ".join(cols))
    for row in rows:
        print(" | ".join(str(v) for v in row))
    return 0


# ─────────────────────────── check / explain [online] ────────────────────────


def _read_sql_file(path_str: str) -> str | None:
    path = Path(path_str)
    if not path.exists():
        print(f"[ERRO] Arquivo nao encontrado: {path}")
        return None
    return path.read_text(encoding="utf-8")


def cmd_check(args: argparse.Namespace) -> int:
    raw_sql = _read_sql_file(args.arquivo)
    if raw_sql is None:
        return 1
    try:
        sql = _ensure_select_only(raw_sql)
    except GuardError as exc:
        print(f"[ERRO] {exc}")
        return 1

    creds = _resolve_online_creds()

    def _run(holder: dict[str, Any]) -> None:
        import oracledb  # pylint: disable=import-outside-toplevel

        # Fechada por `run_with_cancel` (owns_connection), nunca aqui.
        connection = oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        )
        holder["connection"] = connection
        _raise_if_expired(holder)
        connection.cursor().parse(sql)

    try:
        _run_guarded(_run)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[INVALIDO] {exc}")
        return 1
    print("[OK] SQL parseado com sucesso (nomes e sintaxe validos).")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    raw_sql = _read_sql_file(args.arquivo)
    if raw_sql is None:
        return 1
    try:
        sql = _ensure_select_only(raw_sql)
    except GuardError as exc:
        print(f"[ERRO] {exc}")
        return 1

    creds = _resolve_online_creds()

    def _run(holder: dict[str, Any]) -> list[str]:
        import oracledb  # pylint: disable=import-outside-toplevel

        # Fechada por `run_with_cancel` (owns_connection), nunca aqui.
        connection = oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        )
        holder["connection"] = connection
        _raise_if_expired(holder)
        cursor = connection.cursor()
        cursor.execute(f"EXPLAIN PLAN FOR {sql}")
        cursor.execute("SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())")
        return [row[0] for row in cursor.fetchall()]

    try:
        linhas = _run_guarded(_run)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[ERRO] Nao foi possivel gerar o plano: {exc}")
        return 1
    for linha in linhas:
        print(linha)
    return 0


# ────────────────────────────── Main ──────────────────────────────────────────


def _add_offline_subparsers(sub: Any) -> None:
    p_table = sub.add_parser("table", help="Ficha completa de uma tabela/view")
    p_table.add_argument("name")
    p_table.set_defaults(func=cmd_table)

    p_cols = sub.add_parser("cols", help="Colunas que casam com um padrao")
    p_cols.add_argument("table")
    p_cols.add_argument("--like", default=None)
    p_cols.set_defaults(func=cmd_cols)

    p_find = sub.add_parser("find", help="Busca textual em objetos/colunas/comentarios")
    p_find.add_argument("text")
    p_find.add_argument("--limit", type=int, default=20)
    p_find.set_defaults(func=cmd_find)

    p_path = sub.add_parser("path", help="Menor caminho de FK entre duas tabelas")
    p_path.add_argument("de")
    p_path.add_argument("para")
    p_path.add_argument("--max-depth", type=int, default=6)
    p_path.set_defaults(func=cmd_path)

    p_neighbors = sub.add_parser("neighbors", help="Vizinhanca de FK de uma tabela")
    p_neighbors.add_argument("table")
    p_neighbors.add_argument("--depth", type=int, default=1)
    p_neighbors.set_defaults(func=cmd_neighbors)

    p_view = sub.add_parser("view", help="Fonte SQL de uma view")
    p_view.add_argument("name")
    p_view.set_defaults(func=cmd_view)

    p_usage = sub.add_parser(
        "usage", help="Cruza os .sql do repo com o catalogo (drift)"
    )
    p_usage.set_defaults(func=cmd_usage)


def _add_online_subparsers(sub: Any) -> None:
    p_distinct = sub.add_parser(
        "distinct", help="[online] Valores distintos de uma coluna"
    )
    p_distinct.add_argument("table")
    p_distinct.add_argument("column")
    p_distinct.add_argument("--with-desc", action="store_true")
    p_distinct.add_argument("--limit", type=int, default=DEFAULT_DISTINCT_ROWS)
    p_distinct.set_defaults(func=cmd_distinct)

    p_sample = sub.add_parser("sample", help="[online] Amostra de ate 100 linhas")
    p_sample.add_argument("table")
    p_sample.add_argument("--where", default=None)
    p_sample.add_argument("--columns", default=None, help="Lista separada por virgula")
    p_sample.add_argument("--max-rows", type=int, default=DEFAULT_SAMPLE_ROWS)
    p_sample.set_defaults(func=cmd_sample)

    p_check = sub.add_parser("check", help="[online] Valida sintaxe/nomes sem executar")
    p_check.add_argument("arquivo")
    p_check.set_defaults(func=cmd_check)

    p_explain = sub.add_parser(
        "explain", help="[online] Plano de execucao sem executar"
    )
    p_explain.add_argument("arquivo")
    p_explain.set_defaults(func=cmd_explain)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta o catalogo local do schema Oracle SGTPRD"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_offline_subparsers(sub)
    _add_online_subparsers(sub)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

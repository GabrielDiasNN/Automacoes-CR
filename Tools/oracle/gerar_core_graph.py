"""Gera `docs/oracle-schema/core-graph.json`: subgrafo dos objetos SGTPRD citados
pelos `.sql` versionáveis do repositório, lido do catálogo local `schema.db`.

- referências: `SGTPRD.<nome>` (sem diferenciar maiúsculas, mesma regra do
  `Tools/oracle/oracle_catalog.py usage`) em cada `.sql` do índice do git (`git ls-files -c`,
  inclui arquivos staged) — `.loop-state/`, `SQL Reference/` e backups ficam de
  fora. `SGTPRD.<a>.<b>` (função de pacote, ex.: `SGTPRD.PKG.FUNC`) não conta como
  objeto: só referências simples;
- reprodutibilidade: por padrão a saída depende só do índice, logo é igual no CI
  e no checkout de outra pessoa. `--include-untracked` usa `git ls-files -co`
  (índice + não rastreados não ignorados) e serve para regenerar localmente o
  grafo do working tree que ainda vai ser commitado (antes do `git add`);
  `--check` sem a flag é o modo canônico local (exige o `schema.db`
  gitignored; o JSON embute a data de extração do catálogo, então só compara
  com o mesmo catálogo — não roda no CI);
- nós: tipo, linhas, comentário e colunas `nome:tipo` de cada objeto citado;
- arestas: FKs entre objetos citados (não expande vizinhança, ver `note`).

Nomes citados que não existem no `schema.db` saem em `unknown_references`
(drift entre o SQL do repo e o catálogo, ou catálogo desatualizado).

Uso:
    .venv/Scripts/python Tools/oracle/gerar_core_graph.py           # grava o JSON
    .venv/Scripts/python Tools/oracle/gerar_core_graph.py --check   # falha se desatualizado
    .venv/Scripts/python Tools/oracle/gerar_core_graph.py --include-untracked  # working tree ainda não adicionado ao índice
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DB = ROOT / "docs" / "oracle-schema" / "schema.db"
OUTPUT = ROOT / "docs" / "oracle-schema" / "core-graph.json"
# `(?!\.[A-Za-z_])`: `SGTPRD.PKG.FUNC` é função de pacote, não o objeto `PKG`.
SCHEMA_PREFIX_RE = re.compile(
    r"\bSGTPRD\.([A-Za-z_][A-Za-z0-9_]*)\b(?!\.[A-Za-z_])", re.IGNORECASE
)
VERSION = "2.1.0"
NOTE = (
    "Subgrafo dos objetos referenciados via SGTPRD.<nome> pelos .sql do repo -- TOPOLOGIA apenas "
    "(colunas so por 'nome:tipo', sem nullable/comentario/tamanho). Para ficha completa de uma "
    "tabela, rode 'Tools/oracle/oracle_catalog.py table <NOME>' contra o catalogo completo (schema.db, "
    "gitignored, gerado por Tools/oracle/build_oracle_catalog.py). Nao expande vizinhanca de FK alem dos "
    "objetos core: um salto a partir de tabelas centrais (ex.: OB) alcanca centenas de objetos no "
    "schema real (3.6 mil tabelas) e inviabilizaria um grafo pequeno o bastante para ler inteiro. "
    "Para isso, use 'Tools/oracle/oracle_catalog.py neighbors <TABELA>' ou 'path <DE> <PARA>'. "
    "Regenerar: Tools/oracle/gerar_core_graph.py."
)


def repo_sql_files(include_untracked: bool = False) -> list[str]:
    """`.sql` do índice do git (`-c`), em caminho relativo com `/`.

    Com `include_untracked`, usa `-co --exclude-standard` (também os não
    rastreados e não ignorados).
    """
    flags = ["-co", "--exclude-standard"] if include_untracked else ["-c"]
    out = subprocess.run(
        ["git", "ls-files", *flags, "-z", "--", "*.sql"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p and (ROOT / p).is_file())


def references(files: list[str]) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        found = {m.upper() for m in SCHEMA_PREFIX_RE.findall(text)}
        if found:
            refs[rel] = found
    return refs


def _node(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT object_type, num_rows, comment FROM objects WHERE object_name = ?",
        (name,),
    ).fetchone()
    node: dict[str, Any] = {"id": name, "type": row[0]}
    if row[1] is not None:
        node["num_rows"] = row[1]
    if row[2]:
        node["description"] = row[2]
    node["columns"] = [
        f"{col}:{dtype}"
        for col, dtype in conn.execute(
            "SELECT column_name, data_type FROM columns WHERE table_name = ? ORDER BY position",
            (name,),
        )
    ]
    return node


def _edges(conn: sqlite3.Connection, core: set[str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT c.table_name, r.table_name, c.constraint_name FROM constraints c "
        "JOIN constraints r ON r.constraint_name = c.ref_constraint_name "
        "WHERE c.constraint_type = 'R' ORDER BY c.table_name, c.constraint_name"
    )
    for src, dst, fk in rows:
        if src in core and dst in core:
            cols = [
                c
                for (c,) in conn.execute(
                    "SELECT column_name FROM constraint_columns WHERE constraint_name = ? "
                    "AND table_name = ? ORDER BY position",
                    (fk, src),
                )
            ]
            edges.append({"from": src, "to": dst, "fk_name": fk, "columns": cols})
    return edges


def _totals(conn: sqlite3.Connection) -> dict[str, int]:
    def count(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    return {
        "total_objects": count("SELECT COUNT(*) FROM objects"),
        "total_tables": count(
            "SELECT COUNT(*) FROM objects WHERE object_type = 'TABLE'"
        ),
        "total_columns": count("SELECT COUNT(*) FROM columns"),
        "total_constraints": count("SELECT COUNT(*) FROM constraints"),
        "total_indexes": count("SELECT COUNT(*) FROM indexes"),
    }


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def build(conn: sqlite3.Connection, refs: dict[str, set[str]]) -> dict[str, Any]:
    known = {name for (name,) in conn.execute("SELECT object_name FROM objects")}
    core = set().union(*refs.values()) & known if refs else set()
    unknown = {
        rel: sorted(names - known) for rel, names in refs.items() if names - known
    }
    edges = _edges(conn, core)
    return {
        "schema": "SGTPRD",
        "generated_from": "docs/oracle-schema/schema.db (Tools/oracle/build_oracle_catalog.py) + .sql versionaveis do repo",
        "catalog_extracted_at": _meta(conn, "extracted_at"),
        "version": VERSION,
        "note": NOTE,
        "real_schema_totals": _totals(conn),
        "stats": {
            "sql_files_with_refs": len(refs),
            "core_objects": len(core),
            "fk_edges_among_core_objects": len(edges),
            "unknown_references": sum(len(v) for v in unknown.values()),
        },
        "referenced_by_file": {
            rel: sorted(names & known) for rel, names in sorted(refs.items())
        },
        "unknown_references": unknown,
        "nodes": [_node(conn, name) for name in sorted(core)],
        "edges": edges,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Falha se o JSON estiver desatualizado"
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Inclui .sql nao rastreados (git ls-files -co); so para regenerar local",
    )
    args = parser.parse_args(argv)
    if not SCHEMA_DB.is_file():
        print(
            f"schema.db ausente: rode Tools/oracle/build_oracle_catalog.py ({SCHEMA_DB})",
            file=sys.stderr,
        )
        return 2
    conn = sqlite3.connect(f"file:{SCHEMA_DB.as_posix()}?mode=ro", uri=True)
    try:
        graph = build(conn, references(repo_sql_files(args.include_untracked)))
    finally:
        conn.close()
    text = json.dumps(graph, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != text:
            print(
                "core-graph.json desatualizado: rode Tools/oracle/gerar_core_graph.py",
                file=sys.stderr,
            )
            return 1
        print("core-graph.json em dia.")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    stats = graph["stats"]
    print(
        f"core-graph.json gerado em {datetime.now():%H:%M:%S}: {stats['core_objects']} objetos, "
        f"{stats['fk_edges_among_core_objects']} FKs, {stats['sql_files_with_refs']} arquivos, "
        f"{stats['unknown_references']} referencias desconhecidas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

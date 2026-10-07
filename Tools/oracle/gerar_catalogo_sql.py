"""Gera `docs/oracle-schema/consultas/CATALOGO_QUERIES.md` a partir do disco.

O catálogo é derivado, nunca editado à mão:

- inventário: os arquivos `.sql` das pastas `NN_*` (fonte de verdade);
- descrição/categoria: linhas `OBJETIVO:` e `TIPO:` do cabeçalho de cada SQL;
- binds: extraídos do próprio SQL (mesma regra do `validar_sql_oracle.py`);
- status Oracle: `validacao_status.json`, alimentado pela saída do
  `validar_sql_oracle.py` via `--evidencia`. Cada status guarda o hash do
  arquivo validado; se o SQL mudou depois, o catálogo mostra isso em vez de
  manter um "sucesso" que não vale mais para o texto atual.

Uso:
    .venv/Scripts/python Tools/oracle/gerar_catalogo_sql.py
    .venv/Scripts/python Tools/oracle/gerar_catalogo_sql.py --evidencia <saida_validador.json>
    .venv/Scripts/python Tools/oracle/gerar_catalogo_sql.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle_session import is_session_drop  # noqa: E402
from validar_sql_oracle import (  # noqa: E402
    CONSULTAS_ROOT,
    _bind_names,
    content_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = CONSULTAS_ROOT
CATALOG = SQL_ROOT / "CATALOGO_QUERIES.md"
STATUS_FILE = SQL_ROOT / "validacao_status.json"
FOLDER_RE = re.compile(r"^\d{2}_")
LEGACY_PREFIX = "Produção Beneficimento/sql/"  # local do acervo até 06/10/2026
HEADER_LINES = 40
# Pastas fora do smoke por desenho (ver `_files` em validar_sql_oracle.py).
NOT_VALIDATED = {
    "11_views_referencia_sgt": "referência (DDL de view, não executada)",
    "12_manutencao_dml_restrito": "DML restrito (nunca executado)",
}
# Evidência complementar que o validador não captura (ex.: execução real no runner).
NOTES: dict[str, str] = {}
STATUS_LABELS = {
    "validated": "✅ validada",
    "parse_ok": "🟡 só parse",
    "parse_ok_smoke_timeout": "⏱️ parse ok, execução estourou o prazo",
    "parse_ok_smoke_error": "⚠️ parse ok, execução falhou",
    "blocked_custom_function": "🟡 parse ok; execução não feita (guard não reconhece uma função)",
    "blocked_guard": "🔒 bloqueada pelo guard",
    "blocked_multiple_statements": "❌ mais de uma instrução",
    "oracle_error": "❌ erro Oracle",
    "timeout": "⏱️ timeout",
    "encoding_error": "❌ encoding",
}


def _sha8(path: Path) -> str:
    return str(content_sha256(path.read_bytes()))[:8]


def _header_field(text: str, field: str) -> str:
    """Valor de `FIELD:` nas primeiras linhas (aceita `-- FIELD:` e bloco /* */)."""
    pattern = re.compile(rf"^\s*(?:--\s*)?{field}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in text.splitlines()[:HEADER_LINES]:
        match = pattern.match(line)
        if match:
            value = re.sub(r"\s*\*/\s*$", "", match.group(1))
            return value.replace("|", "/")
    return ""


def _inventory() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    folders = sorted(
        p for p in SQL_ROOT.iterdir() if p.is_dir() and FOLDER_RE.match(p.name)
    )
    for folder in folders:
        # Recursivo, como `_files` em validar_sql_oracle.py (rglob). As pastas 11 e 12
        # ficam no inventário (o validador as exclui da execução; aqui aparecem
        # como NOT_VALIDATED).
        for path in sorted(folder.rglob("*.sql")):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(folder).as_posix()
            items.append(
                {
                    "folder": folder.name,
                    "file": rel,
                    "key": f"{folder.name}/{rel}",
                    "objetivo": _header_field(text, "OBJETIVO")
                    or "(sem OBJETIVO no cabeçalho)",
                    "tipo": _header_field(text, "TIPO"),
                    "binds": _bind_names(text),
                    "sha8": _sha8(path),
                }
            )
    return items


def _load_status() -> dict[str, Any]:
    if not STATUS_FILE.is_file():
        return {"schema": "sql-catalog-status/v1", "files": {}}
    data: dict[str, Any] = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    if "files" not in data:
        data = {"schema": "sql-catalog-status/v1", "files": {}}
    return data


_STATUS_RANK = {"validated": 2, "parse_ok": 1}


def _should_replace(current: dict[str, Any] | None, result: dict[str, Any]) -> bool:
    """Evidência mais antiga, ou mais fraca para o MESMO conteúdo, não rebaixa."""
    if current is None:
        return True
    new_date = str(result.get("started_at_utc", ""))[:10]
    if new_date < str(current.get("validated_at", "")):
        return False
    same_sha = current.get("sha8") == str(result.get("raw_sha256", ""))[:8]
    weaker = _STATUS_RANK.get(str(result.get("status")), 0) < _STATUS_RANK.get(
        str(current.get("status")), 0
    )
    return not (same_sha and weaker)


def _merge_evidence(status: dict[str, Any], evidence_path: Path) -> dict[str, Any]:
    """Incorpora a saída do validar_sql_oracle.py, sem caminhos absolutos nem
    dados retornados — só o necessário para o catálogo."""
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    prefix = CONSULTAS_ROOT.relative_to(ROOT).as_posix() + "/"
    for result in evidence.get("results", []):
        # Evidências gravadas antes da mudança do acervo usam o prefixo antigo.
        key = str(result["file"]).removeprefix(LEGACY_PREFIX).removeprefix(prefix)
        if not _should_replace(status["files"].get(key), result):
            continue
        status["files"][key] = {
            "status": result.get("status", "unknown"),
            "sample_rows": result.get("rows"),
            "execute_ms": result.get("execute_ms"),
            "sha8": str(result.get("raw_sha256", ""))[:8],
            "validated_at": str(result.get("started_at_utc", ""))[:10],
            "validator_version": result.get("validator_version"),
            "cancelled": is_session_drop(str(result.get("error", ""))),
        }
    status["files"] = dict(sorted(status["files"].items()))
    status["validated_on"] = str(evidence.get("generated_at_utc", ""))[:10]
    return status


def _br_date(iso: str) -> str:
    """`2026-09-29` -> `29/09/2026`; texto que não é data ISO volta como veio.

    O catálogo é Markdown, e a governança (`Test-DateConformidade.ps1`) exige
    DD/MM/YYYY na documentação. A evidência em JSON continua em ISO.
    """
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if match is None:
        return iso
    year, month, day = match.groups()
    return f"{day}/{month}/{year}"


def _status_cell(
    item: dict[str, Any], record: dict[str, Any] | None
) -> tuple[str, str, str]:
    """(status, amostra, tempo) de um arquivo."""
    if item["folder"] in NOT_VALIDATED:
        return NOT_VALIDATED[item["folder"]], "—", "—"
    if record is None:
        return "⬜ não validada", "—", "—"
    if record["sha8"] != item["sha8"]:
        validated_at = _br_date(str(record["validated_at"]))
        return f"⬜ alterada após validação de {validated_at}", "—", "—"
    label = STATUS_LABELS.get(record["status"], record["status"])
    if record.get("cancelled"):
        stage = "a execução" if record["status"].startswith("parse_ok") else "o parse"
        label = f"⏳ inconclusiva: sessão derrubada pela rede durante {stage}"
    label += NOTES.get(item["key"], "")
    rows = record.get("sample_rows")
    sample = "—" if rows is None else ("com dados" if rows else "vazia")
    ms = record.get("execute_ms")
    return label, sample, "—" if ms is None else f"{ms:.0f} ms"


def _summary_lines(
    items: list[dict[str, Any]], cells: dict[str, tuple[str, str, str]]
) -> list[str]:
    per_folder = Counter(item["folder"] for item in items)
    lines = [
        "## Resumo",
        "",
        f"**{len(items)} arquivos `.sql` em {len(per_folder)} pastas.**",
        "",
        "| Status | Arquivos |",
        "|---|---|",
    ]
    for label, count in sorted(
        Counter(c[0] for c in cells.values()).items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(f"| {label} | {count} |")
    empty = sum(1 for c in cells.values() if c[1] == "vazia")
    lines += [
        "",
        f"Amostra vazia: {empty} consulta(s) validadas não retornaram linhas na janela/filtros padrão "
        "(sentinelas de anomalia ou filtros sem dados no momento — não é erro).",
        "",
    ]
    return lines


def _folder_lines(
    folder: str, items: list[dict[str, Any]], cells: dict[str, tuple[str, str, str]]
) -> list[str]:
    lines = [
        f"### {folder} ({len(items)})",
        "",
        "| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in items:
        status, sample, elapsed = cells[item["key"]]
        binds = ", ".join(f"`:{b.lower()}`" for b in item["binds"]) or "—"
        lines.append(
            f"| `{item['file']}` | {item['objetivo']} | {item['tipo'] or '—'} | {binds} "
            f"| {status} | {sample} | {elapsed} |"
        )
    return lines + [""]


def render(items: list[dict[str, Any]], status: dict[str, Any]) -> str:
    records: dict[str, Any] = status.get("files", {})
    cells = {
        item["key"]: _status_cell(item, records.get(item["key"])) for item in items
    }
    lines = [
        "# Catálogo de Consultas SQL — Produção Beneficiamento",
        "",
        "> **Arquivo gerado — não edite à mão.** Regerar: `.venv/Scripts/python Tools/oracle/gerar_catalogo_sql.py`",
        "> (`--evidencia <saida_validador.json>` para atualizar o status Oracle; `--check` antes do PR).",
        ">",
        "> Inventário = arquivos `.sql` das pastas `NN_*`; Objetivo/Categoria = linhas `OBJETIVO:`/`TIPO:` do cabeçalho;",
        "> Binds = extraídos do SQL; Status = `validacao_status.json`, alimentado pela saída de `Tools/oracle/validar_sql_oracle.py`",
        "> (guard + parse + execução limitada a 1 linha). Status de um arquivo alterado depois da validação é descartado.",
        "> A referência estável de uma consulta é `pasta/arquivo.sql`.",
        "",
    ]
    lines += _summary_lines(items, cells)
    lines += ["## Inventário por pasta", ""]
    for folder in sorted({item["folder"] for item in items}):
        lines += _folder_lines(
            folder, [i for i in items if i["folder"] == folder], cells
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidencia", type=Path, action="append", default=[])
    parser.add_argument(
        "--check", action="store_true", help="Falha se o catálogo estiver desatualizado"
    )
    args = parser.parse_args(argv)

    status = _load_status()
    for evidence in args.evidencia:
        status = _merge_evidence(status, evidence)
    catalog = render(_inventory(), status)

    if args.check:
        current = CATALOG.read_text(encoding="utf-8") if CATALOG.is_file() else ""
        if current != catalog:
            print(
                "CATALOGO_QUERIES.md desatualizado: rode Tools/oracle/gerar_catalogo_sql.py",
                file=sys.stderr,
            )
            return 1
        print("CATALOGO_QUERIES.md em dia.")
        return 0

    if args.evidencia:
        STATUS_FILE.write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    CATALOG.write_text(catalog, encoding="utf-8", newline="\n")
    print(f"Catálogo gerado: {CATALOG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

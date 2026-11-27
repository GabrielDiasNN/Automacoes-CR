"""O SQL de runtime do Beneficiamento precisa existir no caminho configurado."""

import re
import sys
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from beneficiamento import (
    quality,
    settings,
)
from beneficiamento.data import writer

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_AS_ALIAS_RE = re.compile(r"\bAS\s+([A-Z_][A-Z0-9_$#]*)\s*$", re.IGNORECASE)
_TRAILING_COL_RE = re.compile(r"(?:[A-Z_][A-Z0-9_$#]*\.)?([A-Z_][A-Z0-9_$#]*)\s*$", re.IGNORECASE)


def _strip_sql_comments(sql: str) -> str:
    sem_bloco = _BLOCK_COMMENT_RE.sub(" ", sql)
    return _LINE_COMMENT_RE.sub("", sem_bloco)


def _iter_top_level_tokens(sql: str) -> list[tuple[int, str]]:
    """Percorre `sql` fora de strings literais, emitindo `(idx, char)` no nivel 0."""
    depth = 0
    in_single = False
    i = 0
    n = len(sql)
    tokens: list[tuple[int, str]] = []
    while i < n:
        ch = sql[i]
        if in_single:
            if ch == "'" and i + 1 < n and sql[i + 1] == "'":
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif depth == 0:
            tokens.append((i, ch))
        i += 1
    return tokens


def _is_word_boundary(text: str, start: int, length: int) -> bool:
    prev_ok = start == 0 or not (text[start - 1].isalnum() or text[start - 1] == "_")
    end = start + length
    next_ok = end >= len(text) or not (text[end].isalnum() or text[end] == "_")
    return prev_ok and next_ok


def _find_top_level_keyword(sql: str, keyword: str, *, start_after: int = 0, last: bool = False) -> int:
    upper = sql.upper()
    kw_len = len(keyword)
    matches = [
        idx
        for idx, _ch in _iter_top_level_tokens(sql)
        if idx >= start_after
        and upper.startswith(keyword, idx)
        and _is_word_boundary(sql, idx, kw_len)
    ]
    if not matches:
        return -1
    return matches[-1] if last else matches[0]


def _split_top_level_commas(select_list: str) -> list[str]:
    comma_positions = [idx for idx, ch in _iter_top_level_tokens(select_list) if ch == ","]
    parts: list[str] = []
    prev = 0
    for pos in comma_positions:
        parts.append(select_list[prev:pos].strip())
        prev = pos + 1
    tail = select_list[prev:].strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_final_select_columns(sql: str) -> set[str]:
    """Extrai nomes/aliases projetados no SELECT final de fora das CTEs."""
    clean = _strip_sql_comments(sql)
    last_top_select = _find_top_level_keyword(clean, "SELECT", last=True)
    assert last_top_select >= 0, "SELECT final nao encontrado no template SQL."

    from_idx = _find_top_level_keyword(clean, "FROM", start_after=last_top_select + 6)
    assert from_idx > last_top_select, "FROM do SELECT final nao encontrado."

    select_list = clean[last_top_select + 6 : from_idx]
    projected: set[str] = set()
    for expr in _split_top_level_commas(select_list):
        match_as = _AS_ALIAS_RE.search(expr)
        if match_as:
            projected.add(match_as.group(1).upper())
            continue
        match_col = _TRAILING_COL_RE.search(expr)
        if match_col:
            projected.add(match_col.group(1).upper())
    return projected


@pytest.mark.parametrize("periodo", settings.PERIOD_ORDER)
def test_template_de_cada_periodo_existe_no_disco(periodo: str) -> None:
    config = settings.get_period_config(periodo)
    template = settings.SQL_TEMPLATE_DIR / config.sql_template

    assert template.is_file(), (
        f"Template do período '{periodo}' ausente: {template}. O runner de produção "
        "depende dele; se o acervo foi reorganizado, ajuste settings.SQL_TEMPLATE_DIR."
    )


def test_template_nao_esta_vazio() -> None:
    config = settings.get_period_config("diario")
    raw_bytes = (settings.SQL_TEMPLATE_DIR / config.sql_template).read_bytes()
    assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "Template deve ser UTF-8 sem BOM."
    texto = raw_bytes.decode("utf-8")

    assert ":dt_inicio" in texto and ":dt_fim" in texto


def test_template_detalhado_projeta_todas_as_colunas_de_field_specs_e_qualidade() -> (
    None
):
    """Contrato: SELECT final do template deve projetar SEQ, OPERADOR_FINAL e
    todas as fontes exigidas por FIELD_SPECS e DETAILED_REQUIRED_COLUMNS."""
    config = settings.get_period_config("diario")
    texto = (settings.SQL_TEMPLATE_DIR / config.sql_template).read_text(
        encoding="utf-8"
    )
    projected = _extract_final_select_columns(texto)

    assert "SEQ" in projected, "SEQ (parte da PK) ausente no SELECT final."
    assert "OPERADOR_FINAL" in projected, "OPERADOR_FINAL ausente no SELECT final."

    specs_sem_fonte = [
        spec.column
        for spec in writer.FIELD_SPECS
        if not any(src.upper() in projected for src in spec.sources)
    ]
    assert not specs_sem_fonte, (
        f"Colunas de FIELD_SPECS sem fonte projetada no template: {specs_sem_fonte}"
    )

    ausentes_qualidade = [
        col for col in quality.DETAILED_REQUIRED_COLUMNS if col.upper() not in projected
    ]
    assert not ausentes_qualidade, (
        f"DETAILED_REQUIRED_COLUMNS ausentes no template: {ausentes_qualidade}"
    )

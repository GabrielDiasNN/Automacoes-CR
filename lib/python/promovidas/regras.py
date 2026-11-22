"""Avaliacao pura de regras de excecao, chaves e KPIs (sem I/O)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .config import CondicaoFiltro


def _como_float(valor: Any) -> float | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _como_texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _comparar_numerico(op: str, atual: Any, alvo: Any) -> bool:
    num_atual = _como_float(atual)
    num_alvo = _como_float(alvo)
    if num_atual is None or num_alvo is None:
        return False
    if op == "lt":
        return num_atual < num_alvo
    if op == "lte":
        return num_atual <= num_alvo
    if op == "gt":
        return num_atual > num_alvo
    return num_atual >= num_alvo


def avaliar_condicao(row: Mapping[str, Any], cond: CondicaoFiltro) -> bool:
    """Avalia uma condicao isolada contra uma linha do resultado SQL."""
    atual = row.get(cond.coluna)
    if cond.op == "eq":
        return _como_texto(atual) == _como_texto(cond.valor)
    if cond.op == "ne":
        return _como_texto(atual) != _como_texto(cond.valor)
    if cond.op in {"in", "not_in"}:
        itens = (
            cond.valor if isinstance(cond.valor, (list, tuple, set)) else [cond.valor]
        )
        esperados = {_como_texto(item) for item in itens}
        contido = _como_texto(atual) in esperados
        return contido if cond.op == "in" else not contido
    return _comparar_numerico(cond.op, atual, cond.valor)


def filtrar_excecoes(
    rows: Sequence[Mapping[str, Any]],
    condicoes: Sequence[CondicaoFiltro],
) -> list[dict[str, Any]]:
    """Devolve as linhas que satisfazem todas as condicoes (AND)."""
    if not condicoes:
        return [dict(row) for row in rows]
    return [
        dict(row)
        for row in rows
        if all(avaliar_condicao(row, cond) for cond in condicoes)
    ]


def extrair_chave(row: Mapping[str, Any], colunas_chave: Sequence[str]) -> str:
    """Monta chave deterministica de idempotencia a partir das colunas configuradas."""
    return "|".join(_como_texto(row.get(col)) for col in colunas_chave)


def _valor_kpi(rows: Sequence[Mapping[str, Any]], expr: str) -> float | int | None:
    if expr == "count":
        return len(rows)
    if ":" not in expr:
        return None
    op, coluna = expr.split(":", 1)
    valores = [v for r in rows if (v := _como_float(r.get(coluna))) is not None]
    resultado: float | None = None
    if op == "sum":
        resultado = round(sum(valores), 2)
    elif valores and op == "min":
        resultado = round(min(valores), 2)
    elif valores and op == "max":
        resultado = round(max(valores), 2)
    return resultado


def calcular_kpis(
    rows: Sequence[Mapping[str, Any]],
    kpis: Sequence[str],
) -> dict[str, float | int | None]:
    """Calcula KPIs declarativos (`count`, `sum:<COL>`, `min:<COL>`, `max:<COL>`)."""
    return {expr: _valor_kpi(rows, expr) for expr in kpis}

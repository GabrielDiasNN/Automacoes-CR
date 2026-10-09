"""Repositorio de SQLs parametrizadas do Beneficiamento."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .settings import PERIOD_ORDER, SQL_TEMPLATE_DIR, get_period_config


def load_sql_template(period: str, sql_dir: Path = SQL_TEMPLATE_DIR) -> str:
    config = get_period_config(period)
    path = sql_dir / config.sql_template
    if not path.exists():
        raise FileNotFoundError(f"Template SQL nao encontrado: {path}")
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def period_window(period: str, reference: date | None = None) -> tuple[date, date]:
    current = reference or date.today()
    normalized = period.strip().lower()
    if normalized == "diario":
        return current, current + timedelta(days=1)
    if normalized == "semanal":
        start = current - timedelta(days=current.weekday())
        return start, start + timedelta(days=7)
    if normalized == "mensal":
        start = current.replace(day=1)
        end = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, end
    if normalized == "anual":
        return date(current.year, 1, 1), date(current.year + 1, 1, 1)
    if normalized not in PERIOD_ORDER:
        raise ValueError(f"Periodo de Beneficiamento invalido: {period}")
    raise ValueError(f"Janela nao configurada para periodo: {period}")


def bind_parameters(period: str, reference: date | None = None) -> dict[str, Any]:
    start, end = period_window(period, reference)
    return {
        "dt_inicio": datetime.combine(start, time.min),
        "dt_fim": datetime.combine(end, time.min),
    }


def apply_rownum_limit(sql: str, max_rows: int | None) -> str:
    """Envelopa a query com limite de linhas.

    `sql` vem de `load_sql_template`, que lê um arquivo de `SQL_TEMPLATE_DIR`
    escolhido por `get_period_config` — nome fixo por período validado, não
    caminho de request. `max_rows` é coagido a `int`. Nenhuma das duas partes
    é entrada de usuário.
    """
    if not max_rows or max_rows <= 0:
        return sql
    return f"SELECT * FROM (\n{sql}\n) WHERE ROWNUM <= {int(max_rows)}"  # nosec B608


_FECHAMENTO_Q = {"[": "]", "{": "}", "(": ")", "<": ">"}


def _identificador(caractere: str) -> bool:
    return caractere.isalnum() or caractere in "_$#"


def _delimitador_de_q_literal(sql: str, i: int) -> int | None:
    """Posição do delimitador de um `q'X...X'` (ou `nq'`) que começa em `i`."""
    if i > 0 and _identificador(sql[i - 1]):
        return None
    inicio = i + 1 if sql[i : i + 1] in ("n", "N") else i
    if sql[inicio : inicio + 1] in ("q", "Q") and sql[inicio + 1 : inicio + 2] == "'":
        return inicio + 2
    return None


def _fim_de_literal(sql: str, i: int) -> int | None:
    """Índice logo após o literal, identificador ou q-literal que começa em `i`.

    Devolve None se não houver literal ali. Sem fechamento, o trecho vai até o
    fim do texto: a checagem então acusa a falta do bind em vez de passar.
    """
    if sql[i] in "'\"":
        aspas = sql[i]
        j = i + 1
        while True:
            j = sql.find(aspas, j)
            if j == -1:
                return len(sql)
            if aspas == "'" and sql.startswith("''", j):
                j += 2
                continue
            return j + 1
    delimitador_pos = _delimitador_de_q_literal(sql, i)
    if delimitador_pos is None:
        return None
    if delimitador_pos >= len(sql):
        return len(sql)
    delimitador = sql[delimitador_pos]
    fechamento = _FECHAMENTO_Q.get(delimitador, delimitador) + "'"
    fim = sql.find(fechamento, delimitador_pos + 1)
    return len(sql) if fim == -1 else fim + len(fechamento)


def _sem_comentarios(sql: str) -> str:
    """Remove comentários `--` e `/* */` e troca cada literal ou identificador por espaço.

    Assim `'--'` ou `q'[/*]'` não começam comentário e não engolem os binds que
    vêm depois na mesma linha. Com `sem_literais`, cada literal ou identificador
    vira um espaço, e um bind citado nele deixa de contar como bind.
    """
    partes: list[str] = []
    i = 0
    while i < len(sql):
        fim = _fim_de_literal(sql, i)
        if fim is not None:
            partes.append(" ")
            i = fim
        elif sql.startswith("--", i):
            fim_da_linha = sql.find("\n", i)
            i = len(sql) if fim_da_linha == -1 else fim_da_linha
        elif sql.startswith("/*", i):
            fim_do_bloco = sql.find("*/", i + 2)
            partes.append(" ")
            i = len(sql) if fim_do_bloco == -1 else fim_do_bloco + 2
        else:
            partes.append(sql[i])
            i += 1
    return "".join(partes)


_BIND_INICIO = re.compile(r":DT_INICIO(?![\w$#])")
_BIND_FIM = re.compile(r":DT_FIM(?![\w$#])")


def validate_static_sql(sql: str) -> list[str]:
    """Regras estáticas do template.

    Os binds `:dt_inicio` e `:dt_fim` são exigidos no SQL executável: fora de
    comentários e de literais, e como nome inteiro (`:dt_inicio_x` não conta).
    As demais regras leem o texto inteiro.
    """
    issues: list[str] = []
    upper_sql = sql.upper()
    if "SELECT *" in upper_sql:
        issues.append("SELECT * nao permitido em template operacional.")
    if "TRUNC(SYSDATE" in upper_sql:
        issues.append(
            "Janela hardcoded com SYSDATE encontrada; use binds :dt_inicio/:dt_fim."
        )
    executavel = _sem_comentarios(sql).upper()
    if not (_BIND_INICIO.search(executavel) and _BIND_FIM.search(executavel)):
        issues.append("Template deve possuir binds :dt_inicio e :dt_fim.")
    return issues

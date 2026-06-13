"""Persistencia idempotente do historico, orientada a dados (FIELD_SPECS).

Substitui o antigo ``salvar_historico`` de ~200 linhas de blocos try/except
manuais por uma tabela declarativa de campos + coercoes do nucleo. Mantem o
contrato: ``INSERT OR REPLACE`` na PK ``(NUMERO_OB, SEQ)``, pulando registros
sem OB, e gravando o payload original em ``DADOS_COMPLETOS`` para auditoria.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, NamedTuple

from ..core import normalize_shift, safe_strip, to_float
from .schema import COLUMN_NAMES, apply_pragmas, init_db


def _text_or_none(value: Any) -> str | None:
    text = safe_strip(value)
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0


def _date_iso(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = safe_strip(value)
    return text or None


class FieldSpec(NamedTuple):
    """Mapeia uma coluna tipada para suas fontes candidatas e a coercao aplicada."""

    column: str
    sources: tuple[str, ...]
    coerce: Callable[[Any], Any]


def _first(record: dict[str, Any], sources: tuple[str, ...]) -> Any:
    for key in sources:
        value = record.get(key)
        if value is not None:
            return value
    return None


# Specs das colunas tipadas (exceto derivadas e o blob), na ordem de COLUMNS.
FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("NUMERO_OB", ("NUMERO_OB",), safe_strip),
    FieldSpec("SEQ", ("SEQ",), _int_or_zero),
    FieldSpec("DATA_FIM", ("DATA_HORA_FIM", "DATA_FIM", "DATA_PROD"), _date_iso),
    FieldSpec("NUMERO_MAQUINA", ("NUMERO_MAQUINA",), _int_or_none),
    FieldSpec("NOME_MAQUINA", ("NOME_MAQUINA",), _text_or_none),
    FieldSpec("CD_DS_FASE", ("CD_DS_FASE",), _text_or_none),
    FieldSpec("REDUZ", ("REDUZ",), _text_or_none),
    FieldSpec("CODIGO_ALTERNATIVO", ("CODIGO_ALTERNATIVO",), _text_or_none),
    FieldSpec("DESCR_ITEM", ("DESCR_ITEM",), _text_or_none),
    FieldSpec("ARTIGO", ("ARTIGO",), _text_or_none),
    FieldSpec("DESCR_ARTIGO", ("DESCR_ARTIGO",), _text_or_none),
    FieldSpec("COR", ("COR",), _text_or_none),
    FieldSpec("DESCR_COR", ("DESCR_COR",), _text_or_none),
    FieldSpec("QT_KG", ("QT_KG",), to_float),
    FieldSpec("QT_MT", ("QT_MT",), to_float),
    FieldSpec("ANO_MES", ("ANO_MES",), _text_or_none),
    FieldSpec("ANO_SEM", ("ANO_SEM",), _int_or_none),
    FieldSpec("OPERADOR_FINAL", ("OPERADOR_FINAL",), _text_or_none),
    FieldSpec("REPROCESSO", ("REPROCESSO",), _int_or_zero),
    FieldSpec("MIN_REAL", ("MIN_REAL",), to_float),
    FieldSpec("MIN_PREV", ("MIN_PREV",), to_float),
    FieldSpec("DESVIO_MIN", ("DESVIO_MIN",), to_float),
)

_INSERT_SQL = (
    "INSERT OR REPLACE INTO fato_producao_historica ("
    + ", ".join(COLUMN_NAMES)
    + ") VALUES ("
    + ", ".join(["?"] * len(COLUMN_NAMES))
    + ");"
)


def _serialize_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (value.isoformat() if isinstance(value, (datetime, date)) else value)
        for key, value in record.items()
    }


def _build_row(record: dict[str, Any]) -> tuple[Any, ...] | None:
    values: dict[str, Any] = {
        spec.column: spec.coerce(_first(record, spec.sources)) for spec in FIELD_SPECS
    }
    if not values["NUMERO_OB"]:
        return None  # registro inconsistente sem OB

    serialized = _serialize_payload(record)
    turno_id, turno_label = normalize_shift(serialized)
    values["TURNO_ID"] = turno_id
    values["TURNO_LABEL"] = turno_label or "Indefinido"
    values["MAQUINA_KEY"] = safe_strip(record.get("NOME_MAQUINA"))
    values["FASE_KEY"] = safe_strip(record.get("CD_DS_FASE"))
    values["CODIGO_KEY"] = (
        safe_strip(record.get("CODIGO_ALTERNATIVO") or record.get("REDUZ")) or None
    )
    values["DADOS_COMPLETOS"] = json.dumps(serialized, ensure_ascii=False)

    return tuple(values[name] for name in COLUMN_NAMES)


def salvar_historico(
    records: list[dict[str, Any]], db_path: Path | str | None = None
) -> int:
    """Grava/atualiza registros idempotentemente; retorna a quantidade aplicada."""
    if not records:
        return 0

    path = init_db(db_path)
    rows = [
        row for row in (_build_row(record) for record in records) if row is not None
    ]
    if not rows:
        return 0

    with sqlite3.connect(path) as conn:
        apply_pragmas(conn)
        conn.executemany(_INSERT_SQL, rows)
        conn.commit()

    return len(rows)

"""Persistencia idempotente do historico, orientada a dados (FIELD_SPECS).

Substitui o antigo ``salvar_historico`` de ~200 linhas de blocos try/except
manuais por uma tabela declarativa de campos + coercoes do nucleo. Mantem o
contrato: ``INSERT OR REPLACE`` na PK ``(NUMERO_OB, SEQ)``, pulando registros
sem OB, e gravando o payload original em ``DADOS_COMPLETOS`` para auditoria.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple

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


# OBF.STATUS_FASE=4 corresponde a DS_STATUS_FASE='CONFIRMADA' na query Oracle
# (ver CASE OBF.STATUS_FASE em sql/templates/detalhado.sql); demais valores
# (PROGRAMADA/EMITIDA/PESADA/EM EXECUCAO) sao producao ainda nao concluida.
_STATUS_FASE_CONFIRMADA = 4


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
    FieldSpec("CODIGO_FASE", ("CODIGO_FASE",), _int_or_none),
    FieldSpec("DESCR_FASE", ("DESCR_FASE",), _text_or_none),
    FieldSpec("DESCR_GRUPO_FASE", ("DESCR_GRUPO_FASE",), _text_or_none),
    FieldSpec("SETOR_IND_SEQ", ("SETOR_IND_SEQ",), _int_or_none),
    FieldSpec("DESCR_SETOR_INDUST", ("DESCR_SETOR_INDUST",), _text_or_none),
    FieldSpec("TIPO_MAQUINA", ("TIPO_MAQUINA",), _int_or_none),
    FieldSpec("DESCR_TIPO_MAQ", ("DESCR_TIPO_MAQ",), _text_or_none),
    FieldSpec("REDUZ", ("REDUZ",), _text_or_none),
    FieldSpec("CODIGO_ALTERNATIVO", ("CODIGO_ALTERNATIVO",), _text_or_none),
    FieldSpec("DESCR_ITEM", ("DESCR_ITEM",), _text_or_none),
    FieldSpec("ARTIGO", ("ARTIGO",), _text_or_none),
    FieldSpec("DESCR_ARTIGO", ("DESCR_ARTIGO",), _text_or_none),
    FieldSpec("COR", ("COR",), _text_or_none),
    FieldSpec("DESCR_COR", ("DESCR_COR",), _text_or_none),
    FieldSpec("QT_KG", ("QT_KG",), to_float),
    FieldSpec("QT_MT", ("QT_MT",), to_float),
    FieldSpec("PECAS_ORIGEM", ("PECAS_ORIGEM",), _int_or_none),
    FieldSpec("KG_ORIGEM_REAL", ("KG_ORIGEM_REAL",), to_float),
    FieldSpec("PECAS_DESTINO", ("PECAS_DESTINO",), _int_or_none),
    FieldSpec("KG_DESTINO_REAL", ("KG_DESTINO_REAL",), to_float),
    FieldSpec("ANO_MES", ("ANO_MES",), _text_or_none),
    FieldSpec("ANO_SEM", ("ANO_SEM",), _int_or_none),
    FieldSpec("OPERADOR_FINAL", ("OPERADOR_FINAL",), _text_or_none),
    FieldSpec("REPROCESSO", ("REPROCESSO",), _int_or_zero),
    FieldSpec("STATUS_FASE", ("STATUS_FASE",), _int_or_none),
    FieldSpec("DS_STATUS_FASE", ("DS_STATUS_FASE",), _text_or_none),
    FieldSpec("MIN_REAL", ("MIN_REAL",), to_float),
    FieldSpec("MIN_PREV", ("MIN_PREV",), to_float),
    FieldSpec("MIN_SETUP", ("MIN_SETUP",), to_float),
    FieldSpec("MIN_PROCESSO", ("MIN_PROCESSO",), to_float),
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
    values["FASE_KEY"] = safe_strip(record.get("DESCR_FASE"))
    values["SETOR_KEY"] = safe_strip(record.get("DESCR_SETOR_INDUST")) or "SEM SETOR"
    values["GRUPO_FASE_KEY"] = safe_strip(record.get("DESCR_GRUPO_FASE"))
    values["TIPO_MAQ_KEY"] = safe_strip(record.get("DESCR_TIPO_MAQ"))
    values["STATUS_KEY"] = (
        "confirmada"
        if values["STATUS_FASE"] == _STATUS_FASE_CONFIRMADA
        else "planejada"
    )
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

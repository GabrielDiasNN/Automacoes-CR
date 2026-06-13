"""Compatibilidade: API historica reexportada do pacote ``data``.

O conteudo foi reorganizado em ``beneficiamento.data`` (schema/writer/queries).
Este modulo mantem os imports legados funcionando; prefira importar de
``beneficiamento.data`` em codigo novo.
"""

from __future__ import annotations

from .data.queries import buscar_historico, descrever_schema_historico
from .data.schema import HISTORICO_SCHEMA_VERSION, init_db, resolve_db_path
from .data.writer import salvar_historico

__all__ = [
    "init_db",
    "resolve_db_path",
    "HISTORICO_SCHEMA_VERSION",
    "salvar_historico",
    "buscar_historico",
    "descrever_schema_historico",
]

# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments,useless-import-alias
"""Implementação compartilhada dos contratos históricos baseados em SQLite.

Os pontos públicos são ``contracts.overview``, ``contracts.detail`` e
``contracts.tingimento``, todos reexportados por ``contracts/__init__.py``.
Este módulo apenas re-exporta os builders dos sub-módulos especializados.
"""

from __future__ import annotations

from ._queries_common import (
    _DETAIL_SELECT as _DETAIL_SELECT,
    _DETAIL_TYPED as _DETAIL_TYPED,
    _build_filtered_dataset as _build_filtered_dataset,
    _build_filtered_where as _build_filtered_where,
    _fetch_filter_options as _fetch_filter_options,
    _normalize_record as _normalize_record,
    _normalize_request_filters as _normalize_request_filters,
    _parse_date as _parse_date,
    _resolve_overview_window as _resolve_overview_window,
)
from ._queries_detail import (
    _build_trace as _build_trace,
    _detail_raw_records as _detail_raw_records,
    _detail_row_to_record as _detail_row_to_record,
    _summary_from_records as _summary_from_records,
)
from ._queries_overview import (
    _build_fases_criticas as _build_fases_criticas,
    _build_gargalos as _build_gargalos,
    _build_overview_kpis as _build_overview_kpis,
    _build_overview_series as _build_overview_series,
    _build_produtos as _build_produtos,
    _build_setores as _build_setores,
    _build_treemap as _build_treemap,
    _build_turnos as _build_turnos,
)

"""Mapa central de aliases de coluna e grupos de fase do Beneficiamento.

Centraliza o conhecimento sobre os multiplos nomes que a mesma grandeza pode
assumir entre o template detalhado, o anual e os snapshots ja agregados. Antes,
esses fallbacks ficavam espalhados como cadeias ``r.get("A") or r.get("B")``
em analytics.py e overview_v1.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Cada alias logico mapeia para a lista ordenada de colunas candidatas.
# A primeira presente (valor nao None) vence.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "volume_kg": ("QUANT_PROD", "QT_KG", "QUILOS", "kg_total"),
    "volume_mt": ("METROS", "QT_MT", "mt_total"),
    "maquina_cod": ("NUMERO_MAQUINA",),
    "maquina_nom": ("DESCR_MAQ", "NOME_MAQUINA"),
    "fase_cod": ("CODIGO_FASE", "FASE", "CD_FASE"),
    "fase_nom": ("DESCR_FASE",),
    "setor_nom": ("DESCR_SETOR_INDUST",),
    "grupo_fase_nom": ("DESCR_GRUPO_FASE",),
    "tipo_maquina_nom": ("DESCR_TIPO_MAQ",),
    "reduz": ("REDUZ", "CODIGO_REDUZIDO"),
    "codigo_operacional": ("CODIGO_ALTERNATIVO", "REDUZ"),
    "produto": ("DESCR_ITEM",),
    "artigo_cod": ("ARTIGO",),
    "artigo_nom": ("DESCR_ARTIGO",),
    "cor_nom": ("DESCR_COR",),
    "rendimento": ("RENDIMENTO_MEDIO", "RENDIMENTO", "rendimento_medio_ponderado"),
    "efic_carga": (
        "EFIC_CARGA_MEDIA",
        "EFIC_CARGA",
        "EFIC_PROC_LINHA",
        "efic_carga_media_ponderada",
    ),
}

# Grupos de fase reconhecidos por rotulo canonico -> codigos de fase Oracle aceitos.
PHASE_GROUPS: dict[str, tuple[int, ...]] = {
    "tingimento": (40,),
}


def resolve_alias(record: Mapping[str, Any], alias: str) -> Any:
    """Retorna o primeiro valor nao None entre as colunas candidatas do alias."""
    candidates = COLUMN_ALIASES.get(alias)
    if not candidates:
        raise KeyError(f"Alias de coluna desconhecido: {alias}")
    return first_present(record, candidates)


def first_present(record: Mapping[str, Any], fields: tuple[str, ...]) -> Any:
    """Primeiro valor nao None entre ``fields`` (ordem importa)."""
    for field in fields:
        value = record.get(field)
        if value is not None:
            return value
    return None

"""Coerção de tipos numéricos vindos do Oracle, compartilhada entre validadores de domínio.

Sem dependência do driver Oracle (ao contrário de `oracle_extract.py`): trata
apenas o valor já retornado pelo cursor (Decimal/float/str/None), então pode
ser importado por camadas de validação puras sem acoplá-las ao driver nem à
conexão — os módulos `validators.py` de cada automação declaram como contrato
"nenhuma função aqui abre conexão ou lê arquivo".
"""

from __future__ import annotations

from typing import Any


def coerce_int(valor: Any, campo: str, contexto: Any, erro_cls: type[Exception]) -> int:
    """Coage NUMBER do Oracle (Decimal/float/str) para int, ou levanta `erro_cls`."""
    if valor is None:
        raise erro_cls(f"{contexto}: campo '{campo}' esta nulo")
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise erro_cls(
            f"{contexto}: campo '{campo}' nao e numerico (valor={valor!r})"
        ) from exc


def coerce_float(
    valor: Any, campo: str, contexto: Any, erro_cls: type[Exception]
) -> float:
    """Coage NUMBER do Oracle (Decimal/float/str) para float, ou levanta `erro_cls`."""
    if valor is None:
        raise erro_cls(f"{contexto}: campo '{campo}' esta nulo")
    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
        raise erro_cls(
            f"{contexto}: campo '{campo}' nao e numerico (valor={valor!r})"
        ) from exc

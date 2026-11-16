"""Base declarativa do ORM, isolada para quebrar o ciclo database <-> models.

``database`` precisa importar ``models`` no topo (validação de schema e purge),
e ``models`` precisa de ``Base``. Manter ``Base`` aqui evita o import circular
sem import tardio.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


# RESIDUAL (too-few-public-methods): classe-base declarativa do SQLAlchemy; o contrato
# e herdado de DeclarativeBase (metadata, registry) e nao ha metodos proprios a expor.
class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Base declarativa tipada (SQLAlchemy 2.0) de todos os modelos ORM."""

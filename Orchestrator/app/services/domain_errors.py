"""Erro de regra de negócio com o status HTTP correspondente.

Os services levantam `DomainRuleError`; os routers só o traduzem em `HTTPException`.
"""

from __future__ import annotations


class DomainRuleError(Exception):
    """Regra de negócio violada, com o status HTTP e a mensagem para o cliente."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

"""Runner Python da automacao OBs Restricao Branco (ORB-07), delegando ao motor comum.

Substitui a orquestracao do ``run.ps1`` anterior (shim) e delega pre-flight, lock,
rotacao de log, extract (3x), transform (``format_message.py``), dispatch WhatsApp
(AUTO/BATCH) e commit de estado para ``lib/python/obs_cards_runner.py``.

Uso: ``python run_orb.py [ExecId] [--dry-run]``.
"""

# pylint: disable=import-error
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

import hub_runner as hr  # noqa: E402
import obs_cards_runner as ocr  # noqa: E402

AUTOMACAO: Final[str] = "OBs Restrição Branco"
CHAVE_LOCK: Final[str] = "ORB-07"
SLUG_LOG: Final[str] = "Orb"
SLUG_TRACE: Final[str] = "orb"
PREFIXO: Final[str] = "orb"
ORB_DIR: Final[Path] = Path(__file__).resolve().parent
RAIZ: Final[Path] = ORB_DIR.parent
CODIGOS_SEM_FALHA: Final[tuple[int, ...]] = ocr.CODIGOS_SEM_FALHA
RETENCAO_LOG_DIAS: Final[int] = ocr.RETENCAO_LOG_DIAS
SPEC: Final[ocr.ObsCardsSpec] = ocr.ObsCardsSpec(
    automacao=AUTOMACAO,
    chave_lock=CHAVE_LOCK,
    slug_log=SLUG_LOG,
    slug_trace=SLUG_TRACE,
    prefixo=PREFIXO,
)


class Caminhos:  # pylint: disable=too-few-public-methods
    """Atalho de caminhos de ORB-07 sobre ``obs_cards_runner.Caminhos``."""

    @staticmethod
    def da_pasta(pasta: Path, raiz: Path = RAIZ) -> ocr.Caminhos:
        """Caminhos padrao de ORB-07 a partir da pasta da automacao e da raiz."""
        return ocr.Caminhos.da_pasta(pasta, raiz, prefixo=PREFIXO)


def executar(
    ctx: hr.HubRunContext,
    caminhos: ocr.Caminhos,
    *,
    dry_run: bool = False,
    aviso_env: str | None = None,
) -> int:
    """Roda o fluxo completo de ORB-07 e devolve o exit code."""
    return ocr.executar(ctx, caminhos, SPEC, dry_run=dry_run, aviso_env=aviso_env)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: ``run_orb.py [ExecId] [--dry-run]``. Devolve o exit code."""
    return ocr.rodar_cli(SPEC, ORB_DIR, RAIZ, argv)


if __name__ == "__main__":
    sys.exit(main())

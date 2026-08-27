"""Testes de lib/python/log_masking.py — paridade com Protect-SensitiveData."""

import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "python"
    ),
)

from log_masking import (  # noqa: E402  pylint: disable=wrong-import-position
    mask_sensitive,
)


def test_mascara_email_preservando_primeira_letra_e_dominio() -> None:
    assert mask_sensitive("aviso para joao.silva@empresa.com.br hoje") == (
        "aviso para j***@empresa.com.br hoje"
    )


def test_mascara_segredos_rotulados() -> None:
    # Paridade exata com Protect-SensitiveData: separador é `[:= ]\s*` — cobre
    # `token: valor`, `password=valor` e `apikey valor`, mas não ` = ` com
    # espaço dos dois lados (o regex do PS também não cobre esse caso).
    assert "[REDACTED]" in mask_sensitive("token: abcd1234efgh")
    assert "[REDACTED]" in mask_sensitive("password=Sup3rS3nha")
    assert "[REDACTED]" in mask_sensitive("apikey 9999zzzz")


def test_mascara_host_de_connect_string_oracle() -> None:
    entrada = (
        "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=oradb.interno.local)(PORT=1521)))"
    )
    saida = mask_sensitive(entrada)
    assert "oradb.interno.local" not in saida
    assert "[HIDDEN]" in saida


def test_texto_sem_segredo_passa_intacto() -> None:
    assert (
        mask_sensitive("120 OBs lidas, 2 qualificadas")
        == "120 OBs lidas, 2 qualificadas"
    )


def test_vazio_ou_espacos_vira_string_vazia() -> None:
    assert mask_sensitive("") == ""
    assert mask_sensitive("   ") == ""


def test_nao_mascara_palavra_user_sem_rotulo_de_segredo() -> None:
    # Paridade: Protect-SensitiveData não trata "user" como rótulo de segredo.
    assert mask_sensitive("user=admin") == "user=admin"

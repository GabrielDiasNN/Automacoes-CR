"""Carregamento e validacao de `promocao.json`."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

ModoOperacao = Literal["sombra", "producao"]
OperadorFiltro = Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte"]

_MODOS_VALIDOS: Final[frozenset[str]] = frozenset({"sombra", "producao"})
_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COR_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DESTINOS_VALIDOS: Final[frozenset[str]] = frozenset({"whatsapp", "dashboard"})
_OPS_VALIDOS: Final[frozenset[str]] = frozenset(
    {"eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte"}
)


@dataclass(frozen=True)
class CondicaoFiltro:
    """Predicado unitario sobre uma coluna de resultado SQL."""

    coluna: str
    op: OperadorFiltro
    valor: Any


@dataclass(frozen=True)
class ConfigPainel:
    """Configuracao de exibicao no Dashboard (/pcp)."""

    titulo: str
    kpis: tuple[str, ...]
    colunas: tuple[str, ...]


@dataclass(frozen=True)
class ConfigExcecao:  # pylint: disable=too-many-instance-attributes
    """Regra de excecao para disparo de alerta WhatsApp."""

    condicoes: tuple[CondicaoFiltro, ...]
    renotificar_apos_horas: float
    colunas_card: tuple[str, ...]
    titulo_alerta: str
    destino_whatsapp_env: str = "AUTOMACAO_ALERT_WHATSAPP"
    client_id_whatsapp: str = "hub-global"
    coluna_unidade: str = "UM"
    colunas_unidade: tuple[str, ...] = ()
    cor_header: str | None = None


@dataclass(frozen=True)
class ConfigPromocao:  # pylint: disable=too-many-instance-attributes
    """Contrato completo de uma consulta promovida (`promocao.json`)."""

    slug: str
    nome: str
    consulta: str
    modo: ModoOperacao
    chave: tuple[str, ...]
    destinos: tuple[str, ...]
    painel: ConfigPainel
    excecao: ConfigExcecao | None


def _texto_obrigatorio(dados: dict[str, Any], campo: str, origem: Path) -> str:
    valor = str(dados.get(campo) or "").strip()
    if not valor:
        raise ValueError(f"Campo obrigatorio '{campo}' ausente em {origem}.")
    return valor


def _parse_condicoes(raw: Any, origem: Path) -> tuple[CondicaoFiltro, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"'excecao.condicoes' deve ser uma lista em {origem}.")
    condicoes: list[CondicaoFiltro] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Condicao invalida em {origem}: esperado objeto.")
        coluna = str(item.get("coluna") or "").strip()
        op = str(item.get("op") or "").strip()
        if not coluna or op not in _OPS_VALIDOS:
            raise ValueError(
                f"Condicao invalida (coluna='{coluna}', op='{op}') em {origem}."
            )
        condicoes.append(
            CondicaoFiltro(
                coluna=coluna,
                op=cast(OperadorFiltro, op),
                valor=item.get("valor"),
            )
        )
    return tuple(condicoes)


def _parse_excecao(
    bruto: dict[str, Any], titulo_padrao: str, origem: Path
) -> ConfigExcecao | None:
    raw = bruto.get("excecao")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"Campo 'excecao' deve ser um objeto em {origem}.")
    colunas = _parse_lista_strings(
        raw.get("colunas_card"), "excecao.colunas_card", origem, padrao=[]
    )
    horas_raw = raw.get("renotificar_apos_horas", 24.0)
    if isinstance(horas_raw, bool) or horas_raw is None:
        raise ValueError(
            f"'renotificar_apos_horas' invalido em {origem}: esperado numero >= 0."
        )
    try:
        horas = float(horas_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'renotificar_apos_horas' invalido em {origem}.") from exc
    if not math.isfinite(horas) or horas < 0:
        raise ValueError(
            f"'renotificar_apos_horas' invalido (negativo ou nao finito) em {origem}."
        )
    colunas_unidade = _parse_lista_strings(
        raw.get("colunas_unidade"), "excecao.colunas_unidade", origem, padrao=[]
    )
    cor_header_raw = raw.get("cor_header")
    cor_header: str | None = None
    if cor_header_raw is not None:
        cor_txt = str(cor_header_raw).strip()
        if cor_txt:
            if not _COR_HEX_RE.match(cor_txt):
                raise ValueError(
                    f"'excecao.cor_header' invalido em {origem}: esperado #RRGGBB."
                )
            cor_header = cor_txt.upper()
    return ConfigExcecao(
        condicoes=_parse_condicoes(raw.get("condicoes"), origem),
        renotificar_apos_horas=horas,
        colunas_card=colunas,
        titulo_alerta=str(raw.get("titulo_alerta") or "").strip() or titulo_padrao,
        destino_whatsapp_env=(
            str(bruto.get("destino_whatsapp_env") or "").strip()
            or "AUTOMACAO_ALERT_WHATSAPP"
        ),
        client_id_whatsapp=(
            str(bruto.get("client_id_whatsapp") or "").strip() or "hub-global"
        ),
        coluna_unidade=str(raw.get("coluna_unidade") or "").strip() or "UM",
        colunas_unidade=colunas_unidade,
        cor_header=cor_header,
    )


def _parse_lista_strings(
    raw: Any, campo: str, origem: Path, *, padrao: list[str]
) -> tuple[str, ...]:
    valores = padrao if raw is None else raw
    if not isinstance(valores, list) or not all(
        isinstance(item, str) and item.strip() for item in valores
    ):
        raise ValueError(f"'{campo}' deve ser uma lista de strings em {origem}.")
    return tuple(item.strip() for item in valores)


def _parse_painel(bruto: dict[str, Any], origem: Path) -> ConfigPainel:
    painel_raw = bruto.get("painel")
    if not isinstance(painel_raw, dict):
        raise ValueError(f"Campo 'painel' obrigatorio em {origem}.")
    titulo = _texto_obrigatorio(painel_raw, "titulo", origem)
    kpis = _parse_lista_strings(
        painel_raw.get("kpis"), "painel.kpis", origem, padrao=["count"]
    )
    colunas = _parse_lista_strings(
        painel_raw.get("colunas"), "painel.colunas", origem, padrao=[]
    )
    return ConfigPainel(titulo=titulo, kpis=kpis, colunas=colunas)


def carregar_config(caminho: Path) -> ConfigPromocao:
    """Le e valida ``promocao.json``, devolvendo ``ConfigPromocao``."""
    bruto: Any = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(bruto, dict):
        raise ValueError(f"Raiz de {caminho} deve ser um objeto JSON.")

    slug = _texto_obrigatorio(bruto, "slug", caminho)
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"'slug' invalido ('{slug}') em {caminho}: use apenas minusculas, digitos e hifens."
        )
    nome = _texto_obrigatorio(bruto, "nome", caminho)
    consulta = _texto_obrigatorio(bruto, "consulta", caminho)
    consulta_path = Path(consulta)
    if (
        consulta_path.is_absolute()
        or bool(consulta_path.drive)
        or bool(consulta_path.root)
        or ".." in consulta_path.parts
    ):
        raise ValueError(
            f"'consulta' deve ser caminho relativo dentro da pasta em {caminho}."
        )
    try:
        (caminho.parent / consulta_path).resolve().relative_to(caminho.parent.resolve())
    except ValueError as exc:
        raise ValueError(
            f"'consulta' deve permanecer contido na pasta em {caminho}."
        ) from exc

    modo = str(bruto.get("modo") or "sombra").strip().lower()
    if modo not in _MODOS_VALIDOS:
        raise ValueError(f"'modo' invalido ('{modo}') em {caminho}.")

    chave_raw = bruto.get("chave") or []
    if not isinstance(chave_raw, list) or not chave_raw:
        raise ValueError(f"'chave' deve listar ao menos uma coluna em {caminho}.")
    chave = tuple(str(c).strip() for c in chave_raw if str(c).strip())
    if not chave:
        raise ValueError(
            f"'chave' deve conter ao menos uma coluna valida em {caminho}."
        )

    destinos_raw = bruto.get("destinos")
    if destinos_raw is None:
        destinos_raw = ["dashboard"]
    if not isinstance(destinos_raw, list):
        raise ValueError(f"'destinos' deve ser uma lista em {caminho}.")
    destinos = tuple(str(d).strip().lower() for d in destinos_raw if str(d).strip())
    if not destinos or any(d not in _DESTINOS_VALIDOS for d in destinos):
        raise ValueError(f"'destinos' invalido em {caminho}: {destinos_raw}.")

    painel = _parse_painel(bruto, caminho)
    return ConfigPromocao(
        slug=slug,
        nome=nome,
        consulta=consulta,
        modo=cast(ModoOperacao, modo),
        chave=chave,
        destinos=destinos,
        painel=painel,
        excecao=_parse_excecao(bruto, painel.titulo, caminho),
    )

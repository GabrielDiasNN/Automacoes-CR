"""Carregamento e validacao de `promocao.json`."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

ModoOperacao = Literal["sombra", "producao"]
OperadorFiltro = Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte"]

_MODOS_VALIDOS: Final[frozenset[str]] = frozenset({"sombra", "producao"})
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
class ConfigExcecao:
    """Regra de excecao para disparo de alerta WhatsApp."""

    condicoes: tuple[CondicaoFiltro, ...]
    renotificar_apos_horas: float
    colunas_card: tuple[str, ...]
    titulo_alerta: str
    destino_whatsapp_env: str = "AUTOMACAO_ALERT_WHATSAPP"
    client_id_whatsapp: str = "hub-global"


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
    colunas_raw = raw.get("colunas_card") or []
    if not isinstance(colunas_raw, list) or not all(
        isinstance(c, str) and c.strip() for c in colunas_raw
    ):
        raise ValueError(f"'excecao.colunas_card' invalido em {origem}.")
    horas = float(raw.get("renotificar_apos_horas", 24.0))
    if not math.isfinite(horas) or horas < 0:
        raise ValueError(
            f"'renotificar_apos_horas' invalido (negativo ou nao finito) em {origem}."
        )
    return ConfigExcecao(
        condicoes=_parse_condicoes(raw.get("condicoes"), origem),
        renotificar_apos_horas=horas,
        colunas_card=tuple(c.strip() for c in colunas_raw),
        titulo_alerta=str(raw.get("titulo_alerta") or titulo_padrao).strip(),
        destino_whatsapp_env=str(
            bruto.get("destino_whatsapp_env") or "AUTOMACAO_ALERT_WHATSAPP"
        ).strip(),
        client_id_whatsapp=str(bruto.get("client_id_whatsapp") or "hub-global").strip(),
    )


def carregar_config(caminho: Path) -> ConfigPromocao:
    """Le e valida ``promocao.json``, devolvendo ``ConfigPromocao``."""
    bruto: Any = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(bruto, dict):
        raise ValueError(f"Raiz de {caminho} deve ser um objeto JSON.")

    slug = _texto_obrigatorio(bruto, "slug", caminho)
    nome = _texto_obrigatorio(bruto, "nome", caminho)
    consulta = _texto_obrigatorio(bruto, "consulta", caminho)
    consulta_path = Path(consulta)
    if consulta_path.is_absolute() or ".." in consulta_path.parts:
        raise ValueError(
            f"'consulta' deve ser caminho relativo dentro da pasta em {caminho}."
        )

    modo = str(bruto.get("modo") or "sombra").strip().lower()
    if modo not in _MODOS_VALIDOS:
        raise ValueError(f"'modo' invalido ('{modo}') em {caminho}.")

    chave_raw = bruto.get("chave") or []
    if not isinstance(chave_raw, list) or not chave_raw:
        raise ValueError(f"'chave' deve listar ao menos uma coluna em {caminho}.")
    chave = tuple(str(c).strip() for c in chave_raw if str(c).strip())
    if not chave:
        raise ValueError(f"'chave' deve conter ao menos uma coluna valida em {caminho}.")

    destinos_raw = bruto.get("destinos")
    if destinos_raw is None:
        destinos_raw = ["dashboard"]
    if not isinstance(destinos_raw, list):
        raise ValueError(f"'destinos' deve ser uma lista em {caminho}.")
    destinos = tuple(str(d).strip().lower() for d in destinos_raw if str(d).strip())
    if not destinos or any(d not in _DESTINOS_VALIDOS for d in destinos):
        raise ValueError(f"'destinos' invalido em {caminho}: {destinos_raw}.")

    painel_raw = bruto.get("painel")
    if not isinstance(painel_raw, dict):
        raise ValueError(f"Campo 'painel' obrigatorio em {caminho}.")
    titulo = _texto_obrigatorio(painel_raw, "titulo", caminho)
    kpis = tuple(
        str(k).strip() for k in (painel_raw.get("kpis") or ["count"]) if str(k).strip()
    )
    colunas = tuple(
        str(c).strip() for c in (painel_raw.get("colunas") or []) if str(c).strip()
    )

    return ConfigPromocao(
        slug=slug,
        nome=nome,
        consulta=consulta,
        modo=cast(ModoOperacao, modo),
        chave=chave,
        destinos=destinos,
        painel=ConfigPainel(titulo=titulo, kpis=kpis, colunas=colunas),
        excecao=_parse_excecao(bruto, titulo, caminho),
    )

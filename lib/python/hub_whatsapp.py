"""Base WhatsApp do runner Python do Hub (migracao do item 3, parte 2).

Porta para Python o que os ``run.ps1`` com WhatsApp usam do PowerShell, com as mesmas
regras e os mesmos formatos de arquivo:

* ``lib/Lib-WhatsAppBatch.psm1``: manifesto de cards (``read_cards_manifest``),
  ``batch_input.json`` (``write_whatsapp_batch_input``), reconciliacao do lote
  (``resolve_whatsapp_batch_delivery``) e ``record_counts`` parcial
  (``update_whatsapp_result_record_counts``);
* ``lib/Lib-Config.psm1``: ``whatsapp_config_enabled`` (Test-WhatsAppConfigEnabled);
* ``lib/Lib-Process.psm1``: ``get_whatsapp_auth_path`` (Get-WhatsAppAuthPath);
* ``lib/Send-WhatsApp.ps1``: ``send_whatsapp``, que monta a linha de comando do script
  e encaminha a saida ao log da execucao.

O modulo nao envia mensagem sozinho. ``send_whatsapp`` so aciona o ``Send-WhatsApp.ps1``
pelo executor injetado (em producao, ``executar_send_whatsapp`` roda powershell.exe);
os testes usam duble. Caminhos do Windows sao tratados como texto, como no PowerShell.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import IO, Any, Final, Literal

import hub_runner as hr

_VALORES_DESLIGADOS: Final[frozenset[str]] = frozenset({"false", "0", "no"})
# System.Decimal do .NET: maior inteiro representavel. Acima disso o PS 5.1 usa Double.
_LIMITE_DECIMAL: Final[Decimal] = Decimal("79228162514264337593543950335")
_MSG_COLECAO_VAZIA: Final[str] = (
    "Não é possível associar o argumento ao parâmetro 'Cards' porque ele é uma coleção vazia."
)
# Escapes do ConvertTo-Json do PS 5.1, medidos caractere a caractere (ver _json_string_ps).
_ESCAPES_NOMEADOS: Final[dict[str, str]] = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}
_ESCAPES_UNICODE: Final[frozenset[str]] = frozenset("&'<>\u0085  ")


# ---------------------------------------------------------------------------
# Tipos publicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardPagina:
    """Uma pagina do manifesto: uma entrada de ``cards_manifest.json``."""

    phase_key: str
    image_path: str
    caption: str
    ob_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResultadoManifesto:
    """Resultado de ``read_cards_manifest``: equivale a Valid, Cards e Error do PowerShell."""

    valid: bool
    cards: tuple[CardPagina, ...]
    error: str


StatusEntrega = Literal["AllSent", "PartialSent", "NoneSent"]


@dataclass(frozen=True)
class EntregaWhatsApp:
    """Reconciliacao do lote (``resolve_whatsapp_batch_delivery``), com os campos do PS."""

    status: StatusEntrega
    sent_count: int
    total_count: int
    delivered_ob_count: int
    failed_ob_count: int
    should_commit_state: bool


@dataclass(frozen=True)
class ComandoWhatsApp:
    """O que o executor precisa para rodar o Send-WhatsApp.ps1."""

    argv: tuple[str, ...]
    work_dir: Path
    ambiente: Mapping[str, str]


type EncaminharLinha = Callable[[str, str], None]
"""(linha, nivel padrao) -> None. O nivel padrao e INFO para stdout e WARN para stderr."""

type ExecutorWhatsApp = Callable[[ComandoWhatsApp, EncaminharLinha], int]
"""Roda o comando, encaminha cada linha de saida e devolve o exit code."""


class _ManifestoInvalido(Exception):
    """Motivo de rejeicao do manifesto; vira ``ResultadoManifesto(valid=False)``."""


# ---------------------------------------------------------------------------
# Auxiliares de dados (regras de Get-JsonPropValue e da conversao [string] do PS)
# ---------------------------------------------------------------------------


_SEPARADORES_NAO_ESPACO: Final[str] = "\x1c\x1d\x1e\x1f"


def _chave_real(objeto: dict[str, Any], nome: str) -> str | None:
    """Chave de ``objeto`` que casa com ``nome`` sem diferenciar caixa, ou None.

    O PowerShell busca propriedades sem diferenciar caixa; a chave exata tem prioridade.
    """
    if nome in objeto:
        return nome
    for chave in objeto:
        if str(chave).casefold() == nome.casefold():
            return str(chave)
    return None


def _prop(objeto: object, nome: str) -> object:
    """Valor de uma propriedade de objeto JSON (Get-JsonPropValue).

    Quem nao e dicionario (lista, texto, numero, None) devolve None, como no PowerShell.
    """
    if not isinstance(objeto, dict):
        return None
    chave = _chave_real(objeto, nome)
    if chave is None:
        return None
    valor: object = objeto[chave]
    return valor


def _definir(objeto: dict[str, Any], nome: str, valor: object) -> None:
    """Define uma propriedade, reaproveitando a chave que casa sem diferenciar caixa."""
    chave = _chave_real(objeto, nome)
    objeto[chave if chave is not None else nome] = valor


def _parse_float(literal: str) -> object:
    """Numero com ponto ou expoente, como o ConvertFrom-Json do PS 5.1 (JavaScriptSerializer).

    Sem expoente vira ``Decimal``, que preserva a escala do literal (``1.50`` continua
    ``1.50``). Com expoente vira ``float``. Valor que estoura o Double (``1e400``) e erro.
    """
    if "e" in literal or "E" in literal:
        valor = float(literal)
        if math.isinf(valor):
            raise ValueError(f"JSON primitivo inválido: {literal}.")
        return valor
    decimal = Decimal(literal)
    if decimal.adjusted() > 308:
        raise ValueError(f"JSON primitivo inválido: {literal}.")
    return decimal


def _parse_int(literal: str) -> int:
    """Inteiro do JSON. Acima do maior Double o PS 5.1 nao consegue ler: erro de parse."""
    valor = int(literal)
    if abs(valor) > sys.float_info.max:
        raise ValueError(f"JSON primitivo inválido: {literal}.")
    return valor


_CONSTANTES_JSON: Final[dict[str, float]] = {
    "NaN": math.nan,
    "Infinity": math.inf,
    "-Infinity": -math.inf,
}


def _parse_constante(nome: str) -> float:
    """NaN, Infinity e -Infinity viram Double no ConvertFrom-Json do PS 5.1 (medido). -NaN e erro."""
    return _CONSTANTES_JSON[nome]


def _em_branco(texto: str) -> bool:
    """String.IsNullOrWhiteSpace do .NET: U+001C..U+001F nao contam como espaco (no Python, sim)."""
    return all(c.isspace() and c not in _SEPARADORES_NAO_ESPACO for c in texto)


def _ler_json(bruto: str) -> object:
    """Parseia o texto como o ConvertFrom-Json do PS 5.1: numeros e erros no mesmo formato."""
    # strict=False: o ConvertFrom-Json do PS 5.1 aceita caractere de controle cru em string.
    dados: object = json.loads(
        bruto,
        strict=False,
        parse_float=_parse_float,
        parse_int=_parse_int,
        parse_constant=_parse_constante,
    )
    return dados


def _g15(valor: float) -> str:
    """Double como [string] do PS 5.1 (G15 do .NET Framework): 15 digitos, E maiusculo.

    Zero sai sem sinal. NaN e infinitos saem com os nomes do .NET (NaN, Infinity, -Infinity).
    """
    if math.isnan(valor):
        return "NaN"
    if math.isinf(valor):
        return "Infinity" if valor > 0 else "-Infinity"
    if valor == 0:
        return "0"
    return format(valor, ".15g").replace("e", "E")


def _decimal_ps(valor: Decimal) -> str | None:
    """Texto de um System.Decimal do PS 5.1, ou None quando o valor nao cabe em Decimal.

    A escala do literal e mantida (``1.50`` fica ``1.50``). Acima de 28 casas decimais o valor
    e arredondado para 28 (meio para par) e depois para 29 digitos significativos. Zero perde
    o sinal (``-0.0`` vira ``0.0``). Aproximacao: o arredondamento segue a regra do Decimal
    do .NET observada nos testes; casos com mais de 29 digitos fora dos medidos nao foram provados.
    """
    if abs(valor) > _LIMITE_DECIMAL:
        return None
    with localcontext() as ctx:
        ctx.rounding = ROUND_HALF_EVEN
        ctx.prec = 100
        expoente = valor.as_tuple().exponent
        if isinstance(expoente, int) and expoente < -28:
            valor = valor.quantize(Decimal("1e-28"))
        ctx.prec = 29
        arredondado = +valor
    if arredondado == 0:
        arredondado = abs(arredondado)
    return format(arredondado, "f")


def _numero_texto(valor: int | float | Decimal) -> str:
    """Numero do JSON como [string] do PS 5.1: Int32/Int64, Decimal ou Double (G15)."""
    if isinstance(valor, int):
        return str(valor) if abs(valor) <= _LIMITE_DECIMAL else _g15(float(valor))
    if isinstance(valor, float):
        return _g15(valor)
    decimal_ps = _decimal_ps(valor)
    return _g15(float(valor)) if decimal_ps is None else decimal_ps


def _texto_item(valor: object) -> str:
    """Item de lista ou propriedade de objeto no [string]: lista vira System.Object[], objeto vazio."""
    if isinstance(valor, list):
        return "System.Object[]"
    if isinstance(valor, dict):
        return ""
    return _texto(valor)


def _texto(valor: object) -> str:
    """Valor do JSON como o [string] do PowerShell 5.1.

    null vira vazio, bool vira True/False e numero segue ``_numero_texto``. Lista junta os
    itens com espaco (como ``$OFS``). Objeto vira ``@{chave=valor; ...}`` e objeto vazio vira
    vazio. Medido em probe no PS 5.1 (ver testes de paridade).
    """
    if isinstance(valor, dict):
        return _objeto_texto(valor)
    if isinstance(valor, list):
        return " ".join(_texto_item(item) for item in valor)
    if isinstance(valor, bool):
        return "True" if valor else "False"
    if isinstance(valor, (int, float, Decimal)):
        return _numero_texto(valor)
    return "" if valor is None else str(valor)


def _objeto_texto(valor: dict[str, object]) -> str:
    """Objeto JSON no [string] do PS 5.1: objeto vazio vira vazio; senao ``@{chave=valor; ...}``."""
    if not valor:
        return ""
    pares = "; ".join(f"{chave}={_texto_item(item)}" for chave, item in valor.items())
    return "@{" + pares + "}"


def _como_lista(dados: object) -> list[object]:
    """Raiz do JSON como lista, como @($parsed): null vira lista vazia, escalar vira um item."""
    if dados is None:
        return []
    if isinstance(dados, list):
        return list(dados)
    return [dados]


def _eh_verdadeiro(valor: object) -> bool:
    """Valor de ``success`` como ``valor -eq $true`` no PowerShell 5.1 (medido em probe).

    bool vale por si. Numero vale quando e igual a 1 (1, 1.0, 1e0). Texto vale so quando e
    'true' sem diferenciar caixa e sem espacos (nao ha Trim). Lista vale quando algum item
    escalar vale, porque o ``-eq`` filtra a lista. Itens aninhados e objetos nao foram medidos
    e contam como falsos. Null e objeto sao falsos.
    """
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float, Decimal)):
        return valor == 1
    if isinstance(valor, str):
        return valor.casefold() == "true"
    if isinstance(valor, list):
        return any(
            _eh_verdadeiro(item) for item in valor if not isinstance(item, (list, dict))
        )
    return False


# ---------------------------------------------------------------------------
# Caminhos (Path.IsPathRooted, Join-Path e Get-WhatsAppAuthPath, sem I/O)
# ---------------------------------------------------------------------------


def _e_raiz(caminho: str) -> bool:
    """Path.IsPathRooted do .NET: separador inicial ou letra de unidade (C: ou C:foo)."""
    if caminho[:1] in ("\\", "/"):
        return True
    return len(caminho) >= 2 and caminho[1] == ":"


def _juntar(base: str, relativo: str) -> str:
    """Join-Path do PowerShell: une com barra invertida e troca '/' por '\\' nos dois lados."""
    base_norm = base.replace("/", "\\")
    relativo_norm = relativo.replace("/", "\\")
    if base_norm.endswith("\\"):
        return base_norm + relativo_norm
    return f"{base_norm}\\{relativo_norm}"


def _caminho_completo(base: str, imagem: str) -> str:
    """Caminho da imagem do manifesto: rooted fica como esta, relativo une-se a base."""
    return imagem if _e_raiz(imagem) else _juntar(base, imagem)


def _arquivo_fisico(caminho: str) -> Path:
    """Path do arquivo no disco. No Windows e o proprio caminho; em POSIX (so testes), troca '\\'."""
    return Path(caminho.replace("\\", os.sep))


def _arquivo_com_conteudo(caminho: str) -> bool:
    """True quando o caminho e um arquivo com pelo menos um byte (Test-Path + Length -le 0)."""
    arquivo = _arquivo_fisico(caminho)
    return arquivo.is_file() and arquivo.stat().st_size > 0


def _gravar_utf8(caminho: Path, conteudo: str) -> None:
    """Grava texto em UTF-8 sem BOM (Write-Utf8NoBomFile)."""
    caminho.write_bytes(conteudo.encode("utf-8"))


# ---------------------------------------------------------------------------
# Manifesto de cards e batch_input.json (Lib-WhatsAppBatch.psm1)
# ---------------------------------------------------------------------------


def _ler_manifesto(caminho: Path) -> object:
    """Conteudo JSON do manifesto. Ausente, vazio ou ilegivel viram ``_ManifestoInvalido``."""
    if not caminho.exists():
        raise _ManifestoInvalido("cards_manifest.json nao encontrado.")
    try:
        bruto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise _ManifestoInvalido(f"Falha ao ler cards_manifest.json: {exc}") from exc
    if not bruto.strip():
        raise _ManifestoInvalido("cards_manifest.json vazio.")
    try:
        dados = _ler_json(bruto)
    except ValueError as exc:
        raise _ManifestoInvalido(f"Falha ao ler cards_manifest.json: {exc}") from exc
    return dados


def _ob_ids_validos(bruto: object, phase_key: str) -> tuple[str, ...]:
    """Lista de OBs de um card: precisa ser lista nao vazia, sem IDs em branco."""
    prefixo = "Entrada invalida em cards_manifest.json:"
    if not isinstance(bruto, list):
        raise _ManifestoInvalido(
            f"{prefixo} ob_ids ausente ou invalido em '{phase_key}'."
        )
    if not bruto:
        raise _ManifestoInvalido(f"{prefixo} ob_ids vazio em '{phase_key}'.")
    if any(_em_branco(_texto(ob)) for ob in bruto):
        raise _ManifestoInvalido(f"{prefixo} ob_ids contem ID vazio em '{phase_key}'.")
    return tuple(_texto(ob) for ob in bruto)


def _card_valido(item: object, base_dir: str, vistos: set[str]) -> CardPagina:
    """Valida um card na ordem do PowerShell: campos, chave unica, ob_ids e imagem."""
    phase_key = _texto(_prop(item, "phase_key"))
    image_path = _texto(_prop(item, "image_path"))
    caption = _texto(_prop(item, "caption"))
    if _em_branco(phase_key) or _em_branco(image_path) or _em_branco(caption):
        raise _ManifestoInvalido(
            "Entrada invalida em cards_manifest.json (phase_key/image_path/caption)."
        )
    chave = phase_key.casefold()
    if chave in vistos:
        raise _ManifestoInvalido(
            f"phase_key duplicado em cards_manifest.json: {phase_key}"
        )
    vistos.add(chave)
    ob_ids = _ob_ids_validos(_prop(item, "ob_ids"), phase_key)
    if not _arquivo_com_conteudo(_caminho_completo(base_dir, image_path)):
        raise _ManifestoInvalido(f"Imagem do card ausente ou vazia: {image_path}")
    return CardPagina(
        phase_key=phase_key, image_path=image_path, caption=caption, ob_ids=ob_ids
    )


def _cards_do_manifesto(caminho: Path, base_dir: str) -> list[CardPagina]:
    """Parseia o manifesto e valida cada card, na mesma ordem do PowerShell."""
    itens = _como_lista(_ler_manifesto(caminho))
    if not itens:
        raise _ManifestoInvalido("cards_manifest.json sem paginas.")
    vistos: set[str] = set()
    return [_card_valido(item, base_dir, vistos) for item in itens]


def _validar_saidas_card_unico(message_file: str, card_file: str) -> None:
    """Com um unico card, message.txt e card.png (quando informados) precisam ter conteudo."""
    if message_file.strip() and not _arquivo_com_conteudo(message_file):
        raise _ManifestoInvalido("message.txt nao foi gerado ou esta vazio.")
    if card_file.strip() and not _arquivo_com_conteudo(card_file):
        raise _ManifestoInvalido("card.png nao foi gerado ou esta vazio.")


def read_cards_manifest(
    manifest_path: Path,
    base_dir: Path,
    message_file: str = "",
    card_file: str = "",
) -> ResultadoManifesto:
    """Le e valida ``cards_manifest.json`` (Read-CardsManifest).

    Conteudo invalido nao levanta excecao: devolve ``valid=False`` com a mensagem do PS.
    Com um unico card, ``message_file`` e ``card_file`` (quando informados) tambem precisam
    existir com conteudo. Com mais de um card essas saidas nao sao checadas.
    """
    try:
        cards = _cards_do_manifesto(manifest_path, str(base_dir))
        if len(cards) == 1:
            _validar_saidas_card_unico(message_file, card_file)
    except _ManifestoInvalido as exc:
        return ResultadoManifesto(valid=False, cards=(), error=str(exc))
    return ResultadoManifesto(valid=True, cards=tuple(cards), error="")


def _json_string_ps(texto: str) -> str:
    """String como o ConvertTo-Json do PS 5.1 escreve (medido caractere a caractere).

    ``"`` e ``\\`` sao escapados; ``\\b \\t \\n \\f \\r`` sao nomeados; os demais controles
    (abaixo de U+0020), ``&``, ``'``, ``<``, ``>``, U+0085, U+2028 e U+2029 viram ``\\uXXXX``
    em hexa minuscula. Os demais caracteres, inclusive acentos e emoji, seguem crus em UTF-8.
    """
    partes: list[str] = []
    for caractere in texto:
        if caractere in _ESCAPES_NOMEADOS:
            partes.append(_ESCAPES_NOMEADOS[caractere])
        elif ord(caractere) < 0x20 or caractere in _ESCAPES_UNICODE:
            partes.append(f"\\u{ord(caractere):04x}")
        else:
            partes.append(caractere)
    return '"' + "".join(partes) + '"'


def _serializar_lote_ps(itens: Sequence[Sequence[tuple[str, str]]]) -> str:
    """Texto de ``batch_input.json`` no layout do ConvertTo-Json do PS 5.1.

    Indentacao de 4 espacos por nivel, ``"chave":  valor`` com dois espacos depois dos dois
    pontos, quebra de linha CRLF e sem quebra final. As chaves seguem a ordem dada.
    """
    linhas: list[str] = ["["]
    for indice, item in enumerate(itens):
        linhas.append("    {")
        for posicao, (chave, valor) in enumerate(item):
            virgula = "," if posicao < len(item) - 1 else ""
            linhas.append(f'        "{chave}":  {_json_string_ps(valor)}{virgula}')
        linhas.append("    }," if indice < len(itens) - 1 else "    }")
    linhas.append("]")
    return "\r\n".join(linhas)


def write_whatsapp_batch_input(
    cards: Sequence[CardPagina], base_dir: Path, batch_input_file: Path
) -> None:
    """Grava ``batch_input.json`` como o Write-WhatsAppBatchInput do PS 5.1 (UTF-8 sem BOM).

    Cada item leva ``caption``, ``image_path`` absoluto e ``phase_key``, nessa ordem (a ordem
    observada no Hashtable do PS), na ordem do manifesto. O layout segue o ConvertTo-Json do
    PS 5.1 (ver ``_serializar_lote_ps``), e os bytes gravados sao iguais aos do PS. Lista vazia
    e erro, como o parametro ``Cards`` obrigatorio do PS.
    """
    if not cards:
        raise ValueError(_MSG_COLECAO_VAZIA)
    itens = [
        [
            ("caption", card.caption),
            ("image_path", _caminho_completo(str(base_dir), card.image_path)),
            ("phase_key", card.phase_key),
        ]
        for card in cards
    ]
    _gravar_utf8(batch_input_file, _serializar_lote_ps(itens))


# ---------------------------------------------------------------------------
# Reconciliacao do lote (Resolve-WhatsAppBatchDelivery) e record_counts
# ---------------------------------------------------------------------------


def _ler_resultados_lote(
    batch_result_file: Path, on_warn: Callable[[str], None] | None
) -> list[object]:
    """Itens de ``batch_result.json``. Ilegivel vira aviso e lista vazia, como no PS."""
    if not batch_result_file.exists():
        return []
    try:
        bruto = batch_result_file.read_text(encoding="utf-8-sig", errors="replace")
        if not bruto.strip():
            return []
        dados = _ler_json(bruto)
    except (OSError, ValueError) as exc:
        if on_warn is not None:
            on_warn(f"Falha ao ler batch_result.json para reconciliacao: {exc}")
        return []
    return _como_lista(dados)


def _chaves_com_sucesso(resultados: Sequence[object]) -> set[str]:
    """Chaves de fase (sem caixa) com ``success`` verdadeiro no resultado do lote."""
    chaves: set[str] = set()
    for item in resultados:
        chave = _texto(_prop(item, "phase_key"))
        if chave.strip() and _eh_verdadeiro(_prop(item, "success")):
            chaves.add(chave.casefold())
    return chaves


def _obs_entregues(enviadas: Sequence[CardPagina]) -> set[str]:
    """OBs das paginas enviadas, sem diferenciar caixa (a tabela do PS era case-insensitive)."""
    return {ob.casefold() for card in enviadas for ob in card.ob_ids if ob.strip()}


def _obs_falhas(falhas: Sequence[CardPagina], entregues: set[str]) -> list[str]:
    """OBs das paginas sem sucesso que nenhuma pagina enviada entregou.

    Como no PS, um id repetido em duas paginas falhas aparece duas vezes.
    """
    return [
        ob
        for card in falhas
        for ob in card.ob_ids
        if ob.strip() and ob.casefold() not in entregues
    ]


def _retirar_obs_do_state(state_tmp: Path, obs: Sequence[str]) -> None:
    """Tira do ``notified`` do ``.tmp`` as OBs com falha e regrava o arquivo.

    Arquivo ausente nao faz nada. Arquivo ilegivel levanta excecao (o PS tambem
    interrompia aqui), para nao commitar um state corrompido.
    """
    if not state_tmp.exists():
        return
    estado: object = json.loads(
        state_tmp.read_text(encoding="utf-8-sig", errors="replace"), strict=False
    )
    notified = _prop(estado, "notified")
    if isinstance(notified, dict):
        for ob in obs:
            chave = _chave_real(notified, ob)
            if chave is not None:
                del notified[chave]
    _gravar_utf8(state_tmp, json.dumps(estado, ensure_ascii=False, indent=4))


def resolve_whatsapp_batch_delivery(
    cards: Sequence[CardPagina],
    batch_result_file: Path,
    state_tmp_path: Path,
    *,
    wa_exit_code: int,
    on_warn: Callable[[str], None] | None = None,
) -> EntregaWhatsApp:
    """Reconcilia ``batch_result.json`` com o lote enviado (Resolve-WhatsAppBatchDelivery).

    Pagina enviada e a que tem ``success`` verdadeiro no resultado. Com exit 0 e nenhuma
    pagina falha, o status e ``AllSent``. Sem pagina enviada, ``NoneSent`` e o state nao
    deve ser commitado. Com parte enviada, ``PartialSent``: as OBs das paginas falhas saem
    do ``notified`` do ``.tmp``, que segue para commit.
    """
    resultados = _ler_resultados_lote(batch_result_file, on_warn)
    sucesso = _chaves_com_sucesso(resultados)
    enviadas = [card for card in cards if card.phase_key.casefold() in sucesso]
    falhas = [card for card in cards if card.phase_key.casefold() not in sucesso]
    entregues = _obs_entregues(enviadas)
    total = len(cards)
    if wa_exit_code == 0 and not falhas:
        return EntregaWhatsApp("AllSent", len(enviadas), total, len(entregues), 0, True)
    obs_falhas = _obs_falhas(falhas, entregues)
    if not enviadas:
        return EntregaWhatsApp("NoneSent", 0, total, 0, len(obs_falhas), False)
    _retirar_obs_do_state(state_tmp_path, obs_falhas)
    return EntregaWhatsApp(
        "PartialSent",
        len(enviadas),
        total,
        len(entregues),
        len(obs_falhas),
        True,
    )


def update_whatsapp_result_record_counts(
    result_path: Path,
    delivered_ob_count: int,
    sent_pages: int,
    total_pages: int,
) -> None:
    """Atualiza ``record_counts`` de ``*_result.json`` apos envio parcial (UTF-8 sem BOM).

    Sem o arquivo, sem conteudo ou sem o bloco ``record_counts``, nada e alterado.
    Quando existe a chave ``sent``, ela recebe as OBs entregues, como no PS.
    """
    if not result_path.exists():
        return
    bruto = result_path.read_text(encoding="utf-8-sig", errors="replace")
    if not bruto.strip():
        return
    resultado: object = json.loads(bruto, strict=False)
    contagens = _prop(resultado, "record_counts")
    if not isinstance(contagens, dict):
        return
    _definir(contagens, "notified", delivered_ob_count)
    if _chave_real(contagens, "sent") is not None:
        _definir(contagens, "sent", delivered_ob_count)
    _definir(contagens, "pages_sent", sent_pages)
    _definir(contagens, "pages_total", total_pages)
    _gravar_utf8(result_path, json.dumps(resultado, ensure_ascii=False, indent=4))


# ---------------------------------------------------------------------------
# Configuracao e sessao (Lib-Config.psm1 e Lib-Process.psm1)
# ---------------------------------------------------------------------------


def _secao_habilitada(secao: object) -> bool:
    """Flag ``enabled`` de uma secao (Test-WhatsAppFlagEnabled). Ausente vale True.

    bool vale por si; numero (Int, Double ou Decimal) desabilita quando e zero. O resto passa
    pelo [string] do PS, com Trim e minusculas, e desabilita em 'false', '0' ou 'no'.
    """
    valor = _prop(secao, "enabled")
    if valor is None:
        return True
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float, Decimal)):
        return valor != 0
    return _texto(valor).strip().lower() not in _VALORES_DESLIGADOS


def whatsapp_config_enabled(config: object) -> bool:
    """Test-WhatsAppConfigEnabled: False quando ``app`` ou ``target`` desabilitam o envio.

    Config ausente, secao ausente ou flag ausente valem habilitado. Desabilitam: false,
    0, no (sem diferenciar caixa e com espacos ignorados) e o numero 0.
    """
    return _secao_habilitada(_prop(config, "app")) and _secao_habilitada(
        _prop(config, "target")
    )


def _absolutizar(candidato: str, cwd: str) -> str:
    """Normalizacao lexica de Get-WhatsAppAuthPath: '.' some e '..' sobe um nivel."""
    if not _e_raiz(candidato):
        candidato = f"{cwd}\\{candidato}"
    segmentos: list[str] = []
    for parte in re.split(r"[\\/]+", candidato):
        if parte in (".", ""):
            continue
        if parte == ".." and len(segmentos) > 1:
            segmentos.pop()
            continue
        segmentos.append(parte)
    prefixo = "\\\\" if re.match(r"^[\\/]{2}", candidato) else ""
    return prefixo + "\\".join(segmentos)


def get_whatsapp_auth_path() -> str:
    """Pasta da sessao autenticada do WhatsApp (Get-WhatsAppAuthPath), fora do repositorio.

    Ordem: ``WHATSAPP_AUTH_PATH`` (relativo resolve pelo diretorio corrente); senao
    ``LOCALAPPDATA``, ``HOME`` ou o diretorio corrente, seguido de ``Automacoes\\wwebjs_auth``.
    A normalizacao e lexica, sem GetFullPath, como no PowerShell e no Node.
    """
    cwd = os.getcwd()
    override = os.environ.get("WHATSAPP_AUTH_PATH", "").strip()
    if override:
        return _absolutizar(override, cwd)
    base = os.environ.get("LOCALAPPDATA", "")
    if not base.strip():
        base = os.environ.get("HOME", "")
    if not base.strip():
        base = cwd
    return _absolutizar(_juntar(base, "Automacoes\\wwebjs_auth"), cwd)


def read_whatsapp_config(caminho: Path) -> dict[str, Any]:
    """Le ``whatsapp-config.json`` (tolera BOM) e exige objeto JSON na raiz."""
    dados: object = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(dados, dict):
        raise ValueError(f"{caminho.name} invalido: a raiz nao e um objeto JSON.")
    return dados


def resolve_whatsapp_target(alvo: object, origem: Path) -> str:
    """Destino real (Resolve-WhatsAppTarget): ``contactIdEnv`` vence; ``contactId`` e placeholder."""
    trecho = f" ({origem})"
    if not isinstance(alvo, dict):
        raise ValueError(
            f"Destino do WhatsApp ausente: 'target' nao e um objeto em {origem}."
        )
    env_bruto = alvo.get("contactIdEnv")
    nome_env = env_bruto.strip() if isinstance(env_bruto, str) else ""
    if nome_env:
        destino = os.environ.get(nome_env, "")
        if not destino.strip():
            raise ValueError(
                f"Destino do WhatsApp ausente: variavel de ambiente '{nome_env}'{trecho} "
                "nao esta definida ou esta vazia. O contactId do config e apenas "
                "placeholder de schema, nunca um destino real."
            )
        return destino
    placeholder = _texto(alvo.get("contactId")) or _texto(alvo.get("contactPhone"))
    if not placeholder.strip():
        raise ValueError(
            f"Destino do WhatsApp ausente: 'target'{trecho} nao declara contactId, "
            "contactPhone nem contactIdEnv."
        )
    return placeholder


# ---------------------------------------------------------------------------
# Encaminhamento de linhas e envio pelo Send-WhatsApp.ps1
# ---------------------------------------------------------------------------


def _nivel_da_linha(linha: str, padrao: str) -> str:
    """Delega para ``hub_runner._nivel_da_linha`` (mantido como ponte para testes)."""
    # pylint: disable=protected-access
    return hr._nivel_da_linha(linha, padrao)


def _encaminhar(
    ctx: hr.HubRunContext, linha: str, nivel_padrao: str, step: str
) -> None:
    """Encaminha uma linha do Send-WhatsApp.ps1 via ``hub_runner.forward_line``."""
    hr.forward_line(ctx, linha, nivel_padrao, step)


def _leitor_fluxo(
    fluxo: IO[str], nivel_padrao: str, encaminhar: EncaminharLinha
) -> threading.Thread:
    """Le um fluxo do filho linha a linha, em thread daemon, sem bloquear o pipe."""

    def ler() -> None:
        for linha in fluxo:
            encaminhar(linha.rstrip("\r\n"), nivel_padrao)

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    return leitor


def executar_send_whatsapp(
    comando: ComandoWhatsApp, encaminhar: EncaminharLinha
) -> int:
    """Executor de producao: roda o comando em powershell.exe e devolve o exit code.

    stdout vai ao ``encaminhar`` como INFO e stderr como WARN, cada um em uma thread, para
    o pipe nunca travar. A entrada e fechada (DEVNULL), como no Invoke-NativeProcess.
    """
    with subprocess.Popen(
        list(comando.argv),
        cwd=comando.work_dir,
        env=dict(comando.ambiente),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    ) as processo:
        leitores: list[threading.Thread] = []
        if processo.stdout is not None:
            leitores.append(_leitor_fluxo(processo.stdout, "INFO", encaminhar))
        if processo.stderr is not None:
            leitores.append(_leitor_fluxo(processo.stderr, "WARN", encaminhar))
        processo.wait()
        for leitor in leitores:
            leitor.join()
        return int(processo.returncode)


def _opcional(valor: Path | None) -> str | None:
    """Caminho como texto, ou None quando o argumento nao foi informado."""
    return None if valor is None else str(valor)


def send_whatsapp(  # pylint: disable=too-many-arguments,too-many-locals
    ctx: hr.HubRunContext,
    *,
    script: Path,
    work_dir: Path,
    mode: str = "AUTO",
    config_path: Path | None = None,
    client_id: str | None = None,
    phone: str | None = None,
    batch_input_file: Path | None = None,
    batch_result_file: Path | None = None,
    step: str = "dispatch",
    executor: ExecutorWhatsApp = executar_send_whatsapp,
) -> int:
    """Aciona o ``Send-WhatsApp.ps1`` e devolve o exit code (0, 21, 22, 23, 24...).

    Os argumentos espelham os parametros do script; os nao informados ficam de fora e o
    PowerShell usa o padrao dele. ``-ExecId`` e ``-LogFile`` (o .jsonl da execucao) sempre
    vao. ``work_dir`` e a pasta de trabalho do filho, e ``step`` marca o log encaminhado.
    Os parametros sao nomeados e nao um objeto, por contrato com o script: o mesmo motivo
    de ``hub_runner.retry_attempt``.
    """
    opcoes: tuple[tuple[str, str | None], ...] = (
        ("-ExecId", ctx.exec_id),
        ("-Mode", mode),
        ("-ClientId", client_id),
        ("-Phone", phone),
        ("-ConfigPath", _opcional(config_path)),
        ("-BatchInputFile", _opcional(batch_input_file)),
        ("-BatchResultFile", _opcional(batch_result_file)),
        ("-LogFile", str(ctx.log_path)),
    )
    argv = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    for nome, valor in opcoes:
        if valor is not None:
            argv.extend((nome, valor))
    comando = ComandoWhatsApp(
        argv=tuple(argv),
        work_dir=work_dir,
        ambiente={
            **os.environ,
            **ctx.ambiente(),
            "HUB_LOG_STRUCTURED": "1",
            "HUB_STEP": step,
        },
    )

    def encaminhar(linha: str, nivel_padrao: str) -> None:
        _encaminhar(ctx, linha, nivel_padrao, step)

    return executor(comando, encaminhar)

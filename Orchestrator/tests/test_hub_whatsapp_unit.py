"""Testes unitarios de lib/python/hub_whatsapp.py.

Sem WhatsApp, sem rede e sem Send-WhatsApp.ps1 de verdade: o envio usa um executor duble.
Os testes de paridade comparam com a saida congelada das antigas funcoes de lote do
lib/Lib-WhatsAppBatch.psm1 no Windows PowerShell 5.1 (fixtures/). Tudo fica em
tmp_path; nada e gravado em Logs/ nem dentro de lib/.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

import hub_runner as hr
import hub_whatsapp as hw
import pytest

# Dubles de teste sao deliberadamente minimos (um metodo cada).
# pylint: disable=too-few-public-methods

BOM_UTF8: Final[bytes] = b"\xef\xbb\xbf"


# ---------------------------------------------------------------------------
# Fixtures e dubles
# ---------------------------------------------------------------------------


def _arquivo(caminho: Path, conteudo: bytes = b"imagem") -> Path:
    """Cria um arquivo com conteudo (imagem ou saida qualquer) e devolve o caminho."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


def _card(
    phase_key: str,
    image: str = "cards/a.png",
    caption: str = "Legenda",
    ob_ids: list[object] | None = None,
) -> dict[str, object]:
    """Entrada de cards_manifest.json no formato do format_message.py."""
    return {
        "phase_key": phase_key,
        "image_path": image,
        "caption": caption,
        "ob_ids": ["OB1"] if ob_ids is None else ob_ids,
    }


def _montar_base(base: Path) -> None:
    """Pasta de automacao com as duas imagens, message.txt e card.png nao vazios."""
    _arquivo(base / "cards" / "a.png")
    _arquivo(base / "cards" / "b.png")
    _arquivo(base / "message.txt", b"mensagem")
    _arquivo(base / "card.png", b"png")


def _manifesto(base: Path, cards: object) -> Path:
    """Grava cards_manifest.json em ``base`` a partir de objetos Python."""
    caminho = base / "cards_manifest.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    return caminho


def _manifesto_bruto(base: Path, texto: str) -> Path:
    """Grava cards_manifest.json com o texto exato, para preservar a grafia dos numeros."""
    caminho = base / "cards_manifest.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(texto.encode("utf-8"))
    return caminho


def _manifesto_com_ob_ids(base: Path, ob_ids_json: str) -> Path:
    """Manifesto de um card cujo ``ob_ids`` e o trecho JSON dado, sem alterar a grafia."""
    texto = (
        '[{"phase_key":"FASE-A","image_path":"cards/a.png","caption":"c","ob_ids":['
        + ob_ids_json
        + "]}]"
    )
    return _manifesto_bruto(base, texto)


def _contexto(tmp_path: Path) -> hr.HubRunContext:
    """Contexto de execucao com exec_id fixo e log dentro de tmp_path (sem telemetria)."""
    return hr.create_run_context(
        hr.AutomationSpec(
            automacao="Teste WhatsApp",
            slug="teste_whatsapp",
            trace_slug="tw",
            log_dir=tmp_path / "Logs",
        ),
        exec_id="EXEC_TESTE",
        project_root=tmp_path,
    )


@dataclass
class _ExecutorFalso:
    """Executor duble: registra o comando, emite as linhas dadas e devolve o codigo."""

    codigo: int = 0
    linhas: list[tuple[str, str]] = field(default_factory=list)
    comandos: list[hw.ComandoWhatsApp] = field(default_factory=list)

    def __call__(
        self, comando: hw.ComandoWhatsApp, encaminhar: hw.EncaminharLinha
    ) -> int:
        self.comandos.append(comando)
        for linha, nivel in self.linhas:
            encaminhar(linha, nivel)
        return self.codigo


def _cards_ab() -> tuple[hw.CardPagina, hw.CardPagina]:
    """Duas paginas: FASE-A com OB1/OB2 e FASE-B com OB3/OB4."""
    return (
        hw.CardPagina("FASE-A", "cards/a.png", "A", ("OB1", "OB2")),
        hw.CardPagina("FASE-B", "cards/b.png", "B", ("OB3", "OB4")),
    )


# ---------------------------------------------------------------------------
# read_cards_manifest: casos de borda do Read-CardsManifest
# ---------------------------------------------------------------------------


def test_manifesto_ausente(tmp_path: Path) -> None:
    resultado = hw.read_cards_manifest(tmp_path / "nao_existe.json", tmp_path)
    assert (resultado.valid, resultado.error, resultado.cards) == (
        False,
        "cards_manifest.json nao encontrado.",
        (),
    )


@pytest.mark.parametrize(
    ("texto", "mensagem"),
    [
        ("   \n", "cards_manifest.json vazio."),
        ("[]", "cards_manifest.json sem paginas."),
        ("null", "cards_manifest.json sem paginas."),
    ],
)
def test_manifesto_vazio_ou_sem_paginas(
    tmp_path: Path, texto: str, mensagem: str
) -> None:
    caminho = tmp_path / "cards_manifest.json"
    caminho.write_text(texto, encoding="utf-8")
    resultado = hw.read_cards_manifest(caminho, tmp_path)
    assert (resultado.valid, resultado.error) == (False, mensagem)


def test_manifesto_json_invalido(tmp_path: Path) -> None:
    caminho = tmp_path / "cards_manifest.json"
    caminho.write_text("{nao e json", encoding="utf-8")
    resultado = hw.read_cards_manifest(caminho, tmp_path)
    assert resultado.valid is False
    assert resultado.error.startswith("Falha ao ler cards_manifest.json: ")


def test_manifesto_aceita_objeto_unico_como_um_card(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = base / "cards_manifest.json"
    caminho.write_text(json.dumps(_card("FASE-A")), encoding="utf-8")
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.valid is True
    assert [card.phase_key for card in resultado.cards] == ["FASE-A"]


@pytest.mark.parametrize("campo", ["phase_key", "image_path", "caption"])
def test_campo_obrigatorio_em_branco(tmp_path: Path, campo: str) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    card = _card("FASE-A")
    card[campo] = "   "
    caminho = _manifesto(base, [card])
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.error == (
        "Entrada invalida em cards_manifest.json (phase_key/image_path/caption)."
    )


def test_imagem_ausente(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto(base, [_card("FASE-A", "cards/nao_existe.png")])
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.error == "Imagem do card ausente ou vazia: cards/nao_existe.png"


def test_imagem_vazia_conta_como_ausente(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    _arquivo(base / "cards" / "vazia.png", b"")
    caminho = _manifesto(base, [_card("FASE-A", "cards/vazia.png")])
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.error == "Imagem do card ausente ou vazia: cards/vazia.png"


def test_phase_key_duplicado_sem_diferenciar_caixa(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto(base, [_card("FASE-A"), _card("fase-a")])
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.error == "phase_key duplicado em cards_manifest.json: fase-a"


@pytest.mark.parametrize(
    ("ob_ids", "trecho"),
    [
        (None, "ob_ids ausente ou invalido"),
        ("OB1", "ob_ids ausente ou invalido"),
        ({"a": 1}, "ob_ids ausente ou invalido"),
        (7, "ob_ids ausente ou invalido"),
        ([], "ob_ids vazio"),
        (["OB1", " "], "ob_ids contem ID vazio"),
    ],
)
def test_ob_ids_invalidos(tmp_path: Path, ob_ids: object, trecho: str) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    card: dict[str, object] = {
        "phase_key": "A",
        "image_path": str(base / "cards" / "a.png"),
        "caption": "c",
    }
    if ob_ids is not None:
        card["ob_ids"] = ob_ids
    caminho = _manifesto(base, [card])
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.valid is False
    assert trecho in resultado.error
    assert "'A'" in resultado.error


def test_ob_ids_numericos_viram_texto_e_caminho_relativo_resolve(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto(base, [_card("FASE-A", ob_ids=[123, "OB2"])])
    resultado = hw.read_cards_manifest(caminho, base)
    assert resultado.valid is True
    assert resultado.cards[0].ob_ids == ("123", "OB2")
    assert resultado.cards[0].image_path == "cards/a.png"


# Numeros do JSON medidos no ConvertFrom-Json + [string] do PowerShell 5.1 (probe em
# 18/11/2026). Cada par e (grafia no JSON, texto que o PS produz). A mesma tabela alimenta os
# testes de paridade, que executam Lib-WhatsAppBatch.psm1 de verdade.
TABELA_NUMEROS: Final[list[tuple[str, str]]] = [
    ("1.50", "1.50"),
    ("1.0", "1.0"),
    ("-0.0", "0.0"),
    ("-0", "0"),
    ("123", "123"),
    ("1e5", "100000"),
    ("1E+2", "100"),
    ("1.5e3", "1500"),
    ("2.5E-3", "0.0025"),
    ("0.1", "0.1"),
    ("3000000000", "3000000000"),
    ("9223372036854775808", "9223372036854775808"),
    ("12345678901234567890", "12345678901234567890"),
    ("1.23456789012345678901234567890", "1.2345678901234567890123456789"),
    ("1.7976931348623157E+308", "1.79769313486232E+308"),
    ("100000000000000000000.5", "100000000000000000000.5"),
    ("-12.340", "-12.340"),
    ("5e-7", "5E-07"),
    ("79228162514264337593543950335", "79228162514264337593543950335"),
    ("79228162514264337593543950336", "7.92281625142643E+28"),
    ("1000000000000000000000000000000", "1E+30"),
    ("100000000000000000000000000000.5", "1E+29"),
    ("1.00000000000000000000000000005", "1.0000000000000000000000000000"),
    ("0.0000001", "0.0000001"),
    ("-0e0", "0"),
    ("1e15", "1E+15"),
    ("1e14", "100000000000000"),
    ("1e-5", "1E-05"),
    ("1.5e-5", "1.5E-05"),
    ("123456789.123456789e3", "123456789123.457"),
    ("NaN", "NaN"),
    ("Infinity", "Infinity"),
    ("-Infinity", "-Infinity"),
]
# Listas e objetos como ob_ids: o [string] de lista junta com espaco; objeto vira @{...}.
TABELA_OBJETOS: Final[list[tuple[str, str]]] = [
    ('[1,"a"]', "1 a"),
    ('{"a":1}', "@{a=1}"),
    ('[{"a":1},2]', " 2"),
    ('{"a":null,"b":[]}', "@{a=; b=System.Object[]}"),
    ("[1,[2,3],null,true]", "1 System.Object[]  True"),
    ("[[]]", "System.Object[]"),
]
PREFIXO_FALHA_LEITURA: Final[str] = "Falha ao ler cards_manifest.json: "


@pytest.mark.parametrize(
    ("literal", "esperado"),
    TABELA_NUMEROS,
    ids=[literal for literal, _ in TABELA_NUMEROS],
)
def test_numero_json_vira_texto_como_o_ps(
    tmp_path: Path, literal: str, esperado: str
) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    resultado = hw.read_cards_manifest(_manifesto_com_ob_ids(base, literal), base)
    assert resultado.valid is True
    assert resultado.cards[0].ob_ids == (esperado,)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    TABELA_OBJETOS,
    ids=[valor for valor, _ in TABELA_OBJETOS],
)
def test_lista_e_objeto_viram_texto_como_o_ps(
    tmp_path: Path, valor: str, esperado: str
) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    resultado = hw.read_cards_manifest(_manifesto_com_ob_ids(base, valor), base)
    assert resultado.valid is True
    assert resultado.cards[0].ob_ids == (esperado,)


def test_phase_key_numerico_mantem_a_escala(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    texto = (
        '[{"phase_key":1.50,"image_path":"cards/a.png","caption":"c","ob_ids":["OB1"]}]'
    )
    resultado = hw.read_cards_manifest(_manifesto_bruto(base, texto), base)
    assert resultado.valid is True
    assert resultado.cards[0].phase_key == "1.50"


@pytest.mark.parametrize(
    "ob_ids",
    ["1e400", "-NaN"],
    ids=["estouro_double", "nan_negativo"],
)
def test_json_que_o_ps_recusa_vira_erro_de_leitura(tmp_path: Path, ob_ids: str) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    resultado = hw.read_cards_manifest(_manifesto_com_ob_ids(base, ob_ids), base)
    assert resultado.valid is False
    assert resultado.error.startswith(PREFIXO_FALHA_LEITURA)
    assert len(resultado.error) > len(PREFIXO_FALHA_LEITURA)


def test_layout_do_batch_input_e_escapes_como_o_ps(tmp_path: Path) -> None:
    """Bytes iguais aos que o ConvertTo-Json do PS 5.1 grava para esta legenda."""
    legenda = "a\"b\\c<&>'\t\x01é"
    cards = (hw.CardPagina("FASE-1", "cards/a.png", legenda, ("OB1",)),)
    destino = tmp_path / "batch_input.json"
    hw.write_whatsapp_batch_input(cards, Path("C:\\base"), destino)
    esperado = (
        "[\r\n"
        "    {\r\n"
        '        "caption":  "a\\"b\\\\c\\u003c\\u0026\\u003e\\u0027\\t\\u0001é",\r\n'
        '        "image_path":  "C:\\\\base\\\\cards\\\\a.png",\r\n'
        '        "phase_key":  "FASE-1"\r\n'
        "    }\r\n"
        "]"
    )
    assert destino.read_bytes() == esperado.encode("utf-8")


def test_write_batch_input_lista_vazia_e_erro(tmp_path: Path) -> None:
    """O PS recusa -Cards vazio (parametro obrigatorio) e nao grava arquivo."""
    destino = tmp_path / "batch_input.json"
    with pytest.raises(ValueError, match="coleção vazia"):
        hw.write_whatsapp_batch_input((), tmp_path, destino)
    assert not destino.exists()


def test_lote_nao_checa_message_e_card(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto(base, [_card("FASE-A"), _card("FASE-B", "cards/b.png")])
    resultado = hw.read_cards_manifest(
        caminho,
        base,
        message_file=str(tmp_path / "nao_existe.txt"),
        card_file=str(tmp_path / "nao_existe.png"),
    )
    assert resultado.valid is True


def test_card_unico_exige_message_e_card_com_conteudo(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto(base, [_card("FASE-A")])
    mensagem = _arquivo(tmp_path / "message.txt", b"")
    cartao = tmp_path / "card.png"

    vazio = hw.read_cards_manifest(
        caminho, base, message_file=str(mensagem), card_file=str(cartao)
    )
    assert vazio.error == "message.txt nao foi gerado ou esta vazio."

    _arquivo(mensagem, b"texto")
    sem_cartao = hw.read_cards_manifest(
        caminho, base, message_file=str(mensagem), card_file=str(cartao)
    )
    assert sem_cartao.error == "card.png nao foi gerado ou esta vazio."

    _arquivo(cartao, b"png")
    completo = hw.read_cards_manifest(
        caminho, base, message_file=str(mensagem), card_file=str(cartao)
    )
    assert completo.valid is True


# ---------------------------------------------------------------------------
# write_whatsapp_batch_input
# ---------------------------------------------------------------------------


def test_write_batch_input_um_card_continua_lista(tmp_path: Path) -> None:
    """Lote de uma pagina e lista JSON, nunca objeto: o motor Node descartava o objeto
    como "Lote vazio" (09/11/2026, `$lote | ConvertTo-Json` no PS)."""
    base = tmp_path / "base"
    destino = tmp_path / "batch_input.json"

    hw.write_whatsapp_batch_input(
        (hw.CardPagina("FASE-1", "cards/a.png", "Unica", ("OB1",)),), base, destino
    )

    itens = json.loads(destino.read_bytes().decode("utf-8"))
    assert isinstance(itens, list)
    assert [item["phase_key"] for item in itens] == ["FASE-1"]


def test_write_batch_input_utf8_sem_bom_e_caminhos_absolutos(tmp_path: Path) -> None:
    base = tmp_path / "base"
    absoluta = _arquivo(base / "cards" / "abs.png")
    cards = (
        hw.CardPagina("FASE-1", "cards/a.png", "Acentuação & <tags>", ("OB1",)),
        hw.CardPagina("FASE-2", str(absoluta), "Segunda", ("OB2",)),
    )
    destino = tmp_path / "batch_input.json"

    hw.write_whatsapp_batch_input(cards, base, destino)

    bruto = destino.read_bytes()
    assert not bruto.startswith(BOM_UTF8)
    itens = json.loads(bruto.decode("utf-8"))
    base_win = str(base).replace("/", "\\")
    assert itens == [
        {
            "phase_key": "FASE-1",
            "image_path": f"{base_win}\\cards\\a.png",
            "caption": "Acentuação & <tags>",
        },
        {"phase_key": "FASE-2", "image_path": str(absoluta), "caption": "Segunda"},
    ]


# ---------------------------------------------------------------------------
# resolve_whatsapp_batch_delivery: AllSent, PartialSent e NoneSent
# ---------------------------------------------------------------------------


def _lote(tmp_path: Path, resultados: object | None) -> Path:
    """Grava batch_result.json (ou nao grava quando ``resultados`` e None)."""
    caminho = tmp_path / "batch_result.json"
    if resultados is not None:
        caminho.write_text(json.dumps(resultados), encoding="utf-8")
    return caminho


def _estado(tmp_path: Path) -> Path:
    """State .tmp com notified para as quatro OBs e um last_hash."""
    caminho = tmp_path / "estado.json.tmp"
    estado = {
        "last_hash": "h1",
        "notified": {"OB1": "ok", "OB2": "ok", "OB3": "ok", "OB4": "ok"},
    }
    caminho.write_text(json.dumps(estado), encoding="utf-8")
    return caminho


def test_resolve_todos_enviados(tmp_path: Path) -> None:
    cards = _cards_ab()
    lote = _lote(
        tmp_path,
        [
            {"phase_key": "FASE-A", "success": True},
            {"phase_key": "FASE-B", "success": True},
        ],
    )
    estado = _estado(tmp_path)
    antes = estado.read_bytes()

    entrega = hw.resolve_whatsapp_batch_delivery(cards, lote, estado, wa_exit_code=0)

    assert entrega == hw.EntregaWhatsApp("AllSent", 2, 2, 4, 0, True)
    assert estado.read_bytes() == antes


def test_resolve_parcial_retira_obs_pendentes_do_state(tmp_path: Path) -> None:
    cards = _cards_ab()
    lote = _lote(
        tmp_path,
        [
            {"phase_key": "FASE-A", "success": True},
            {"phase_key": "FASE-B", "success": False},
        ],
    )
    estado = _estado(tmp_path)

    entrega = hw.resolve_whatsapp_batch_delivery(cards, lote, estado, wa_exit_code=24)

    assert entrega == hw.EntregaWhatsApp("PartialSent", 1, 2, 2, 2, True)
    gravado = json.loads(estado.read_text(encoding="utf-8"))
    assert gravado["notified"] == {"OB1": "ok", "OB2": "ok"}
    assert gravado["last_hash"] == "h1"


def test_resolve_nenhum_enviado(tmp_path: Path) -> None:
    cards = _cards_ab()
    lote = _lote(
        tmp_path,
        [
            {"phase_key": "FASE-A", "success": False},
            {"phase_key": "FASE-B", "success": False},
        ],
    )
    estado = _estado(tmp_path)
    antes = estado.read_bytes()

    entrega = hw.resolve_whatsapp_batch_delivery(cards, lote, estado, wa_exit_code=24)

    assert entrega == hw.EntregaWhatsApp("NoneSent", 0, 2, 0, 4, False)
    assert estado.read_bytes() == antes


def test_resolve_sem_arquivo_de_lote_e_nenhum_enviado(tmp_path: Path) -> None:
    entrega = hw.resolve_whatsapp_batch_delivery(
        _cards_ab(),
        tmp_path / "batch_result.json",
        tmp_path / "estado.json.tmp",
        wa_exit_code=24,
    )
    assert entrega == hw.EntregaWhatsApp("NoneSent", 0, 2, 0, 4, False)


def test_resolve_exit_zero_com_pagina_falha_e_parcial(tmp_path: Path) -> None:
    lote = _lote(
        tmp_path,
        [
            {"phase_key": "FASE-A", "success": True},
            {"phase_key": "FASE-B", "success": False},
        ],
    )
    entrega = hw.resolve_whatsapp_batch_delivery(
        _cards_ab(), lote, tmp_path / "x.tmp", wa_exit_code=0
    )
    assert entrega.status == "PartialSent"
    assert entrega.failed_ob_count == 2


def test_resolve_success_aceita_true_texto_e_numero_um(tmp_path: Path) -> None:
    """Como no PS, 'TRUE' (texto) e 1 (numero) contam como sucesso."""
    lote = _lote(
        tmp_path,
        [
            {"phase_key": "FASE-A", "success": "TRUE"},
            {"phase_key": "fase-b", "success": 1},
        ],
    )
    entrega = hw.resolve_whatsapp_batch_delivery(
        _cards_ab(), lote, tmp_path / "x.tmp", wa_exit_code=0
    )
    assert entrega == hw.EntregaWhatsApp("AllSent", 2, 2, 4, 0, True)


def test_resolve_ob_repetida_em_paginas_falhas_conta_duas_vezes(
    tmp_path: Path,
) -> None:
    """FailedObCount do PS e a contagem de uma lista: id repetido conta de novo."""
    cards = (
        hw.CardPagina("FASE-A", "cards/a.png", "A", ("OB9",)),
        hw.CardPagina("FASE-B", "cards/b.png", "B", ("OB9",)),
        hw.CardPagina("FASE-C", "cards/b.png", "C", ("OB5",)),
    )
    lote = _lote(tmp_path, [{"phase_key": "FASE-C", "success": True}])
    entrega = hw.resolve_whatsapp_batch_delivery(
        cards, lote, tmp_path / "x.tmp", wa_exit_code=24
    )
    assert entrega == hw.EntregaWhatsApp("PartialSent", 1, 3, 1, 2, True)


def test_resolve_lote_ilegivel_avisa_e_trata_como_vazio(tmp_path: Path) -> None:
    lote = tmp_path / "batch_result.json"
    lote.write_text("{quebrado", encoding="utf-8")
    avisos: list[str] = []

    entrega = hw.resolve_whatsapp_batch_delivery(
        _cards_ab(),
        lote,
        tmp_path / "x.tmp",
        wa_exit_code=24,
        on_warn=avisos.append,
    )

    assert entrega.status == "NoneSent"
    assert len(avisos) == 1
    assert avisos[0].startswith("Falha ao ler batch_result.json para reconciliacao: ")


def test_resolve_parcial_sem_state_tmp_nao_cria_arquivo(tmp_path: Path) -> None:
    lote = _lote(
        tmp_path,
        [
            {"phase_key": "FASE-A", "success": True},
            {"phase_key": "FASE-B", "success": False},
        ],
    )
    state = tmp_path / "ausente.json.tmp"
    entrega = hw.resolve_whatsapp_batch_delivery(
        _cards_ab(), lote, state, wa_exit_code=24
    )
    assert entrega.status == "PartialSent"
    assert not state.exists()


# ---------------------------------------------------------------------------
# update_whatsapp_result_record_counts
# ---------------------------------------------------------------------------


def test_update_record_counts_grava_contagens_parciais(tmp_path: Path) -> None:
    resultado = tmp_path / "receitas_result.json"
    resultado.write_text(
        json.dumps(
            {
                "status": "ok",
                "record_counts": {"sent": 5, "total": 9, "notified": 0},
            }
        ),
        encoding="utf-8",
    )

    hw.update_whatsapp_result_record_counts(
        resultado, delivered_ob_count=2, sent_pages=1, total_pages=2
    )

    bruto = resultado.read_bytes()
    assert not bruto.startswith(BOM_UTF8)
    dados = json.loads(bruto.decode("utf-8"))
    assert dados["status"] == "ok"
    assert dados["record_counts"] == {
        "sent": 2,
        "total": 9,
        "notified": 2,
        "pages_sent": 1,
        "pages_total": 2,
    }


def test_update_record_counts_sem_bloco_nao_altera(tmp_path: Path) -> None:
    resultado = tmp_path / "x_result.json"
    original = json.dumps({"outro": 1})
    resultado.write_text(original, encoding="utf-8")
    hw.update_whatsapp_result_record_counts(
        resultado, delivered_ob_count=1, sent_pages=1, total_pages=1
    )
    assert resultado.read_text(encoding="utf-8") == original


def test_update_record_counts_arquivo_ausente_nao_levanta(tmp_path: Path) -> None:
    hw.update_whatsapp_result_record_counts(
        tmp_path / "nao_existe.json",
        delivered_ob_count=1,
        sent_pages=1,
        total_pages=1,
    )
    assert not (tmp_path / "nao_existe.json").exists()


# ---------------------------------------------------------------------------
# whatsapp_config_enabled e get_whatsapp_auth_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("config", "esperado"),
    [
        (None, True),
        ({}, True),
        ({"app": "texto", "target": 3}, True),
        ({"app": {"enabled": False}}, False),
        ({"app": {"enabled": "no"}}, False),
        ({"app": {"enabled": " False "}}, False),
        ({"target": {"enabled": 0}}, False),
        ({"target": {"enabled": "Yes"}}, True),
        ({"target": {"enabled": None}}, True),
        ({"app": {"enabled": 0.0}}, False),
        ({"app": {"enabled": -0.0}}, False),
        ({"app": {"enabled": 1.50}}, True),
        ({"app": {"enabled": True}, "target": {"enabled": 2}}, True),
    ],
)
def test_whatsapp_config_enabled(config: object, esperado: bool) -> None:
    assert hw.whatsapp_config_enabled(config) is esperado


def test_auth_path_override_absoluto_normaliza(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHATSAPP_AUTH_PATH", "  C:\\dados\\..\\whats\\  ")
    assert hw.get_whatsapp_auth_path() == "C:\\whats"


def test_auth_path_override_relativo_usa_diretorio_corrente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WHATSAPP_AUTH_PATH", "sessao\\..\\perfil")
    resultado = hw.get_whatsapp_auth_path()
    assert resultado.endswith("\\perfil")
    assert ".." not in resultado


def test_auth_path_usa_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHATSAPP_AUTH_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\dev\\AppData\\Local")
    assert hw.get_whatsapp_auth_path() == (
        "C:\\Users\\dev\\AppData\\Local\\Automacoes\\wwebjs_auth"
    )


def test_auth_path_cai_para_home_com_localappdata_em_branco(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WHATSAPP_AUTH_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "   ")
    monkeypatch.setenv("HOME", "C:\\home\\dev")
    assert hw.get_whatsapp_auth_path() == "C:\\home\\dev\\Automacoes\\wwebjs_auth"


def test_auth_path_cai_para_diretorio_corrente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("WHATSAPP_AUTH_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "")
    monkeypatch.setenv("HOME", "")
    monkeypatch.chdir(tmp_path)
    assert hw.get_whatsapp_auth_path().endswith("\\Automacoes\\wwebjs_auth")


# ---------------------------------------------------------------------------
# send_whatsapp com executor duble
# ---------------------------------------------------------------------------


def test_send_whatsapp_monta_argv_encaminha_linhas_e_devolve_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _contexto(tmp_path)
    script = tmp_path / "lib" / "Send-WhatsApp.ps1"
    config = tmp_path / "whatsapp-config.json"
    lote_entrada = tmp_path / "batch_input.json"
    lote_saida = tmp_path / "batch_result.json"
    envelope = json.dumps(
        {
            "ts": "2026-11-18T10:00:00Z",
            "level": "INFO",
            "component": "node",
            "event": "log",
            "automation": "Teste WhatsApp",
            "exec_id": "EXEC_TESTE",
            "trace_id": "tw-1",
            "message": "envelope do motor",
        },
        ensure_ascii=False,
    )
    executor = _ExecutorFalso(
        codigo=22,
        linhas=[
            ("Enviando lote", "INFO"),
            ("", "INFO"),
            ("[WARN] sessao em uso", "WARN"),
            (envelope, "INFO"),
            ("falha do motor", "WARN"),
        ],
    )

    codigo = hw.send_whatsapp(
        ctx,
        script=script,
        work_dir=tmp_path,
        mode="BATCH",
        config_path=config,
        batch_input_file=lote_entrada,
        batch_result_file=lote_saida,
        executor=executor,
    )

    assert codigo == 22
    comando = executor.comandos[0]
    assert comando.argv == (
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ExecId",
        "EXEC_TESTE",
        "-Mode",
        "BATCH",
        "-ConfigPath",
        str(config),
        "-BatchInputFile",
        str(lote_entrada),
        "-BatchResultFile",
        str(lote_saida),
        "-LogFile",
        str(ctx.log_path),
    )
    assert comando.work_dir == tmp_path
    assert comando.ambiente["HUB_EXEC_ID"] == "EXEC_TESTE"
    assert comando.ambiente["HUB_AUTOMATION"] == "Teste WhatsApp"

    eventos = [
        json.loads(linha)
        for linha in ctx.log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [(e["message"], e["level"]) for e in eventos] == [
        ("Enviando lote", "INFO"),
        ("[WARN] sessao em uso", "WARN"),
        ("envelope do motor", "INFO"),
        ("falha do motor", "WARN"),
    ]
    # O envelope vai verbatim (sem step acrescentado); as linhas de texto levam o step.
    assert [e.get("step") for e in eventos if e["component"] == "ps_script"] == [
        "dispatch",
        "dispatch",
        "dispatch",
    ]
    assert envelope in capsys.readouterr().out


def test_send_whatsapp_modo_auto_sem_argumentos_extras(tmp_path: Path) -> None:
    ctx = _contexto(tmp_path)
    script = tmp_path / "Send-WhatsApp.ps1"
    executor = _ExecutorFalso(codigo=0)

    codigo = hw.send_whatsapp(ctx, script=script, work_dir=tmp_path, executor=executor)

    assert codigo == 0
    assert executor.comandos[0].argv == (
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ExecId",
        "EXEC_TESTE",
        "-Mode",
        "AUTO",
        "-LogFile",
        str(ctx.log_path),
    )


def test_send_whatsapp_batch_com_cliente_e_destino(tmp_path: Path) -> None:
    ctx = _contexto(tmp_path)
    executor = _ExecutorFalso(codigo=21)

    codigo = hw.send_whatsapp(
        ctx,
        script=tmp_path / "Send-WhatsApp.ps1",
        work_dir=tmp_path,
        mode="BATCH",
        client_id="hub-global",
        phone="5511999999999",
        batch_input_file=tmp_path / "in.json",
        batch_result_file=tmp_path / "out.json",
        executor=executor,
    )

    assert codigo == 21
    argv = executor.comandos[0].argv
    par = argv.index("-ClientId")
    assert argv[par : par + 4] == ("-ClientId", "hub-global", "-Phone", "5511999999999")
    assert "-ConfigPath" not in argv


def test_executor_real_encaminha_stdout_stderr_e_exit(tmp_path: Path) -> None:
    """Testa o executor de producao com um processo Python qualquer (sem Send-WhatsApp)."""
    codigo_filho = (
        "import sys; print('saida'); print('aviso', file=sys.stderr); sys.exit(7)"
    )
    comando = hw.ComandoWhatsApp(
        argv=(sys.executable, "-c", codigo_filho),
        work_dir=tmp_path,
        ambiente=dict(os.environ),
    )
    recebidas: list[tuple[str, str]] = []

    codigo = hw.executar_send_whatsapp(
        comando, lambda linha, nivel: recebidas.append((linha, nivel))
    )

    assert codigo == 7
    assert sorted(recebidas) == [("aviso", "WARN"), ("saida", "INFO")]


@pytest.mark.parametrize(
    "linha",
    [
        "[WARN] a",
        "[ERROR] b",
        "[ERRO] c",
        "[DEBUG] d",
        "[INFO] e",
        "[warn] f",
        "sem marcador",
    ],
)
def test_nivel_da_linha_igual_ao_do_runner(linha: str) -> None:
    # Compara a regra privada de hub_runner com a reescrita local (mesma saida).
    # pylint: disable=protected-access
    for padrao in ("INFO", "WARN"):
        nivel_nosso = hw._nivel_da_linha(linha, padrao)
        nivel_runner = hr._nivel_da_linha(linha, padrao)
        assert nivel_nosso == nivel_runner


# ---------------------------------------------------------------------------
# Paridade com o antigo lib/Lib-WhatsAppBatch.psm1 (saida congelada do PS 5.1)
# ---------------------------------------------------------------------------
# As funcoes de lote do Lib-WhatsAppBatch.psm1 sairam do repositorio depois que as
# automacoes passaram a usar hub_whatsapp.py. Antes da remocao, a saida real delas no
# Windows PowerShell 5.1 foi gravada em fixtures/lib_whatsappbatch_ps51_paridade.json
# (pasta base normalizada para <BASE>); estes testes travam o Python contra ela.

FIXTURE_PS: Final[Path] = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "lib_whatsappbatch_ps51_paridade.json"
)


def _saida_ps() -> dict[str, Any]:
    """Saida congelada do PowerShell 5.1 para os cenarios de paridade."""
    dados: dict[str, Any] = json.loads(FIXTURE_PS.read_text(encoding="utf-8"))
    return dados


def _batch_input_ps(nome: str, base: Path) -> bytes:
    """Bytes do batch_input.json que o PS gravou, com <BASE> trocado pela pasta do teste."""
    texto: str = _saida_ps()["batch_input"][nome]
    return texto.replace("<BASE>", json.dumps(str(base))[1:-1]).encode("utf-8")


def _resultado_leitura_py(resultado: hw.ResultadoManifesto) -> dict[str, Any]:
    """Mesma forma do JSON que o roteiro PowerShell gravou para Read-CardsManifest."""
    return {
        "valid": resultado.valid,
        "error": resultado.error,
        "cards": [
            {
                "phase_key": card.phase_key,
                "image_path": card.image_path,
                "caption": card.caption,
                "ob_ids": list(card.ob_ids),
            }
            for card in resultado.cards
        ],
    }


_CENARIOS_LEITURA: Final[list[tuple[str, object, bool]]] = [
    (
        "valido_dois_cards",
        [
            _card("FASE-A", "cards/a.png", ob_ids=["OB1"]),
            _card("FASE-B", "cards/b.png", ob_ids=[7, "OB8"]),
        ],
        False,
    ),
    ("card_unico_com_saidas", [_card("FASE-A", "cards/a.png")], True),
    (
        "phase_key_duplicado",
        [_card("FASE-A"), _card("fase-a", "cards/b.png")],
        False,
    ),
    ("ob_ids_vazio", [_card("FASE-A", ob_ids=[])], False),
    ("imagem_ausente", [_card("FASE-A", "cards/nao_existe.png")], False),
]


@pytest.mark.parametrize(
    ("nome", "manifesto", "com_saidas"),
    _CENARIOS_LEITURA,
    ids=[nome for nome, _, _ in _CENARIOS_LEITURA],
)
def test_paridade_read_cards_manifest(
    tmp_path: Path, nome: str, manifesto: object, com_saidas: bool
) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto(base, manifesto)
    mensagem = base / "message.txt" if com_saidas else None
    cartao = base / "card.png" if com_saidas else None

    saida_ps = _saida_ps()["leitura"][nome]
    resultado_py = hw.read_cards_manifest(
        caminho,
        base,
        message_file=str(mensagem) if mensagem else "",
        card_file=str(cartao) if cartao else "",
    )

    assert _resultado_leitura_py(resultado_py) == saida_ps


def test_paridade_write_whatsapp_batch_input(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _montar_base(base)
    manifesto = [
        _card("FASE-A", "cards/a.png", "Acentuação & <tags>", ["OB1", "OB2"]),
        _card("FASE-B", "cards/b.png", "Segunda legenda", ["OB3"]),
    ]
    caminho = _manifesto(base, manifesto)
    entrada_py = base / "batch_input_py.json"

    cards = hw.read_cards_manifest(caminho, base).cards
    hw.write_whatsapp_batch_input(cards, base, entrada_py)

    bruto_py = entrada_py.read_bytes()
    assert not bruto_py.startswith(BOM_UTF8)
    assert bruto_py == _batch_input_ps("dois_cards", base)


_CENARIOS_RESOLUCAO: Final[list[tuple[str, list[dict[str, Any]] | None, int]]] = [
    (
        "todos",
        [
            {"phase_key": "FASE-A", "success": True},
            {"phase_key": "FASE-B", "success": True},
        ],
        0,
    ),
    (
        "parcial",
        [
            {"phase_key": "FASE-A", "success": True},
            {"phase_key": "FASE-B", "success": False},
        ],
        24,
    ),
    (
        "nenhum",
        [
            {"phase_key": "FASE-A", "success": False},
            {"phase_key": "FASE-B", "success": False},
        ],
        24,
    ),
]


@pytest.mark.parametrize(
    ("nome", "resultados", "wa_exit"),
    _CENARIOS_RESOLUCAO,
    ids=[nome for nome, _, _ in _CENARIOS_RESOLUCAO],
)
def test_paridade_resolve_whatsapp_batch_delivery(
    tmp_path: Path, nome: str, resultados: list[dict[str, Any]], wa_exit: int
) -> None:
    manifesto = [
        _card("FASE-A", "cards/a.png", ob_ids=["OB1", "OB2"]),
        _card("FASE-B", "cards/b.png", ob_ids=["OB3", "OB4"]),
    ]
    dados_estado = json.dumps(
        {
            "last_hash": "h1",
            "notified": {"OB1": "ok", "OB2": "ok", "OB3": "ok", "OB4": "ok"},
        }
    )
    _montar_base(tmp_path)
    _manifesto(tmp_path, manifesto)
    (tmp_path / "batch_result.json").write_text(
        json.dumps(resultados), encoding="utf-8"
    )
    (tmp_path / "estado.json.tmp").write_text(dados_estado, encoding="utf-8")

    cards = hw.read_cards_manifest(tmp_path / "cards_manifest.json", tmp_path).cards
    entrega_py = hw.resolve_whatsapp_batch_delivery(
        cards,
        tmp_path / "batch_result.json",
        tmp_path / "estado.json.tmp",
        wa_exit_code=wa_exit,
    )

    esperado = _saida_ps()["resolucao"][nome]
    assert asdict(entrega_py) == esperado["saida"]
    estado_py = json.loads((tmp_path / "estado.json.tmp").read_text(encoding="utf-8"))
    assert estado_py == esperado["estado"]


def test_paridade_numeros_e_objetos_em_ob_ids(tmp_path: Path) -> None:
    """Toda a tabela de numeros, listas e objetos numa so leitura."""
    base = tmp_path / "base"
    _montar_base(base)
    literais = [literal for literal, _ in TABELA_NUMEROS]
    literais += [valor for valor, _ in TABELA_OBJETOS]
    esperados = [esperado for _, esperado in TABELA_NUMEROS]
    esperados += [esperado for _, esperado in TABELA_OBJETOS]
    caminho = _manifesto_com_ob_ids(base, ",".join(literais))

    saida_ps = _saida_ps()["leitura"]["numeros_e_objetos"]
    resultado_py = hw.read_cards_manifest(caminho, base)

    assert _resultado_leitura_py(resultado_py) == saida_ps
    assert resultado_py.cards[0].ob_ids == tuple(esperados)


def test_paridade_bytes_batch_input_com_escapes_e_phase_numerico(
    tmp_path: Path,
) -> None:
    """Bytes do batch_input.json iguais aos do PS: escapes, CRLF e phase_key 1.50."""
    base = tmp_path / "base"
    _montar_base(base)
    legenda = (
        "Acentuação & <tags> 'q' \"d\" \\ tab\t nl\n cr\r bs\b ff\f ctl\x01\x1f"
        " del\x7f nel\x85 ls  ps  ✓ 😀 `~+é/"
    )
    texto = (
        '[{"phase_key":"FASE-A","image_path":"cards/a.png","caption":'
        + json.dumps(legenda, ensure_ascii=False)
        + ',"ob_ids":["OB1"]},{"phase_key":1.50,"image_path":"cards/b.png",'
        '"caption":"Segunda","ob_ids":[1.0,"OB3"]}]'
    )
    caminho = _manifesto_bruto(base, texto)
    entrada_py = base / "batch_input_py.json"

    cards = hw.read_cards_manifest(caminho, base).cards
    hw.write_whatsapp_batch_input(cards, base, entrada_py)

    assert entrada_py.read_bytes() == _batch_input_ps("escapes_e_phase_numerico", base)


_CASOS_RECUSADOS_PELO_PS: Final[list[tuple[str, str]]] = [
    ("sintaxe", "{nao e json"),
    (
        "nan_negativo",
        '[{"phase_key":"A","image_path":"cards/a.png","caption":"c","ob_ids":[-NaN]}]',
    ),
    (
        "estouro",
        '[{"phase_key":"A","image_path":"cards/a.png","caption":"c","ob_ids":[1e400]}]',
    ),
]


@pytest.mark.parametrize(
    "texto",
    [texto for _, texto in _CASOS_RECUSADOS_PELO_PS],
    ids=[nome for nome, _ in _CASOS_RECUSADOS_PELO_PS],
)
def test_paridade_erro_de_parse_mesmo_prefixo(tmp_path: Path, texto: str) -> None:
    """JSON que o PS 5.1 recusava: invalido, com o prefixo de falha e o detalhe do parser."""
    base = tmp_path / "base"
    _montar_base(base)
    caminho = _manifesto_bruto(base, texto)

    resultado_py = hw.read_cards_manifest(caminho, base)

    assert resultado_py.valid is False
    assert resultado_py.error.startswith(PREFIXO_FALHA_LEITURA)
    assert len(resultado_py.error) > len(PREFIXO_FALHA_LEITURA)


def test_paridade_success_com_valores_do_ps(tmp_path: Path) -> None:
    """Quais valores de success contam como enviados: medido no PS (-eq $true)."""
    resultados: list[dict[str, Any]] = [
        {"phase_key": "K1", "success": 1.0},
        {"phase_key": "K2", "success": "true"},
        {"phase_key": "K3", "success": "1"},
        {"phase_key": "K4", "success": [True]},
        {"phase_key": "K5", "success": 1.5},
    ]
    manifesto = [_card(f"K{i}", ob_ids=[f"O{i}"]) for i in range(1, 7)]
    _montar_base(tmp_path)
    _manifesto(tmp_path, manifesto)
    (tmp_path / "batch_result.json").write_text(
        json.dumps(resultados), encoding="utf-8"
    )
    estado = {"last_hash": "h1", "notified": {f"O{i}": "ok" for i in range(1, 7)}}
    (tmp_path / "estado.json.tmp").write_text(json.dumps(estado), encoding="utf-8")

    cards = hw.read_cards_manifest(tmp_path / "cards_manifest.json", tmp_path).cards
    entrega_py = hw.resolve_whatsapp_batch_delivery(
        cards,
        tmp_path / "batch_result.json",
        tmp_path / "estado.json.tmp",
        wa_exit_code=24,
    )

    # Enviadas: K1 (1.0), K2 ("true") e K4 ([true]). K3 ("1"), K5 (1.5) e K6 (sem item) falham.
    esperado = _saida_ps()["resolucao"]["success_valores_do_ps"]
    assert entrega_py.status == "PartialSent"
    assert entrega_py.sent_count == 3
    assert asdict(entrega_py) == esperado["saida"]
    notificados_py = json.loads(
        (tmp_path / "estado.json.tmp").read_text(encoding="utf-8")
    )
    assert notificados_py["notified"] == esperado["estado"]["notified"]


def test_send_whatsapp_injeta_hub_log_structured_e_hub_step_no_ambiente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HUB_LOG_STRUCTURED", raising=False)
    monkeypatch.delenv("HUB_STEP", raising=False)
    ctx = _contexto(tmp_path)
    executor = _ExecutorFalso(codigo=0)
    codigo = hw.send_whatsapp(
        ctx,
        script=tmp_path / "Send-WhatsApp.ps1",
        work_dir=tmp_path,
        step="dispatch",
        executor=executor,
    )
    assert codigo == 0
    env = executor.comandos[0].ambiente
    assert env["HUB_LOG_STRUCTURED"] == "1"
    assert env["HUB_STEP"] == "dispatch"

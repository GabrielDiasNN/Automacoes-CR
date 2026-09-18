"""Bordas do coletor de triagem (`.claude/skills/log-triage/triagem.py`).

Motivação: o coletor foi validado contra a instância real de produção e passou,
mas o conjunto de dados daquele dia era benigno e escondeu quatro defeitos que
só apareceram em code review — todos nas bordas que dados de um dia qualquer não
exercitam:

- ordenação por data só quebra cruzando mês/ano (as falhas eram do mesmo mês);
- paginação só quebra acima de `per_page` (havia 14 falhas, não 201);
- teto de `limit` só quebra com flag fora do default;
- erro parcial de listagem só aparece quando um status falha.

Um quinto defeito (recuperação inferida por ausência de falha) veio da primeira
execução real do agendado. Este arquivo transforma as verificações ad-hoc que
acharam tudo isso em asserções permanentes: o coletor não tem outra cobertura, e
sem ela uma regressão nessas bordas passa pelo CI em silêncio.

O módulo é carregado por caminho (não é pacote instalável) e toda requisição HTTP
é substituída — nenhum teste aqui toca a API real.
"""

# pylint: disable=protected-access
# O coletor e um script standalone invocado por CLI: nao expoe API publica, e o
# que ha para testar sao justamente as funcoes internas de decisao. Mesmo padrao
# de test_env_admin_coverage.py e test_beneficiamento_refresh_unit.py.

import argparse
import importlib.util
import json
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from app.constants import EXECUTION_DELIVERED_STATUSES, EXECUTION_FAILED_STATUSES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIAGEM_PATH = PROJECT_ROOT / ".claude" / "skills" / "log-triage" / "triagem.py"

pytestmark = pytest.mark.unitario


def _http_error(codigo: int, motivo: str) -> urllib.error.HTTPError:
    """HTTPError sem resposta real, para simular erro vindo da API."""
    return urllib.error.HTTPError(
        url="http://127.0.0.1/api",
        code=codigo,
        msg=motivo,
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )


def _carregar_triagem() -> ModuleType:
    """Importa `triagem.py` pelo caminho, sem exigir que a skill seja pacote."""
    spec = importlib.util.spec_from_file_location("triagem_skill", TRIAGEM_PATH)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(name="triagem")
def fixture_triagem() -> ModuleType:
    """Instância nova do módulo por teste, para isolar monkeypatch."""
    return _carregar_triagem()


def test_arquivo_da_skill_existe() -> None:
    """Guarda contra renomear/mover a skill sem atualizar este teste."""
    assert TRIAGEM_PATH.is_file(), f"coletor nao encontrado em {TRIAGEM_PATH}"


# ---------------------------------------------------------------------------
# Ordenação: `finished_at` chega como DD/MM/YYYY HH:MM:SS (format_dt_br)
# ---------------------------------------------------------------------------


def test_ordenacao_cruzando_mes_nao_usa_comparacao_de_string(
    triagem: ModuleType,
) -> None:
    """30/09 é lexicograficamente maior que 01/10, mas cronologicamente menor.

    Era o defeito: ordenar a string punha a falha mais ANTIGA no topo da lista
    que o agente lê como "mais recentes primeiro".
    """
    falhas = [
        {"finished_at": "30/09/2026 23:00:00", "automacao": "A"},
        {"finished_at": "01/10/2026 07:00:00", "automacao": "B"},
        {"finished_at": "05/01/2027 09:00:00", "automacao": "C"},
    ]
    ordenado = sorted(falhas, key=triagem._ordenar_por_fim, reverse=True)
    assert [f["automacao"] for f in ordenado] == ["C", "B", "A"]

    # A comparação ingênua que existia antes erra este mesmo caso.
    ingenuo = sorted(falhas, key=lambda f: str(f["finished_at"]), reverse=True)
    assert [f["automacao"] for f in ingenuo] != ["C", "B", "A"]


@pytest.mark.parametrize("valor", [None, "", "2026-09-18T10:00:00", "lixo"])
def test_ordenacao_sem_data_valida_vai_para_o_fim(
    triagem: ModuleType, valor: Any
) -> None:
    """Data ausente ou em formato inesperado não pode virar "a mais recente"."""
    com_data = {"finished_at": "18/09/2026 10:00:00"}
    sem_data = {"finished_at": valor}
    assert triagem._ordenar_por_fim(sem_data) < triagem._ordenar_por_fim(com_data)


# ---------------------------------------------------------------------------
# Leitura de log: teto de `limit` e erro explícito
# ---------------------------------------------------------------------------


def test_buscar_logs_respeita_teto_de_limit_da_api(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`linhas * 3` estourava `le=5000` acima de 1666 e a API respondia 422."""
    pedidos: list[str] = []

    def falso_requisicao(rota: str, *_args: Any, **_kwargs: Any) -> Any:
        pedidos.append(rota)
        return {"total_lines": 10, "lines": ["linha"]}

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    triagem._buscar_logs("EXEC_1", 1700)

    limites = [int(r.split("limit=")[1].split("&")[0]) for r in pedidos]
    assert max(limites) <= triagem.LIMITE_LINHAS_LOG


def test_buscar_logs_com_linhas_minimo_nao_pede_limit_zero(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`limit=0` violava `ge=1`; o clamp precisa manter o pedido válido."""
    pedidos: list[str] = []

    def falso_requisicao(rota: str, *_args: Any, **_kwargs: Any) -> Any:
        pedidos.append(rota)
        return {"total_lines": 3, "lines": ["a", "b", "c"]}

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    triagem._buscar_logs("EXEC_1", 1)

    limites = [int(r.split("limit=")[1].split("&")[0]) for r in pedidos]
    assert min(limites) >= 1


def test_buscar_logs_distingue_erro_de_log_vazio(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """429/5xx viravam `[]`, indistinguível de execução que não logou nada.

    O relatório saía com `envelope: {}` e `pista: "indefinida"` e o agente
    concluía "o log não diz nada" em vez de "não consegui ler o log".
    """

    def erro_http(*_args: Any, **_kwargs: Any) -> Any:
        raise _http_error(429, "Too Many Requests")

    monkeypatch.setattr(triagem, "_requisicao", erro_http)
    linhas, erro = triagem._buscar_logs("EXEC_1", 60)

    assert linhas == []
    assert erro is not None and "429" in erro


def test_buscar_logs_sem_erro_devolve_erro_none(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log realmente vazio: lista vazia, mas `erro` None — o par diferencia."""
    monkeypatch.setattr(
        triagem,
        "_requisicao",
        lambda *_a, **_k: {"total_lines": 0, "lines": []},
    )
    linhas, erro = triagem._buscar_logs("EXEC_1", 60)
    assert (linhas, erro) == ([], None)


def test_coletar_falhas_ordena_o_relatorio_cronologicamente(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Testa o PONTO DE USO da ordenação, não só a função de chave.

    Mutation testing pegou este furo: o teste de `_ordenar_por_fim` isolada
    continuava passando quando `_coletar_falhas` voltava a ordenar pela string
    crua. É a ordem DESTE relatório que o agente lê como "mais recentes
    primeiro", então é ela que precisa estar amarrada.
    """
    itens = [
        {"id": "a", "automation_name": "X", "finished_at": "30/09/2026 23:00:00"},
        {"id": "b", "automation_name": "X", "finished_at": "01/10/2026 07:00:00"},
        {"id": "c", "automation_name": "X", "finished_at": "29/09/2026 10:00:00"},
    ]

    def falso_listar(_desde: str, status: str) -> Any:
        return (itens, None) if status == "ERROR" else ([], None)

    monkeypatch.setattr(triagem, "_listar_status", falso_listar)
    monkeypatch.setattr(triagem, "_buscar_logs", lambda *_a, **_k: ([], None))

    falhas, erros = triagem._coletar_falhas("2026-09-01T00:00:00", 60, False)

    assert [f["exec_id"] for f in falhas] == ["b", "a", "c"]
    assert erros == []


# ---------------------------------------------------------------------------
# Paginação e erro parcial de listagem
# ---------------------------------------------------------------------------


def test_listar_status_segue_todas_as_paginas(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`per_page=200` sem seguir `pages` descartava o excedente em silêncio.

    Cenário real: automação em crashloop com mais falhas que uma página, e
    `total_falhas` reportando o teto como se fosse o total — justamente onde a
    contagem de reincidência decide entre requeue e "isto é defeito, abra PR".
    """
    paginas = {
        1: {"items": [{"id": "a"}, {"id": "b"}], "pages": 3},
        2: {"items": [{"id": "c"}], "pages": 3},
        3: {"items": [{"id": "d"}], "pages": 3},
    }

    def falso_requisicao(rota: str, *_args: Any, **_kwargs: Any) -> Any:
        # `&page=` e nao `page=`: `per_page=200` casa primeiro e da KeyError.
        numero = int(rota.split("&page=")[1].split("&")[0])
        return paginas[numero]

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    itens, erro = triagem._listar_status("2026-09-01T00:00:00", "ERROR")

    assert [i["id"] for i in itens] == ["a", "b", "c", "d"]
    assert erro is None


def test_listar_status_erro_devolve_o_que_ja_coletou(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falha na 2ª página não pode descartar a 1ª nem mascarar o problema."""

    def falso_requisicao(rota: str, *_args: Any, **_kwargs: Any) -> Any:
        if "page=1" in rota:
            return {"items": [{"id": "a"}], "pages": 5}
        raise _http_error(422, "Unprocessable")

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    itens, erro = triagem._listar_status("2026-09-01T00:00:00", "ERROR")

    assert [i["id"] for i in itens] == ["a"]
    assert erro is not None and "422" in erro


def test_coletar_marca_relatorio_incompleto(
    triagem: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Erro parcial precisa aparecer no relatório, não virar silêncio.

    Sem `coleta_incompleta`, um relatório ao qual faltava um status inteiro era
    indistinguível de um relatório completo, e o agente decidia requeue sobre
    contagem de reincidência subestimada.
    """
    monkeypatch.setattr(
        triagem,
        "_requisicao",
        lambda *_a, **_k: {"database": "online", "scheduler": "ok", "worker": {}},
    )
    monkeypatch.setattr(
        triagem,
        "_coletar_falhas",
        lambda *_a, **_k: ([], ["ERROR: HTTP 422 (Unprocessable Entity)"]),
    )

    assert triagem.cmd_coletar(24, 60, False) == 0
    relatorio = json.loads(capsys.readouterr().out)
    assert relatorio["coleta_incompleta"] is True
    assert relatorio["erros_parciais"]


def test_coletar_nao_chama_api_respondeu_de_erro_http(
    triagem: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """HTTPError significa que a API RESPONDEU — o oposto de "não respondeu".

    O prompt do agendado manda parar e reportar quando a API não responde, então
    a mensagem errada fazia um 422 pontual abortar a triagem inteira com
    diagnóstico factualmente invertido.
    """

    def erro_http(*_args: Any, **_kwargs: Any) -> Any:
        raise _http_error(500, "Server Error")

    monkeypatch.setattr(triagem, "_requisicao", erro_http)
    assert triagem.cmd_coletar(24, 60, False) == 1

    erro = json.loads(capsys.readouterr().out)["erro"]
    assert "respondeu HTTP 500" in erro
    assert "nao respondeu" not in erro


def test_coletar_expoe_janela_inicio_com_hora(
    triagem: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--horas N` truncado para dia virava janela de ~32 h reportada como 14.

    O agendado tem requeue autônomo e raciocina sobre "não reincidente na
    janela": uma janela maior que a declarada o fazia reavaliar falha já tratada.
    """
    monkeypatch.setattr(
        triagem,
        "_requisicao",
        lambda *_a, **_k: {"database": "online", "scheduler": "ok", "worker": {}},
    )
    capturado: dict[str, str] = {}

    def falso_coletar(desde: str, *_a: Any, **_k: Any) -> Any:
        capturado["desde"] = desde
        return [], []

    monkeypatch.setattr(triagem, "_coletar_falhas", falso_coletar)
    triagem.cmd_coletar(14, 60, False)

    relatorio = json.loads(capsys.readouterr().out)
    # Timestamp completo, não data solta: 'T' separa data e hora no ISO.
    assert "T" in capturado["desde"]
    assert relatorio["janela_inicio"] == capturado["desde"]


# ---------------------------------------------------------------------------
# estado_por_automacao: recuperação por evidência positiva
# ---------------------------------------------------------------------------


def _mock_entrega(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch, entrega: tuple[Any, Any]
) -> None:
    monkeypatch.setattr(triagem, "_ultima_entrega", lambda _id: entrega)


def test_recuperada_true_quando_ha_entrega_posterior(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caso real da OBP-04: falhou 5x e depois entregou — não é para agir."""
    _mock_entrega(triagem, monkeypatch, ("18/09/2026 05:32:12", "SUCCESS"))
    estado = triagem._estado_por_automacao(
        [
            {
                "automacao": "OBs Paradas Fase",
                "automation_id": 4,
                "finished_at": "17/09/2026 18:09:17",
            }
        ]
    )
    assert estado["OBs Paradas Fase"]["recuperada"] is True


def test_recuperada_false_quando_a_falha_e_mais_recente(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ainda quebrada: é aqui que requeue e PR se justificam."""
    _mock_entrega(triagem, monkeypatch, ("18/09/2026 05:32:12", "SUCCESS"))
    estado = triagem._estado_por_automacao(
        [{"automacao": "X", "automation_id": 4, "finished_at": "18/09/2026 09:00:00"}]
    )
    assert estado["X"]["recuperada"] is False


def test_automacao_que_nunca_entregou(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ultimo_sucesso` nulo com `recuperada` falso distingue de "regrediu"."""
    _mock_entrega(triagem, monkeypatch, (None, None))
    estado = triagem._estado_por_automacao(
        [
            {
                "automacao": "Nova",
                "automation_id": 77,
                "finished_at": "18/09/2026 09:00:00",
            }
        ]
    )
    assert estado["Nova"]["ultimo_sucesso"] is None
    assert estado["Nova"]["recuperada"] is False


def test_sem_automation_id_fica_indeterminado(triagem: ModuleType) -> None:
    """`None` é indeterminado e NÃO pode ser lido como recuperada."""
    estado = triagem._estado_por_automacao(
        [
            {
                "automacao": "SemId",
                "automation_id": None,
                "finished_at": "18/09/2026 09:00:00",
            }
        ]
    )
    assert estado["SemId"]["recuperada"] is None


def test_ultima_falha_e_a_mais_recente_cruzando_mes(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A agregação usa a mesma chave cronológica, não ordem de chegada."""
    _mock_entrega(triagem, monkeypatch, (None, None))
    estado = triagem._estado_por_automacao(
        [
            {
                "automacao": "X",
                "automation_id": 4,
                "finished_at": "30/09/2026 23:00:00",
            },
            {
                "automacao": "X",
                "automation_id": 4,
                "finished_at": "01/10/2026 07:00:00",
            },
            {
                "automacao": "X",
                "automation_id": 4,
                "finished_at": "29/09/2026 10:00:00",
            },
        ]
    )
    assert estado["X"]["falhas_na_janela"] == 3
    assert estado["X"]["ultima_falha"] == "01/10/2026 07:00:00"


def test_ultima_entrega_prefere_a_mais_recente_entre_success_e_partial(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PARTIAL conta como entrega (o principal saiu) e pode ser a mais nova."""
    respostas = {
        "SUCCESS": {
            "items": [{"finished_at": "17/09/2026 10:00:00", "status": "SUCCESS"}]
        },
        "PARTIAL": {
            "items": [{"finished_at": "18/09/2026 10:00:00", "status": "PARTIAL"}]
        },
    }

    def falso_requisicao(rota: str, *_a: Any, **_k: Any) -> Any:
        for status, payload in respostas.items():
            if f"status={status}" in rota:
                return payload
        return {"items": []}

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    entrega, status = triagem._ultima_entrega(4)
    assert (entrega, status) == ("18/09/2026 10:00:00", "PARTIAL")


def test_ultima_entrega_ignora_janela(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A evidência de recuperação costuma estar FORA da janela triada."""
    rotas: list[str] = []

    def falso_requisicao(rota: str, *_a: Any, **_k: Any) -> Any:
        rotas.append(rota)
        return {"items": []}

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    triagem._ultima_entrega(4)
    assert rotas and all("date_from" not in rota for rota in rotas)


# ---------------------------------------------------------------------------
# Classificação e envelope
# ---------------------------------------------------------------------------


def test_defeito_do_engine_whatsapp_nao_passa_por_transitorio(
    triagem: ModuleType,
) -> None:
    """O caso que motivou a lista determinística.

    A mensagem real carrega o `timeout` do handshake JUNTO com o erro de defeito,
    e a classificação ingênua a chamava de transitória — convidando a requeue
    cego de algo que quebra em toda tentativa. `ambigua` obriga a ler o log.
    """
    log = [
        "Bootstrap do WhatsApp sem handshake concluido em 180000ms (timeout)",
        "Data passed to getter must include an id property but got undefined",
    ]
    assert triagem._classificar(log) == "ambigua"


@pytest.mark.parametrize(
    ("linhas", "esperado"),
    [
        (["ORA-12170: TNS: timeout"], "provavel_transitoria"),
        (["Traceback (most recent call last):"], "provavel_deterministica"),
        (["tudo normal por aqui"], "indefinida"),
    ],
)
def test_classificacao_dos_casos_puros(
    triagem: ModuleType, linhas: list[str], esperado: str
) -> None:
    """Assinatura de um só lado deve dar veredito, não ambiguidade."""
    assert triagem._classificar(linhas) == esperado


def test_envelope_extrai_execution_end_e_ignora_ruido(triagem: ModuleType) -> None:
    """O envelope é o que substitui o log cru no relatório — precisa ser fiel."""
    linhas = [
        "linha solta que nao e JSON",
        json.dumps({"level": "ERRO", "message": "falha no envio"}),
        json.dumps(
            {
                "event": "execution.end",
                "outcome_code": 4,
                "outcome_reason": "Uma ou mais fases falharam",
                "trace_id": "obp-x",
                "record_counts": {"phases_failed": 5},
                "steps": [
                    {"step": "extract", "ok": True},
                    {"step": "dispatch", "ok": False},
                    {"step": "commit", "ok": False},
                ],
            }
        ),
    ]
    envelope = triagem._resumir_envelope(linhas)
    assert envelope["outcome_code"] == 4
    assert envelope["steps_falhos"] == ["dispatch", "commit"]
    assert envelope["trace_id"] == "obp-x"
    assert "falha no envio" in envelope["mensagens_erro"]


def test_envelope_de_log_sem_json_fica_vazio(triagem: ModuleType) -> None:
    """Log de automação sem envelope estruturado não pode inventar campos."""
    assert triagem._resumir_envelope(["texto", "mais texto"]) == {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["0", "-5", "abc", ""])
def test_cli_recusa_inteiro_nao_positivo(triagem: ModuleType, valor: str) -> None:
    """Clampar em silêncio entregava relatório válido e sem diagnóstico nenhum."""
    with pytest.raises(argparse.ArgumentTypeError):
        triagem._inteiro_positivo(valor)


@pytest.mark.parametrize("valor", ["1", "14", "5000"])
def test_cli_aceita_inteiro_positivo(triagem: ModuleType, valor: str) -> None:
    """A validação não pode recusar valor legítimo."""
    assert triagem._inteiro_positivo(valor) == int(valor)


def test_requeue_exige_motivo(triagem: ModuleType) -> None:
    """`--motivo` é obrigatório: vira trilha de auditoria do que o agente fez."""
    parser = triagem._construir_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["requeue", "EXEC_1"])

    args = parser.parse_args(["requeue", "EXEC_1", "--motivo", "causa transiente"])
    assert args.motivo == "causa transiente"


def test_requeue_identifica_o_agente_na_auditoria(
    triagem: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem `requested_by`, a trilha mostrava salto de execuções sem ator."""
    enviado: dict[str, Any] = {}

    def falso_requisicao(rota: str, metodo: str = "GET", corpo: Any = None) -> Any:
        enviado.update({"rota": rota, "metodo": metodo, "corpo": corpo})
        return {"message": "ok", "queued_exec_id": "EXEC_2"}

    monkeypatch.setattr(triagem, "_requisicao", falso_requisicao)
    assert triagem.cmd_requeue("EXEC_1", "causa transiente") == 0

    assert enviado["metodo"] == "POST"
    assert enviado["corpo"]["requested_by"] == "AGENTE_TRIAGEM"
    assert enviado["corpo"]["reason"] == "causa transiente"


def test_status_de_falha_espelha_o_contrato_do_orchestrator(
    triagem: ModuleType,
) -> None:
    """O coletor duplica a lista por ser script standalone; o teste amarra as duas.

    `EXPIRED` fica fora de propósito: é tick descartado por congestionamento de
    queue_group antes de qualquer tentativa, não automação que rodou e falhou.
    """
    assert set(triagem.STATUS_FALHA) == EXECUTION_FAILED_STATUSES
    assert set(triagem.STATUS_ENTREGUE) == EXECUTION_DELIVERED_STATUSES

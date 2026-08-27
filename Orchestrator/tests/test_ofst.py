"""Smoke tests + unit tests de validação para OBs Fluxo Sem Tingimento (OFST-06).

Nenhum teste aqui toca Oracle: validators.py é puro por contrato, então toda a
regra de decisão (schema, coerção, fan-out de join, comparação estoque x
necessidade) é exercitada com dados mockados. A simulação contra Oracle real é
manual, via "OBs Fluxo Sem Tingimento/test_ofst_simulation.py".
"""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent.parent
AUTOMATION_DIR = ROOT / "OBs Fluxo Sem Tingimento"

# Nomes genericos que _load_module cacheia em sys.modules — ver o fixture
# _isolar_modulos_genericos abaixo, que limpa esses nomes ao fim da suite.
_GENERIC_MODULE_NAMES = ("validators", "errors", "models", "queries")

# validators.py importa `errors`/`models` como módulos irmãos (padrão dos scripts
# de automação, que rodam com o próprio diretório no sys.path).
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))


def _load_module(name: str, path: Path) -> ModuleType:
    """Carrega um módulo da automação sob o seu nome canônico.

    O nome importa: validators.py faz `from errors import DadoIncompletoError`, então
    carregar errors.py sob um apelido criaria uma SEGUNDA classe de exceção e o
    pytest.raises nunca casaria com a que validators realmente levanta. Reaproveitar
    sys.modules garante uma instância só por módulo.
    """
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", autouse=True)
def _isolar_modulos_genericos() -> Any:
    """Evita vazamento de `validators`/`errors`/`models`/`queries` para a suite
    da próxima automação que repetir esse layout de arquivos.

    Os nomes precisam ser genéricos ENQUANTO este arquivo roda (ver docstring
    de `_load_module`), mas nada garante isso após — outra automação com o
    mesmo layout carregaria os módulos ERRADOS via cache de sys.modules. Este
    fixture roda uma vez por módulo de teste e desfaz o cache/path ao final.
    """
    yield
    for nome in _GENERIC_MODULE_NAMES:
        sys.modules.pop(nome, None)
    if str(AUTOMATION_DIR) in sys.path:
        sys.path.remove(str(AUTOMATION_DIR))


def _validators() -> ModuleType:
    return _load_module("validators", AUTOMATION_DIR / "validators.py")


def _queries() -> ModuleType:
    return _load_module("queries", AUTOMATION_DIR / "queries.py")


def _errors() -> ModuleType:
    return _load_module("errors", AUTOMATION_DIR / "errors.py")


def _ob_row(**overrides: Any) -> dict[str, Any]:
    """Linha válida da query de OBs; sobrescreva um campo para testar cada falha."""
    row: dict[str, Any] = {
        "NUMERO_OB": 1001,
        "CODIGO_FLUXO": 204,
        "CODIGO_REDUZIDO_CRU": 12345,
        "CODIGO_ARTIGO_CRU": "00489",
        "STATUS": 1,
        "TOTAL_PECAS": 50,
        "KILOS_PROGRAMADOS": 120.5,
        "OBMONTADA": "0",
        "DT_ENTREGA": "2026-07-20T00:00:00",
        "ID_CLIENTE": 7,
        "NOME_CLIENTE": "CR-LOJA BLUMENAU",
    }
    row.update(overrides)
    return row


def _estoque_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "CODIGO_REDUZIDO_PROD": 12345,
        "QTD_PECAS_DISPONIVEIS": 75,
        "QTD_LINHAS_BRUTAS": 75,
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------
# Smoke: estrutura da automação
# --------------------------------------------------------------------------


def test_manifest_valido() -> None:
    manifest_path = AUTOMATION_DIR / "automation.manifest.json"
    assert manifest_path.exists(), "automation.manifest.json ausente"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == "OFST-06"
    assert manifest["runtime"] == "powershell"
    assert "whatsapp" in manifest["channels"]
    assert manifest["dependencies"]["oracle"] is True


def test_schedule_e_json_valido_de_120_em_120_minutos() -> None:
    manifest = json.loads(
        (AUTOMATION_DIR / "automation.manifest.json").read_text(encoding="utf-8")
    )
    schedule = json.loads(manifest["schedule"])
    assert schedule["schedule_type"] == "cron"
    assert schedule["timezone"] == "America/Sao_Paulo"
    # Desde [1.2.4] o cron_expression é uma lista (janelas distintas Seg-Sex e
    # Sáb), a cada 120 min. Cada expressão dispara no minuto 0 com passo de 2h.
    cron = schedule["cron_expression"]
    assert isinstance(cron, list) and cron
    assert all(expr.startswith("0 ") for expr in cron)
    assert all("/2" in expr for expr in cron)


def test_entrypoint_e_scripts_existem() -> None:
    assert (AUTOMATION_DIR / "run.ps1").exists()
    assert (AUTOMATION_DIR / "extract_ofst.py").exists()
    assert (AUTOMATION_DIR / "validators.py").exists()
    assert (AUTOMATION_DIR / "format_message.py").exists()
    assert (AUTOMATION_DIR / "test_ofst_simulation.py").exists()


def test_docs_existem() -> None:
    assert (AUTOMATION_DIR / "README.md").exists()
    assert (AUTOMATION_DIR / "CONTEXT.md").exists()


def test_whatsapp_config_valido() -> None:
    cfg = json.loads(
        (AUTOMATION_DIR / "whatsapp-config.json").read_text(encoding="utf-8")
    )
    assert cfg["auth"]["clientId"] == "hub-global"
    assert cfg["target"]["type"] == "group"
    assert (
        cfg["target"]["contactIdEnv"] == "OFST_WHATSAPP_TARGET"
    ), "destino real deve vir do .env, nunca do config versionado"
    assert re.match(r"^[\d\-]+@g\.us$", cfg["target"]["contactId"])


def test_sql_obs_respeita_o_contrato_de_negocio() -> None:
    sql = (
        (AUTOMATION_DIR / "SQL-ObsFluxoSemTingimento.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert "SELECT *" not in sql, "SELECT * reprova no Test-SqlPerformance"
    assert "CODIGO_FLUXO = 204" in sql
    assert "OB.STATUS = 1" in sql
    assert "OBMONTADA = '0'" in sql
    assert "TOTAL_PECAS" in sql
    assert "CODIGO_ARTIGO_CRU" in sql
    # Entrega e filial destino: mesmos campos da CTE ENTREGA_OB de OBs Paradas Fase
    assert "DT_ENTREGA" in sql
    assert "NOMEFANTASIA" in sql
    assert "IDFILIALRESPONSAVEL" in sql


def test_sql_obs_filtra_pedido_comercial_terminado_em_r_ou_s() -> None:
    sql = (
        (AUTOMATION_DIR / "SQL-ObsFluxoSemTingimento.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert "PEDIDOCLIENTE NOT LIKE '%R'" in sql
    assert "PEDIDOCLIENTE NOT LIKE '%S'" in sql
    assert (
        "PEDIDOCLIENTE IS NULL" in sql
    ), "OB sem pedido comercial associado deve permanecer na lista (D7 do CONTEXT.md)"
    # Regressão: sem esse filtro na condicao do join, um pedido "placeholder"
    # (PEDIDOCLIENTE='0') introduz fan-out real — ver decisao D7 do CONTEXT.md.
    assert "QUANTIDADE_ATUAL <> 0" in sql


def test_sql_estoque_filtra_deposito_95_e_conta_distinto() -> None:
    sql = (
        (AUTOMATION_DIR / "SQL-EstoqueDeposito95.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert "SELECT *" not in sql
    assert "CODIGO_DEPOSITO IN (95)" in sql
    assert "STPECAPRODUTO IN (0, 16, 18)" in sql
    assert "COUNT(DISTINCT GPP.IDPECASPRODUTO)" in sql
    assert "GROUP BY GPP.CODIGO_REDUZIDO_PROD" in sql


# --------------------------------------------------------------------------
# Validação 1 — query de OBs (schema + domínio)
# --------------------------------------------------------------------------


def test_validate_ob_query_aprova_lote_valido() -> None:
    v = _validators()
    rows = [_ob_row(NUMERO_OB=1), _ob_row(NUMERO_OB=2)]
    relatorio = v.validate_ob_query(list(rows[0].keys()), rows)
    assert relatorio.ok is True
    assert relatorio.total == 2
    assert relatorio.problemas == []


def test_validate_ob_query_reprova_coluna_ausente_sem_avaliar_linhas() -> None:
    """Schema quebrado invalida o lote inteiro — não faz sentido validar linha a linha."""
    v = _validators()
    colunas = [c for c in v.COLUNAS_OB_OBRIGATORIAS if c != "TOTAL_PECAS"]
    relatorio = v.validate_ob_query(colunas, [_ob_row()])
    assert relatorio.ok is False
    assert "TOTAL_PECAS" in relatorio.problemas[0]


def test_validate_ob_query_limita_amostra_a_tres() -> None:
    v = _validators()
    rows = [_ob_row(NUMERO_OB=i) for i in range(10)]
    relatorio = v.validate_ob_query(list(rows[0].keys()), rows)
    assert len(relatorio.amostra) == 3


def test_validate_ob_query_devolve_obs_ja_coagidas() -> None:
    """relatorio.obs poupa o chamador de rodar coerce_ob_row de novo sobre o
    retorno cru — extract_ofst.py e a simulação consomem só este campo."""
    v = _validators()
    rows = [
        _ob_row(NUMERO_OB=1),
        _ob_row(NUMERO_OB=2, TOTAL_PECAS=0),  # invalida: sem necessidade
        _ob_row(NUMERO_OB=3),
    ]
    relatorio = v.validate_ob_query(list(rows[0].keys()), rows)
    assert [ob.id_ob for ob in relatorio.obs] == [1, 3]
    assert len(relatorio.problemas) == 1


def test_validate_ob_query_acumula_todos_os_problemas() -> None:
    """A simulação precisa mostrar todos os defeitos de uma vez, não parar no 1º."""
    v = _validators()
    rows = [_ob_row(NUMERO_OB=1, TOTAL_PECAS=0), _ob_row(NUMERO_OB=2, STATUS=3)]
    relatorio = v.validate_ob_query(list(rows[0].keys()), rows)
    assert relatorio.ok is False
    assert len(relatorio.problemas) == 2


@pytest.mark.parametrize(
    "override, trecho_esperado",
    [
        ({"NUMERO_OB": None}, "NUMERO_OB"),
        ({"TOTAL_PECAS": None}, "TOTAL_PECAS"),
        ({"CODIGO_REDUZIDO_CRU": "abc"}, "CODIGO_REDUZIDO_CRU"),
        ({"ID_CLIENTE": "abc"}, "ID_CLIENTE"),
        ({"CODIGO_FLUXO": 205}, "CODIGO_FLUXO"),
        ({"STATUS": 0}, "STATUS"),
        ({"OBMONTADA": "1"}, "OBMONTADA"),
        ({"TOTAL_PECAS": 0}, "TOTAL_PECAS"),
    ],
)
def test_coerce_ob_row_rejeita_dado_fora_do_contrato(
    override: dict[str, Any], trecho_esperado: str
) -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError) as exc:
        v.coerce_ob_row(_ob_row(**override))
    assert trecho_esperado in str(exc.value)


def test_coerce_ob_row_aceita_numeros_como_string_ou_decimal() -> None:
    """Oracle NUMBER chega como Decimal/float/str dependendo do driver."""
    v = _validators()
    ob = v.coerce_ob_row(
        _ob_row(
            NUMERO_OB="1001",
            TOTAL_PECAS=50.0,
            KILOS_PROGRAMADOS="120.5",
            OBMONTADA=" 0 ",
        )
    )
    assert ob.id_ob == 1001
    assert ob.total_pecas == 50
    assert ob.kilos_programados == pytest.approx(120.5)


def test_coerce_ob_row_preserva_artigo_cru_como_texto() -> None:
    """CDARTIGOCRU é texto no Oracle e chega com zeros à esquerda ('00489')."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(CODIGO_ARTIGO_CRU="00489"))
    assert ob.codigo_artigo_cru == "00489"


def test_coerce_ob_row_aceita_artigo_cru_alfanumerico() -> None:
    """Defeito latente idêntico ao da ORB-07 (onde '0A231' descartou 27% do lote).

    A população de fluxo sem tingimento nunca trouxe um artigo alfanumérico em
    246 execuções, mas o código é o mesmo — este teste trava a regressão.
    """
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(CODIGO_ARTIGO_CRU="0A231"))
    assert ob.codigo_artigo_cru == "0A231"


def test_coerce_ob_row_trata_artigo_cru_em_branco_como_ausente() -> None:
    v = _validators()
    assert v.coerce_ob_row(_ob_row(CODIGO_ARTIGO_CRU="   ")).codigo_artigo_cru is None


def test_coerce_ob_row_aceita_artigo_cru_nulo() -> None:
    """CODIGO_ARTIGO_CRU vem de LEFT JOIN: OB sem cadastro de artigo continua
    notificavel (a mensagem mostra '—'), em vez de ser silenciosamente pulada."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(CODIGO_ARTIGO_CRU=None))
    assert ob.codigo_artigo_cru is None


def test_coerce_ob_row_aceita_entrega_e_cliente_nulos() -> None:
    """DT_ENTREGA/ID_CLIENTE/NOME_CLIENTE vem da cadeia LEFT JOIN ate
    PEDIDOCOMERCIAL/PESSOASFJ: OB sem pedido comercial permanece na lista."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(DT_ENTREGA=None, ID_CLIENTE=None, NOME_CLIENTE=None))
    assert ob.dt_entrega is None
    assert ob.id_cliente is None
    assert ob.nome_cliente is None


def test_coerce_ob_row_coage_entrega_e_cliente() -> None:
    v = _validators()
    ob = v.coerce_ob_row(
        _ob_row(
            DT_ENTREGA="2026-07-21T00:00:00",
            ID_CLIENTE="1",
            NOME_CLIENTE=" CR-MATRIZ/PR ",
        )
    )
    assert ob.dt_entrega == "2026-07-21T00:00:00"
    assert ob.id_cliente == 1
    assert ob.nome_cliente == "CR-MATRIZ/PR"


def test_dedupe_obs_remove_linha_duplicada_e_reporta_o_id() -> None:
    """Blindagem contra fan-out residual do join de pedido comercial: a mesma OB
    repetida no retorno da query nao pode aparecer duas vezes na mensagem."""
    v = _validators()
    obs = [
        v.coerce_ob_row(_ob_row(NUMERO_OB=1)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=2)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=1)),
    ]
    unicas, duplicados = v.dedupe_obs(obs)
    assert [ob.id_ob for ob in unicas] == [1, 2]
    assert duplicados == [1]


def test_dedupe_obs_sem_duplicata_e_noop() -> None:
    v = _validators()
    obs = [v.coerce_ob_row(_ob_row(NUMERO_OB=i)) for i in (1, 2, 3)]
    unicas, duplicados = v.dedupe_obs(obs)
    assert unicas == obs
    assert duplicados == []


# --------------------------------------------------------------------------
# Validação 2 — query de estoque
# --------------------------------------------------------------------------


def test_validate_estoque_row_detecta_fan_out_de_join() -> None:
    """Regressão do risco central: ITENS_ESTOQUE/TIPO_FINALIDADE_FIO entram só como
    filtro; se duplicarem linhas, o COUNT simples do spec superestimaria o estoque
    e a OB seria notificada sem peça. A contagem distinta é a autoritativa."""
    v = _validators()
    estoque = v.validate_estoque_row(
        _estoque_row(QTD_PECAS_DISPONIVEIS=75, QTD_LINHAS_BRUTAS=150)
    )
    assert estoque.quantidade == 75
    assert estoque.tem_fan_out is True


def test_validate_estoque_row_sem_fan_out() -> None:
    v = _validators()
    assert v.validate_estoque_row(_estoque_row()).tem_fan_out is False


def test_validate_estoque_row_reprova_schema_quebrado() -> None:
    v, e = _validators(), _errors()
    row = _estoque_row()
    del row["QTD_PECAS_DISPONIVEIS"]
    with pytest.raises(e.SchemaInvalidoError):
        v.validate_estoque_row(row)


def test_validate_estoque_row_reprova_quantidade_negativa() -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.validate_estoque_row(
            _estoque_row(QTD_PECAS_DISPONIVEIS=-1, QTD_LINHAS_BRUTAS=-1)
        )


def test_validate_estoque_query_trata_ausencia_de_linha_como_zero_valido() -> None:
    """GROUP BY não emite linha para código sem peça: é 0 unidades, não um erro."""
    v = _validators()
    resultado = v.validate_estoque_query(999, [])
    assert resultado["validado"] is True
    assert resultado["quantidade"] == 0


def test_validate_estoque_query_encontra_o_codigo_certo() -> None:
    v = _validators()
    rows = [
        _estoque_row(
            CODIGO_REDUZIDO_PROD=111, QTD_PECAS_DISPONIVEIS=10, QTD_LINHAS_BRUTAS=10
        ),
        _estoque_row(
            CODIGO_REDUZIDO_PROD=222, QTD_PECAS_DISPONIVEIS=20, QTD_LINHAS_BRUTAS=20
        ),
    ]
    resultado = v.validate_estoque_query(222, rows)
    assert resultado["codigo"] == 222
    assert resultado["quantidade"] == 20
    assert resultado["validado"] is True


# --------------------------------------------------------------------------
# Validação 3 — regra de comparação
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "necessario, disponivel, esperado",
    [
        (50, 75, True),
        (50, 50, True),  # igual basta para montar
        (100, 99, False),
        (100, 0, False),
    ],
)
def test_validate_comparison_logic(
    necessario: int, disponivel: int, esperado: bool
) -> None:
    v = _validators()
    assert v.validate_comparison_logic(necessario, disponivel) is esperado


# --------------------------------------------------------------------------
# Validação 4 — priorização (lojas antes da matriz) e alocação de estoque
# --------------------------------------------------------------------------


def _estoques(**por_reduzido: int) -> dict[int, Any]:
    """Mapa codigo_reduzido -> EstoqueDeposito, ex.: _estoques(r100=90)."""
    v = _validators()
    return {
        int(chave[1:]): v.validate_estoque_row(
            _estoque_row(
                CODIGO_REDUZIDO_PROD=int(chave[1:]),
                QTD_PECAS_DISPONIVEIS=qtd,
                QTD_LINHAS_BRUTAS=qtd,
            )
        )
        for chave, qtd in por_reduzido.items()
    }


def test_priorizar_obs_lojas_antes_da_matriz_por_data_de_entrega() -> None:
    """Lojas (ID_CLIENTE != 1) tem prioridade, por entrega ascendente; a matriz
    (CR-MATRIZ/PR, deposito de malhas) vai para o fim, tambem por entrega."""
    v = _validators()
    obs = [
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=1, ID_CLIENTE=1, DT_ENTREGA="2026-07-18T00:00:00")
        ),
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=2, ID_CLIENTE=7, DT_ENTREGA="2026-07-25T00:00:00")
        ),
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=3, ID_CLIENTE=1, DT_ENTREGA="2026-07-17T00:00:00")
        ),
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=4, ID_CLIENTE=9, DT_ENTREGA="2026-07-19T00:00:00")
        ),
    ]
    ordenadas = v.priorizar_obs(obs)
    # Lojas 4 (19/07) e 2 (25/07) antes da matriz, mesmo a matriz entregando antes.
    assert [ob.id_ob for ob in ordenadas] == [4, 2, 3, 1]


def test_priorizar_obs_sem_data_vai_para_o_fim_do_grupo() -> None:
    """OB sem pedido comercial (entrega/cliente nulos) conta como loja, mas
    depois das lojas com data conhecida; desempate final por NUMERO_OB."""
    v = _validators()
    obs = [
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=1, ID_CLIENTE=None, DT_ENTREGA=None, NOME_CLIENTE=None)
        ),
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=2, ID_CLIENTE=7, DT_ENTREGA="2026-07-25T00:00:00")
        ),
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=3, ID_CLIENTE=1, DT_ENTREGA="2026-07-17T00:00:00")
        ),
    ]
    assert [ob.id_ob for ob in v.priorizar_obs(obs)] == [2, 1, 3]


def test_alocar_estoque_deduz_saldo_e_para_quando_acaba() -> None:
    """Alocacao sequencial: 90 pecas cobrem as OBs de 50 e 30, mas a terceira
    (40) NAO entra — o saldo restante e 10. Sem alocacao, as tres seriam
    notificadas contra o mesmo estoque e a montagem falharia no fisico."""
    v = _validators()
    obs = [
        v.coerce_ob_row(_ob_row(NUMERO_OB=1, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=50)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=2, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=30)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=3, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=40)),
    ]
    avaliacoes = v.alocar_estoque(obs, _estoques(r100=90))
    assert [a.notificar for a in avaliacoes] == [True, True, False]
    assert [a.disponivel for a in avaliacoes] == [90, 40, 10]
    assert "faltam 30" in avaliacoes[2].motivo


def test_alocar_estoque_matriz_so_entra_se_sobrar_apos_as_lojas() -> None:
    """Cenario fim-a-fim da regra: a loja consome o estoque primeiro; a matriz
    (mais antiga na fila por entrega) so entra se sobrar saldo."""
    v = _validators()
    matriz = v.coerce_ob_row(
        _ob_row(
            NUMERO_OB=1,
            CODIGO_REDUZIDO_CRU=100,
            TOTAL_PECAS=30,
            ID_CLIENTE=1,
            NOME_CLIENTE="CR-MATRIZ/PR",
            DT_ENTREGA="2026-07-17T00:00:00",
        )
    )
    loja = v.coerce_ob_row(
        _ob_row(
            NUMERO_OB=2,
            CODIGO_REDUZIDO_CRU=100,
            TOTAL_PECAS=60,
            ID_CLIENTE=7,
            DT_ENTREGA="2026-07-30T00:00:00",
        )
    )

    # Estoque 80: cobre a loja (60), sobra 20 — a matriz (30) fica de fora.
    avaliacoes = v.alocar_estoque(v.priorizar_obs([matriz, loja]), _estoques(r100=80))
    assert [(a.ob.id_ob, a.notificar) for a in avaliacoes] == [(2, True), (1, False)]

    # Estoque 100: cobre a loja (60) e sobra 40 — a matriz (30) tambem entra.
    avaliacoes = v.alocar_estoque(v.priorizar_obs([matriz, loja]), _estoques(r100=100))
    assert [(a.ob.id_ob, a.notificar) for a in avaliacoes] == [(2, True), (1, True)]


def test_alocar_estoque_saldos_independentes_por_reduzido() -> None:
    """O saldo e por produto: consumir o reduzido 100 nao afeta o 200."""
    v = _validators()
    obs = [
        v.coerce_ob_row(_ob_row(NUMERO_OB=1, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=50)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=2, CODIGO_REDUZIDO_CRU=200, TOTAL_PECAS=50)),
    ]
    avaliacoes = v.alocar_estoque(obs, _estoques(r100=50, r200=50))
    assert [a.notificar for a in avaliacoes] == [True, True]


def test_alocar_estoque_sem_linha_de_estoque_nao_notifica_e_explica() -> None:
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(TOTAL_PECAS=50))
    avaliacao = v.alocar_estoque([ob], {})[0]
    assert avaliacao.notificar is False
    assert avaliacao.disponivel == 0
    assert "faltam 50" in avaliacao.motivo


# --------------------------------------------------------------------------
# State de idempotência — merge_notified_state
# --------------------------------------------------------------------------


def _avaliacao(numero_ob: int, notificar: bool) -> Any:
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(NUMERO_OB=numero_ob, TOTAL_PECAS=50))
    estoques = (
        {
            ob.codigo_reduzido_cru: v.validate_estoque_row(
                _estoque_row(
                    CODIGO_REDUZIDO_PROD=ob.codigo_reduzido_cru,
                    QTD_PECAS_DISPONIVEIS=75,
                    QTD_LINHAS_BRUTAS=75,
                )
            )
        }
        if notificar
        else {}
    )
    return v.alocar_estoque([ob], estoques)[0]


def test_merge_notified_state_mantem_ob_avisada_com_estoque_oscilando() -> None:
    """Regressão da correção do review: OB já avisada cujo estoque caiu abaixo
    da necessidade (mas segue na query, não montada) NÃO sai do state — senão
    ela seria re-avisada a cada cruzamento do limiar, com execução horária."""
    v = _validators()
    sem_estoque_agora = _avaliacao(1001, notificar=False)
    estado = v.merge_notified_state(
        {"1001": "2026-07-15T10:00:00"}, [sem_estoque_agora], [], "2026-07-16T10:00:00"
    )
    assert estado == {"1001": "2026-07-15T10:00:00"}


def test_merge_notified_state_poda_ob_que_saiu_da_query() -> None:
    """OB montada some da query e do state; se voltar a ficar pendente, avisa de novo."""
    v = _validators()
    outra = _avaliacao(2002, notificar=True)
    estado = v.merge_notified_state(
        {"1001": "2026-07-15T10:00:00", "2002": "2026-07-15T10:00:00"},
        [outra],
        [],
        "2026-07-16T10:00:00",
    )
    assert estado == {"2002": "2026-07-15T10:00:00"}


def test_merge_notified_state_adiciona_novas_com_timestamp_atual() -> None:
    v = _validators()
    nova = _avaliacao(3003, notificar=True)
    estado = v.merge_notified_state({}, [nova], [nova], "2026-07-16T11:00:00")
    assert estado == {"3003": "2026-07-16T11:00:00"}


# --------------------------------------------------------------------------
# Queries — parametrização segura
# --------------------------------------------------------------------------


def test_build_estoque_sql_usa_bind_e_nao_interpola_valores() -> None:
    """Zero-Trust: o valor nunca entra na string SQL."""
    q = _queries()
    sql, params = q.build_estoque_sql([12345, 678])
    assert q.IN_BINDS_MARKER not in sql
    assert ":C0, :C1" in sql
    assert params == {"C0": 12345, "C1": 678}
    assert "12345" not in sql.split("GROUP BY")[0].split("IN (")[-1]


def test_build_estoque_sql_rejeita_lista_vazia_ou_grande_demais() -> None:
    q = _queries()
    with pytest.raises(ValueError):
        q.build_estoque_sql([])
    with pytest.raises(ValueError):
        q.build_estoque_sql(list(range(q.MAX_IN_BINDS + 1)))


def test_chunk_codigos_respeita_o_limite_do_oracle() -> None:
    """ORA-01795: lista IN não aceita mais de 1000 expressões."""
    q = _queries()
    lotes = q.chunk_codigos(list(range(2000)))
    assert len(lotes) == 3
    assert all(len(lote) <= q.MAX_IN_BINDS for lote in lotes)
    assert sum(len(lote) for lote in lotes) == 2000


# --------------------------------------------------------------------------
# Mensagem
# --------------------------------------------------------------------------


def _row_mensagem(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "NUMERO_OB": 1001,
        "CODIGO_REDUZIDO_CRU": 12345,
        "CODIGO_ARTIGO_CRU": 489,
        "TOTAL_PECAS": 50,
        "QTD_PECAS_DISPONIVEIS": 75,
        "DT_ENTREGA": "2026-07-20T00:00:00",
        "NOME_CLIENTE": "CR-LOJA BLUMENAU",
    }
    row.update(overrides)
    return row


def test_build_message_monta_o_template_do_grupo() -> None:
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {"rows": [_row_mensagem()], "resumo": {"tempo_consulta_ms": 1200}}
    )
    assert "Depósito 95 - OBs Fluxo Sem Tingimento" in msg
    assert "*OB: 1001*" in msg
    assert "Artigo: 489" in msg
    assert "Reduzido: 12345" in msg
    assert "Quantidade necessária: 50 peças" in msg
    assert "Estoque disponível: 75 peças" in msg
    assert "Data de entrega: 20/07/2026" in msg
    assert "Filial destino: CR-LOJA BLUMENAU" in msg


def test_build_message_exibe_artigo_alfanumerico_e_mantem_o_numerico_como_antes() -> (
    None
):
    """`codigo_artigo_cru` deixou de ser int (ver coerce_ob_row).

    O texto alfanumérico passa inteiro; o código puramente numérico continua sem
    os zeros à esquerda, para que a mudança de tipo não altere a mensagem que a
    Expedição já conhece.
    """
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    assert "Artigo: 0A231" in module.build_message(
        {"rows": [_row_mensagem(CODIGO_ARTIGO_CRU="0A231")]}
    )
    assert "Artigo: 489" in module.build_message(
        {"rows": [_row_mensagem(CODIGO_ARTIGO_CRU="00489")]}
    )
    assert "Artigo: —" in module.build_message(
        {"rows": [_row_mensagem(CODIGO_ARTIGO_CRU=None)]}
    )


def test_build_message_nao_expoe_tempo_de_consulta_nem_grupo() -> None:
    """Tempo de consulta e grupo destino sao observabilidade interna
    (ofst_result.json/logs) — irrelevantes para os integrantes do grupo."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {"rows": [_row_mensagem()], "resumo": {"tempo_consulta_ms": 4688}}
    )
    assert "Tempo de consulta" not in msg
    assert "4688" not in msg
    assert "Grupo:" not in msg


def test_build_message_mostra_travessao_para_campos_nulos() -> None:
    """OB sem cadastro de artigo cru ou sem pedido comercial (LEFT JOINs)
    notifica com '—' nos campos ausentes."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    CODIGO_ARTIGO_CRU=None, DT_ENTREGA=None, NOME_CLIENTE=None
                )
            ],
            "resumo": {"tempo_consulta_ms": 10},
        }
    )
    assert "Artigo: —" in msg
    assert "Data de entrega: —" in msg
    assert "Filial destino: —" in msg


def test_build_message_agrega_multiplas_obs_na_ordem_recebida() -> None:
    """A ordem dos rows e a ordem de prioridade decidida na extracao
    (priorizar_obs + alocar_estoque) — a mensagem nao reordena."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(NUMERO_OB=2, NOME_CLIENTE="CR-LOJA CURITIBA"),
                _row_mensagem(NUMERO_OB=1, NOME_CLIENTE="CR-MATRIZ/PR"),
            ],
            "resumo": {"tempo_consulta_ms": 10},
        }
    )
    assert "2 OBs prontas" in msg
    assert msg.index("*OB: 2*") < msg.index("*OB: 1*")


def test_record_counts_usa_chaves_canonicas_sem_failures() -> None:
    # pylint: disable=protected-access
    """F3: espelho da ORB-07 — `read` conta as linhas cruas do Oracle e as linhas
    descartadas na validação de schema entram como `rejected` (não `failures`,
    que um agente de monitoramento lê como erro de execução)."""
    extract = _load_module("extract_ofst", AUTOMATION_DIR / "extract_ofst.py")
    resumo = extract.ResumoExecucao()
    resumo.total_lidas = 8
    resumo.total_obs = 6
    resumo.total_notificaveis = 3
    resumo.total_sem_estoque = 3
    resumo.falhas = ["OB #1: campo nulo", "OB #2: campo nulo"]

    rc = extract._record_counts(resumo, novas_count=3)

    assert "failures" not in rc
    assert rc["read"] == 8
    assert rc["validated"] == 6
    assert rc["rejected"] == 2
    assert rc["qualified"] == 3
    assert rc["notified"] == 3
    assert rc["skipped"] == 3
    assert rc["suppressed"] == 0
    assert all(isinstance(v, int) and v >= 0 for v in rc.values())

"""Smoke tests + unit tests de validação para OBs Restrição Branco (ORB-07).

Nenhum teste aqui toca Oracle: validators.py é puro por contrato, então toda a
regra de decisão (schema, coerção, fan-out de join, comparação estoque x
necessidade) é exercitada com dados mockados. A simulação contra Oracle real é
manual, via "OBs Restricao Branco/test_orb_simulation.py".
"""

# protected-access: a suite exercita helpers privados do extrator (`_read_notified`)
# de proposito — sao a unidade sob teste, nao detalhe de outro objeto.
# unused-argument: os dubles de `fetch_*` precisam repetir a assinatura real
# (creds, exec_id, resumo) mesmo quando ignoram os parametros.
# pylint: disable=protected-access, unused-argument

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent.parent
AUTOMATION_DIR = ROOT / "OBs Restricao Branco"

# Nomes genericos que _load_module cacheia em sys.modules — ver o fixture
# _isolar_modulos_genericos abaixo, que limpa esses nomes ao fim da suite.
_GENERIC_MODULE_NAMES = (
    "validators",
    "errors",
    "models",
    "queries",
    "format_message",
    "extract_orb_state",
)


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
    # A coleta do pytest importa todos os arquivos antes de executar fixtures.
    # Alterar sys.path no topo deste módulo contaminaria a suíte OFST-06, que
    # usa os mesmos nomes irmãos. O escopo começa somente quando a ORB roda.
    for nome in _GENERIC_MODULE_NAMES:
        sys.modules.pop(nome, None)
    sys.path.insert(0, str(AUTOMATION_DIR))
    yield
    for nome in _GENERIC_MODULE_NAMES:
        sys.modules.pop(nome, None)
    # TODAS as ocorrências, não só a inserida acima: importar `extract_orb.py`
    # (ver os testes do state) executa o `sys.path.insert` do próprio script,
    # acrescentando uma SEGUNDA entrada deste diretório. Removendo só uma, a
    # suíte OFST-06 passaria a carregar os módulos irmãos da ORB-07 e falharia
    # em massa — mas apenas na ordem em que a ORB roda antes, o que a ordem
    # alfabética esconde.
    while str(AUTOMATION_DIR) in sys.path:
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
        "CODIGO_COR_TINGIMENTO": "00001",
        "CD_CLASSIFICACAO_COR": 6,
        "DS_CLASSIFICACAO_COR": "BRANCO",
        "QTD_CLASSIFICACOES_COR": 1,
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


# Descrições das finalidades compatíveis com as classificações brancas (6 e 9),
# como SGTPRD.COR_FINALIDADE x TIPO_FINALIDADE_FIO as devolvem em produção.
FINALIDADES_BRANCO: dict[int, str] = {
    1: "SEM RESTRIÇÃO",
    3: "CORES CLARAS",
    4: "BRANCO",
    6: "BRANCO OU PRETO",
    8: "FIO C/ RESÍDUO",
    12: "REMOÇÃO DE ÓLEO",
    13: "MARFIM",
}


def _estoque_rows(
    codigo: int = 12345,
    total: int = 75,
    brutas: int | None = None,
    por_finalidade: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Monta o retorno do GROUPING SETS de UM reduzido: linha total + parciais."""
    parciais = {4: total} if por_finalidade is None else por_finalidade
    linhas: list[dict[str, Any]] = [
        {
            "CODIGO_REDUZIDO_PROD": codigo,
            "FINALIDADE": None,
            "EH_TOTAL": 1,
            "QTD_PECAS_DISPONIVEIS": total,
            "QTD_LINHAS_BRUTAS": total if brutas is None else brutas,
        }
    ]
    linhas.extend(
        {
            "CODIGO_REDUZIDO_PROD": codigo,
            "FINALIDADE": finalidade,
            "EH_TOTAL": 0,
            "QTD_PECAS_DISPONIVEIS": quantidade,
            "QTD_LINHAS_BRUTAS": quantidade,
        }
        for finalidade, quantidade in sorted(parciais.items())
    )
    return linhas


def _finalidades_rows(
    classificacoes: tuple[int, ...] = (6, 9),
    finalidades: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    mapa = FINALIDADES_BRANCO if finalidades is None else finalidades
    return [
        {
            "CODCLASSIFICACAO_COR": classe,
            "CODFINALIDADE": codigo,
            "DESCRICAO_FINALIDADE": descricao,
        }
        for classe in classificacoes
        for codigo, descricao in sorted(mapa.items())
    ]


# --------------------------------------------------------------------------
# Smoke: estrutura da automação
# --------------------------------------------------------------------------


def test_manifest_valido() -> None:
    manifest_path = AUTOMATION_DIR / "automation.manifest.json"
    assert manifest_path.exists(), "automation.manifest.json ausente"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == "ORB-07"
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
    assert (AUTOMATION_DIR / "extract_orb.py").exists()
    assert (AUTOMATION_DIR / "validators.py").exists()
    assert (AUTOMATION_DIR / "format_message.py").exists()
    assert (AUTOMATION_DIR / "test_orb_simulation.py").exists()


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
        (AUTOMATION_DIR / "SQL-ObsRestricaoBranco.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert "SELECT *" not in sql, "SELECT * reprova no Test-SqlPerformance"
    assert "CODIGO_FLUXO = 204" not in sql
    assert "OB.STATUS = 1" in sql
    assert "OBMONTADA = '0'" in sql
    assert "VW_EXC_OB_PROD_CLASS_COR" in sql
    assert "CD_CLASSIFICACAO_COR IN (6, 9)" in sql
    assert "GROUP BY V.NR_OB" in sql
    assert "CODIGO_COR_TINGIMENTO" in sql
    assert "TOTAL_PECAS" in sql
    assert "CODIGO_ARTIGO_CRU" in sql
    # Entrega e filial destino: mesmos campos da CTE ENTREGA_OB de OBs Paradas Fase
    assert "DT_ENTREGA" in sql
    assert "NOMEFANTASIA" in sql
    assert "IDFILIALRESPONSAVEL" in sql


def test_sql_obs_protege_conversao_de_data_de_entrega() -> None:
    """Regressão: EXPEDIREM é texto livre; uma linha inválida derrubava o lote.

    ``TO_DATE`` sem proteção levanta ORA-01861/ORA-01847 e mata a extração inteira
    (exit 1 → ``Exit-WithCode 3``) por um campo apenas informativo. A conversão
    tolerante degrada a linha ruim para ``NULL``, caminho já suportado por
    ``coerce_ob_row`` e ``priorizar_obs``.
    """
    sql = (
        (AUTOMATION_DIR / "SQL-ObsRestricaoBranco.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert (
        "TO_DATE(IPC.EXPEDIREM, 'YYYYMMDD')" not in sql
    ), "conversão sem proteção: uma única linha inválida derruba a extração inteira"
    assert "DEFAULT NULL ON CONVERSION ERROR" in sql


def test_sql_obs_filtra_pedido_comercial_terminado_em_r_ou_s() -> None:
    sql = (
        (AUTOMATION_DIR / "SQL-ObsRestricaoBranco.sql")
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
        (AUTOMATION_DIR / "SQL-EstoqueFinalidadesBranco.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert "SELECT *" not in sql
    assert "CODIGO_DEPOSITO = 95" in sql
    # Regressão da subcontagem de 26/08/2026: as finalidades aceitas NÃO podem
    # voltar a ser fixas no SQL. Vêm por bind, derivadas de COR_FINALIDADE — o
    # conjunto fixo {3, 4} descartava a finalidade 1 (SEM RESTRIÇÃO), maioria do
    # estoque do depósito, e o saldo anunciado saía menor que o físico.
    assert "GPC.FINALIDADE IN (3, 4)" not in sql
    assert "GPC.FINALIDADE IN (/*FIN_BINDS*/)" in sql
    assert "GROUPING SETS" in sql
    assert "GROUPING(GPC.FINALIDADE)" in sql
    assert "STPECAPRODUTO IN (0, 16, 18)" in sql
    assert "COUNT(DISTINCT GPP.IDPECASPRODUTO)" in sql
    # Regressão: TIPO_FINALIDADE_FIO e ITENS_ESTOQUE são filtros de existência sem
    # coluna projetada. Como INNER JOIN eles inflavam QTD_LINHAS_BRUTAS e disparavam
    # WARN permanente de fan-out em _fetch_estoque, esvaziando o sinal de auditoria.
    assert "JOIN SGTPRD.TIPO_FINALIDADE_FIO" not in sql
    assert "JOIN SGTPRD.ITENS_ESTOQUE" not in sql
    assert "EXISTS" in sql
    assert "TIPO_FINALIDADE_FIO" in sql
    assert "ITENS_ESTOQUE" in sql


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
    assert relatorio.schema_ok is False
    assert "TOTAL_PECAS" in relatorio.problemas[0]


def test_validate_ob_query_schema_ok_nao_depende_do_texto_da_mensagem() -> None:
    """Regressao: extract_orb.py decidia abortar (SchemaInvalidoError) checando a
    substring 'Colunas obrigatorias ausentes' na mensagem de erro — se o texto
    mudasse, o abort silenciosamente parava de disparar. `schema_ok` e' a fonte
    estrutural dessa decisao agora, independente de qualquer redacao de mensagem."""
    v = _validators()
    colunas = [c for c in v.COLUNAS_OB_OBRIGATORIAS if c != "TOTAL_PECAS"]
    relatorio = v.validate_ob_query(colunas, [_ob_row()])
    assert relatorio.schema_ok is False  # decisao de abortar nao depende do texto

    # Problema de LINHA (nao de schema) nao pode ser confundido com schema quebrado.
    relatorio_linha = v.validate_ob_query(
        list(_ob_row().keys()), [_ob_row(NUMERO_OB=1, TOTAL_PECAS=0)]
    )
    assert relatorio_linha.ok is False
    assert relatorio_linha.schema_ok is True


def test_validate_ob_query_limita_amostra_a_tres() -> None:
    v = _validators()
    rows = [_ob_row(NUMERO_OB=i) for i in range(10)]
    relatorio = v.validate_ob_query(list(rows[0].keys()), rows)
    assert len(relatorio.amostra) == 3


def test_validate_ob_query_devolve_obs_ja_coagidas() -> None:
    """relatorio.obs poupa o chamador de rodar coerce_ob_row de novo sobre o
    retorno cru — extract_orb.py e a simulação consomem só este campo."""
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
        ({"CD_CLASSIFICACAO_COR": 10}, "CD_CLASSIFICACAO_COR"),
        ({"CD_CLASSIFICACAO_COR": 17}, "CD_CLASSIFICACAO_COR"),
        ({"CD_CLASSIFICACAO_COR": 18}, "CD_CLASSIFICACAO_COR"),
        ({"CD_CLASSIFICACAO_COR": None}, "CD_CLASSIFICACAO_COR"),
        ({"QTD_CLASSIFICACOES_COR": 2}, "QTD_CLASSIFICACOES_COR"),
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


def test_coerce_ob_row_aceita_branco_2_fibras() -> None:
    v = _validators()
    ob = v.coerce_ob_row(
        _ob_row(CD_CLASSIFICACAO_COR=9, DS_CLASSIFICACAO_COR="BRANCO 2 FIBRAS")
    )
    assert ob.codigo_classificacao_cor == 9


def test_cor_00001_nao_substitui_classificacao_valida() -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.coerce_ob_row(
            _ob_row(
                CODIGO_COR_TINGIMENTO="00001",
                CD_CLASSIFICACAO_COR=10,
                DS_CLASSIFICACAO_COR="ESTAMPADO COR CLARA",
            )
        )


def test_coerce_ob_row_preserva_artigo_cru_como_texto() -> None:
    """CDARTIGOCRU é texto no Oracle e chega com zeros à esquerda ('00489')."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(CODIGO_ARTIGO_CRU="00489"))
    assert ob.codigo_artigo_cru == "00489"


def test_coerce_ob_row_aceita_artigo_cru_alfanumerico() -> None:
    """Regressão: `ART.CDARTIGOCRU` é alfanumérico e '0A231' ocorre em produção.

    Coagir o campo para int levantava `DadoIncompletoError` e descartava a OB
    inteira — 3 das 11 OBs do primeiro lote real da ORB-07 (27%), todas com
    estoque e nunca avisadas. O campo é puramente cosmético: não entra em
    filtro, prioridade, alocação nem idempotência.
    """
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(CODIGO_ARTIGO_CRU="0A231"))
    assert ob.codigo_artigo_cru == "0A231"


def test_coerce_ob_row_trata_artigo_cru_em_branco_como_ausente() -> None:
    """Mesmo padrão de `codigo_cor_tingimento`/`nome_cliente`: vazio vira None."""
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
    unicas, duplicados, divergencias = v.dedupe_obs(obs)
    assert [ob.id_ob for ob in unicas] == [1, 2]
    assert duplicados == [1]
    assert divergencias == [], "linhas identicas nao divergem"


def test_dedupe_obs_com_dt_entrega_divergente_mantem_a_de_menor_data_deterministicamente() -> (
    None
):
    """Regressao: a query projeta DT_ENTREGA/ID_CLIENTE/NOME_CLIENTE dos joins de
    pedido comercial, entao duplicatas por NUMERO_OB podem ter dt_entrega diferente.
    O resultado nao pode depender da ordem do cursor Oracle (serialize_rows so
    ordena por NUMERO_OB) — a linha de menor dt_entrega vence, nas duas ordens."""
    v = _validators()
    mais_cedo = v.coerce_ob_row(_ob_row(NUMERO_OB=1, DT_ENTREGA="2026-07-10T00:00:00"))
    mais_tarde = v.coerce_ob_row(_ob_row(NUMERO_OB=1, DT_ENTREGA="2026-07-20T00:00:00"))

    unicas_a, duplicados_a, _ = v.dedupe_obs([mais_cedo, mais_tarde])
    unicas_b, duplicados_b, _ = v.dedupe_obs([mais_tarde, mais_cedo])

    assert [ob.dt_entrega for ob in unicas_a] == ["2026-07-10T00:00:00"]
    assert [ob.dt_entrega for ob in unicas_b] == ["2026-07-10T00:00:00"]
    assert duplicados_a == [1]
    assert duplicados_b == [1]


def test_dedupe_obs_mantem_a_linha_de_loja_quando_a_duplicata_diverge_no_cliente() -> (
    None
):
    """Regressão: `dedupe_obs` ordenava só por (sem_data, data), enquanto
    `priorizar_obs` ordena por (é_matriz, sem_data, data, id_ob).

    Quando as linhas duplicadas divergiam em `id_cliente`, o dedupe decidia antes
    e podia manter a linha da MATRIZ — rebaixando uma OB de loja, que a prioridade
    então herdava. Agora as duas consomem a mesma `chave_prioridade`.
    """
    v = _validators()
    loja = v.coerce_ob_row(
        _ob_row(
            NUMERO_OB=2001,
            ID_CLIENTE=7,
            NOME_CLIENTE="LOJA CURITIBA",
            DT_ENTREGA="2026-09-20T00:00:00",
        )
    )
    matriz = v.coerce_ob_row(
        _ob_row(
            NUMERO_OB=2001,
            ID_CLIENTE=1,
            NOME_CLIENTE="CR-MATRIZ/PR",
            DT_ENTREGA="2026-09-05T00:00:00",
        )
    )

    for entrada in ([loja, matriz], [matriz, loja]):
        unicas, duplicados, divergencias = v.dedupe_obs(entrada)
        assert [ob.nome_cliente for ob in unicas] == ["LOJA CURITIBA"]
        assert duplicados == [2001]
        assert len(divergencias) == 1
        assert set(divergencias[0].campos) == {
            "id_cliente",
            "nome_cliente",
            "dt_entrega",
        }
        assert "LOJA CURITIBA" in divergencias[0].mantida
        assert "CR-MATRIZ/PR" in divergencias[0].descartada


def test_dedupe_e_prioridade_nao_podem_divergir() -> None:
    """A escolha do dedupe tem de ser a primeira colocada de `priorizar_obs`.

    Trava de fonte única: se alguém alterar a regra de prioridade sem alterar o
    dedupe (ou vice-versa), este teste reprova.
    """
    v = _validators()
    linhas = [
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=2001, ID_CLIENTE=1, DT_ENTREGA="2026-09-05T00:00:00")
        ),
        v.coerce_ob_row(
            _ob_row(NUMERO_OB=2001, ID_CLIENTE=7, DT_ENTREGA="2026-09-20T00:00:00")
        ),
    ]
    mantida = v.dedupe_obs(linhas)[0][0]
    assert mantida == v.priorizar_obs(linhas)[0]
    assert v.chave_prioridade(mantida) == min(v.chave_prioridade(o) for o in linhas)


def test_dedupe_obs_nao_reporta_divergencia_para_linhas_identicas() -> None:
    """O log de divergência só deve aparecer no caso que nunca ocorreu em produção."""
    v = _validators()
    obs = [v.coerce_ob_row(_ob_row(NUMERO_OB=1)) for _ in range(2)]
    assert v.dedupe_obs(obs)[2] == []


def test_dedupe_obs_sem_duplicata_e_noop() -> None:
    v = _validators()
    obs = [v.coerce_ob_row(_ob_row(NUMERO_OB=i)) for i in (1, 2, 3)]
    unicas, duplicados, divergencias = v.dedupe_obs(obs)
    assert unicas == obs
    assert duplicados == []
    assert divergencias == []


# --------------------------------------------------------------------------
# Validação 2 — query de estoque
# --------------------------------------------------------------------------


def test_validate_estoque_rows_detecta_fan_out_de_join() -> None:
    """Regressão do risco central: ITENS_ESTOQUE/TIPO_FINALIDADE_FIO entram só como
    filtro; se duplicarem linhas, o COUNT simples do spec superestimaria o estoque
    e a OB seria notificada sem peça. A contagem distinta é a autoritativa."""
    v = _validators()
    estoque = v.validate_estoque_rows(
        _estoque_rows(total=75, brutas=150), FINALIDADES_BRANCO
    )
    assert estoque.quantidade == 75
    assert estoque.tem_fan_out is True


def test_validate_estoque_rows_sem_fan_out() -> None:
    v = _validators()
    assert (
        v.validate_estoque_rows(_estoque_rows(), FINALIDADES_BRANCO).tem_fan_out
        is False
    )


def test_validate_estoque_rows_conta_finalidade_1_sem_restricao() -> None:
    """Regressão da subcontagem de 26/08/2026.

    A finalidade 1 (SEM RESTRIÇÃO) é compatível com as classes brancas em
    COR_FINALIDADE e é a maioria do estoque do depósito 95. Enquanto o SQL
    filtrava {3, 4}, ela ficava fora do saldo e a mensagem prometia à Expedição
    menos peças do que existiam fisicamente.
    """
    v = _validators()
    estoque = v.validate_estoque_rows(
        _estoque_rows(total=1855, por_finalidade={1: 1402, 3: 441, 12: 12}),
        FINALIDADES_BRANCO,
    )
    assert estoque.quantidade == 1855
    assert estoque.restricoes_disponiveis == (
        (1, "SEM RESTRIÇÃO"),
        (3, "CORES CLARAS"),
        (12, "REMOÇÃO DE ÓLEO"),
    )


def test_validate_estoque_rows_ignora_finalidade_sem_peca() -> None:
    v = _validators()
    estoque = v.validate_estoque_rows(
        _estoque_rows(total=40, por_finalidade={3: 40, 4: 0}), FINALIDADES_BRANCO
    )
    assert estoque.restricoes_disponiveis == ((3, "CORES CLARAS"),)


def test_validate_estoque_rows_usa_total_distinto_e_nao_a_soma_das_parciais() -> None:
    """Peça com mais de uma finalidade cadastrada apareceria duas vezes numa soma;
    o saldo autoritativo é a linha total do GROUPING SETS."""
    v = _validators()
    estoque = v.validate_estoque_rows(
        _estoque_rows(total=100, brutas=120, por_finalidade={3: 80, 4: 40}),
        FINALIDADES_BRANCO,
    )
    assert estoque.quantidade == 100


def test_validate_estoque_rows_reprova_total_menor_que_maior_parcial() -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.validate_estoque_rows(
            _estoque_rows(total=10, por_finalidade={3: 11}), FINALIDADES_BRANCO
        )


def test_validate_estoque_rows_reprova_total_maior_que_a_soma_das_parciais() -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.validate_estoque_rows(
            _estoque_rows(total=50, por_finalidade={3: 10, 4: 10}), FINALIDADES_BRANCO
        )


def test_validate_estoque_rows_reprova_finalidade_fora_do_conjunto_pedido() -> None:
    """Query e mapa de descrições saindo de conjuntos diferentes é falha, não WARN."""
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.validate_estoque_rows(
            _estoque_rows(total=5, por_finalidade={5: 5}), FINALIDADES_BRANCO
        )


def test_validate_estoque_rows_reprova_ausencia_da_linha_total() -> None:
    v, e = _validators(), _errors()
    linhas = [r for r in _estoque_rows() if r["EH_TOTAL"] != 1]
    with pytest.raises(e.DadoIncompletoError):
        v.validate_estoque_rows(linhas, FINALIDADES_BRANCO)


def test_validate_estoque_rows_reprova_schema_quebrado() -> None:
    v, e = _validators(), _errors()
    linhas = _estoque_rows()
    for linha in linhas:
        del linha["QTD_PECAS_DISPONIVEIS"]
    with pytest.raises(e.SchemaInvalidoError):
        v.validate_estoque_rows(linhas, FINALIDADES_BRANCO)


def test_validate_estoque_rows_reprova_quantidade_negativa() -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.validate_estoque_rows(
            _estoque_rows(total=-1, por_finalidade={4: -1}), FINALIDADES_BRANCO
        )


# --------------------------------------------------------------------------
# Validação 2b — finalidades compatíveis (COR_FINALIDADE)
# --------------------------------------------------------------------------


def test_validate_finalidades_query_resolve_o_conjunto_do_cadastro() -> None:
    """O conjunto vem do ERP, não do código: é isso que impede a subcontagem voltar."""
    v = _validators()
    assert v.validate_finalidades_query((6, 9), _finalidades_rows()) == (
        FINALIDADES_BRANCO
    )


def test_validate_finalidades_query_inclui_a_finalidade_1() -> None:
    v = _validators()
    assert 1 in v.validate_finalidades_query((6, 9), _finalidades_rows())


def test_validate_finalidades_query_reprova_classificacao_sem_cadastro() -> None:
    v, e = _validators(), _errors()
    with pytest.raises(e.DadoIncompletoError):
        v.validate_finalidades_query((6, 9), _finalidades_rows(classificacoes=(6,)))


def test_validate_finalidades_query_reprova_conjuntos_divergentes() -> None:
    """Classes brancas com conjuntos diferentes tornariam o saldo por reduzido
    ambíguo (a query de estoque não sabe a classificação da OB) — falha observável."""
    v, e = _validators(), _errors()
    rows = _finalidades_rows(classificacoes=(6,)) + _finalidades_rows(
        classificacoes=(9,), finalidades={1: "SEM RESTRIÇÃO"}
    )
    with pytest.raises(e.DadoIncompletoError):
        v.validate_finalidades_query((6, 9), rows)


def test_validate_finalidades_query_reprova_descricao_vazia() -> None:
    v, e = _validators(), _errors()
    rows = _finalidades_rows(finalidades={1: "   "})
    with pytest.raises(e.DadoIncompletoError):
        v.validate_finalidades_query((6, 9), rows)


def test_validate_estoque_query_trata_ausencia_de_linha_como_zero_valido() -> None:
    """GROUP BY não emite linha para código sem peça: é 0 unidades, não um erro."""
    v = _validators()
    resultado = v.validate_estoque_query(999, [], FINALIDADES_BRANCO)
    assert resultado["validado"] is True
    assert resultado["quantidade"] == 0


def test_validate_estoque_query_encontra_o_codigo_certo() -> None:
    v = _validators()
    rows = _estoque_rows(codigo=111, total=10) + _estoque_rows(codigo=222, total=20)
    resultado = v.validate_estoque_query(222, rows, FINALIDADES_BRANCO)
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
        int(chave[1:]): v.validate_estoque_rows(
            _estoque_rows(codigo=int(chave[1:]), total=qtd), FINALIDADES_BRANCO
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


def test_alocar_estoque_deduz_saldo_e_a_ultima_ob_leva_o_resto() -> None:
    """Alocacao sequencial: 90 pecas cobrem as OBs de 50 e 30 por inteiro; a
    terceira (40) leva as 10 que sobraram como cobertura PARCIAL.

    A soma dos alocados nunca passa do estoque — e o que impede prometer a mesma
    peca duas vezes —, mas nenhuma peca restrita fica para tras."""
    v = _validators()
    obs = [
        v.coerce_ob_row(_ob_row(NUMERO_OB=1, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=50)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=2, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=30)),
        v.coerce_ob_row(_ob_row(NUMERO_OB=3, CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=40)),
    ]
    avaliacoes = v.alocar_estoque(obs, _estoques(r100=90))
    assert [a.notificar for a in avaliacoes] == [True, True, True]
    assert [a.disponivel for a in avaliacoes] == [90, 40, 10]
    assert [a.alocado for a in avaliacoes] == [50, 30, 10]
    assert sum(a.alocado for a in avaliacoes) == 90
    assert [a.cobertura_total for a in avaliacoes] == [True, True, False]
    assert avaliacoes[2].faltante == 30
    assert "cobertura parcial" in avaliacoes[2].motivo
    assert "faltam 30" in avaliacoes[2].motivo


def test_alocar_estoque_matriz_so_recebe_o_que_sobra_das_lojas() -> None:
    """Cenario fim-a-fim da regra: a loja consome o estoque primeiro; a matriz
    (mais antiga na fila por entrega) fica com o que sobrar — integral se couber,
    parcial se nao."""
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

    # Estoque 80: cobre a loja (60) por inteiro; a matriz (30) entra com as 20
    # que sobraram, como parcial — a loja continua servida primeiro.
    avaliacoes = v.alocar_estoque(v.priorizar_obs([matriz, loja]), _estoques(r100=80))
    assert [(a.ob.id_ob, a.alocado) for a in avaliacoes] == [(2, 60), (1, 20)]
    assert [a.cobertura_total for a in avaliacoes] == [True, False]

    # Estoque 100: cobre a loja (60) e sobra 40 — a matriz (30) entra integral.
    avaliacoes = v.alocar_estoque(v.priorizar_obs([matriz, loja]), _estoques(r100=100))
    assert [(a.ob.id_ob, a.alocado) for a in avaliacoes] == [(2, 60), (1, 30)]
    assert [a.cobertura_total for a in avaliacoes] == [True, True]


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
    """Saldo zero e o UNICO motivo de nao notificar desde 01/09/2026: sem peca
    restrita no deposito, nao ha nada a escoar e o aviso seria ruido."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(TOTAL_PECAS=50))
    avaliacao = v.alocar_estoque([ob], {})[0]
    assert avaliacao.notificar is False
    assert avaliacao.disponivel == 0
    assert avaliacao.alocado == 0
    assert "sem peca restrita disponivel" in avaliacao.motivo


# --------------------------------------------------------------------------
# State de idempotência — merge_notified_state
# --------------------------------------------------------------------------


def _avaliacao(numero_ob: int, notificar: bool) -> Any:
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(NUMERO_OB=numero_ob, TOTAL_PECAS=50))
    estoques = (
        {
            ob.codigo_reduzido_cru: v.validate_estoque_rows(
                _estoque_rows(codigo=ob.codigo_reduzido_cru, total=75),
                FINALIDADES_BRANCO,
            )
        }
        if notificar
        else {}
    )
    return v.alocar_estoque([ob], estoques)[0]


def _reserva(em: str, reduzido: int | None = 12345, quantidade: int = 50) -> Any:
    modelos = _load_module("models", AUTOMATION_DIR / "models.py")
    return modelos.ReservaNotificacao(
        em=em, codigo_reduzido=reduzido, quantidade=quantidade
    )


def test_merge_notified_state_mantem_ob_avisada_com_estoque_oscilando() -> None:
    """Regressão da correção do review: OB já avisada cujo estoque caiu abaixo
    da necessidade (mas segue na query, não montada) NÃO sai do state — senão
    ela seria re-avisada a cada cruzamento do limiar, com execução horária."""
    v = _validators()
    sem_estoque_agora = _avaliacao(1001, notificar=False)
    anterior = _reserva("2026-07-15T10:00:00")
    estado = v.merge_notified_state(
        {"1001": anterior}, [sem_estoque_agora], [], "2026-07-16T10:00:00"
    )
    assert estado == {"1001": anterior}


def test_merge_notified_state_poda_ob_que_saiu_da_query() -> None:
    """OB montada some da query e do state; se voltar a ficar pendente, avisa de novo.

    É por aqui que a reserva termina no caso normal — a validade de 24h existe só
    para a OB que fica pendente indefinidamente e seguraria o saldo para sempre.
    """
    v = _validators()
    outra = _avaliacao(2002, notificar=True)
    reserva = _reserva("2026-07-15T10:00:00")
    estado = v.merge_notified_state(
        {"1001": reserva, "2002": reserva},
        [outra],
        [],
        "2026-07-16T10:00:00",
    )
    assert estado == {"2002": reserva}


def test_merge_notified_state_registra_a_reserva_da_ob_nova() -> None:
    v = _validators()
    nova = _avaliacao(3003, notificar=True)
    estado = v.merge_notified_state({}, [nova], [nova], "2026-07-16T11:00:00")
    assert estado == {"3003": _reserva("2026-07-16T11:00:00", 12345, 50)}


# --------------------------------------------------------------------------
# Reserva de estoque entre ciclos
# --------------------------------------------------------------------------


def _estoque(reduzido: int, quantidade: int) -> Any:
    v = _validators()
    return v.validate_estoque_rows(
        _estoque_rows(codigo=reduzido, total=quantidade), FINALIDADES_BRANCO
    )


def test_reserva_sobrevive_entre_ciclos_e_nao_promete_a_mesma_peca_duas_vezes() -> None:
    """Regressão do bug central: sem reserva persistente, duas OBs eram anunciadas
    como prontas para as MESMAS peças físicas.

    Ciclo 1 (estoque 60): a OB 1001 (precisa 60) é avisada e reserva as 60.
    Ciclo 2 (estoque caiu para 40): antes, a OB 1002 (precisa 40) via as 40 livres
    e era anunciada — mas a 1001 já tinha prometido peças daquele mesmo saldo.
    """
    v = _validators()
    reduzido = 12345
    ob1 = v.coerce_ob_row(_ob_row(NUMERO_OB=1001, TOTAL_PECAS=60))
    ob2 = v.coerce_ob_row(_ob_row(NUMERO_OB=1002, TOTAL_PECAS=40))

    # Ciclo 1
    avaliacoes1 = v.alocar_estoque([ob1, ob2], {reduzido: _estoque(reduzido, 60)}, {})
    novas1 = [a for a in avaliacoes1 if a.notificar]
    assert [a.ob.id_ob for a in novas1] == [1001]
    estado = v.merge_notified_state({}, avaliacoes1, novas1, "2026-08-25T08:00:00")

    # Ciclo 2, duas horas depois, com o estoque do depósito já em 40
    agora = "2026-08-25T10:00:00"
    vivas = v.reservas_vivas(estado, agora)
    reservado = v.reservas_por_reduzido(vivas)
    assert reservado == {reduzido: 60}

    avaliacoes2 = v.alocar_estoque(
        [ob1, ob2], {reduzido: _estoque(reduzido, 40)}, reservado
    )
    novas2 = [a for a in avaliacoes2 if a.notificar and str(a.ob.id_ob) not in vivas]
    assert novas2 == [], "1002 não pode ser anunciada sobre peças já prometidas à 1001"


def test_alocar_estoque_nao_desconta_reserva_ja_viva_duas_vezes() -> None:
    """Item 3 da revisão de 26/08/2026: OB já reservada (presente em `ja_reservadas`)
    não pode ter a quantidade dela descontada de novo do saldo — ela já foi
    subtraída via `reservado`/`presos`. Sem a correção, o saldo cai em dobro e uma
    OB nova legítima, que caberia no espaço realmente livre, fica de fora.

    Estoque 100 do reduzido; OBs 1001 e 1002 já notificadas em ciclo anterior,
    30 un cada (reservado = {reduzido: 60} -> saldo livre real = 40). A OB nova
    de 30 un cabe nesses 40 livres.
    """
    v = _validators()
    reduzido = 12345
    ob1 = v.coerce_ob_row(_ob_row(NUMERO_OB=1001, TOTAL_PECAS=30))
    ob2 = v.coerce_ob_row(_ob_row(NUMERO_OB=1002, TOTAL_PECAS=30))
    ob_nova = v.coerce_ob_row(_ob_row(NUMERO_OB=1003, TOTAL_PECAS=30))

    vivas = {
        "1001": _reserva("2026-08-25T08:00:00", reduzido, 30),
        "1002": _reserva("2026-08-25T08:00:00", reduzido, 30),
    }
    reservado = v.reservas_por_reduzido(vivas)
    assert reservado == {reduzido: 60}

    avaliacoes = v.alocar_estoque(
        [ob1, ob2, ob_nova], {reduzido: _estoque(reduzido, 100)}, reservado, vivas
    )
    por_id = {a.ob.id_ob: a for a in avaliacoes}
    assert por_id[1001].notificar is True
    assert por_id[1002].notificar is True
    assert por_id[1003].notificar is True, "OB nova cabia nos 40 realmente livres"


def test_alocar_estoque_reserva_degradada_compete_normalmente_pelo_saldo() -> None:
    """Achado 4 da revisão de 26/08/2026: reserva DEGRADADA (formato legado ou
    entrada malformada — `reduzido=None`/`quantidade=0`, ver `parse_notified_state`)
    NÃO é descontada em `presos` (reservas_por_reduzido a ignora). Se `alocar_estoque`
    também pulasse a dedução para ela por estar em `ja_reservadas`, o saldo dessa
    OB nunca seria descontado em lugar nenhum: uma OB nova do mesmo reduzido veria
    o saldo bruto e seria aprovada para as MESMAS peças físicas.

    Estoque 50 do reduzido; OB 1001 já "reservada" (mas com quantidade
    desconhecida, registrada como 0) e OB nova 1002 também precisa de 50.
    Com a correção, 1001 compete normalmente pelo saldo (consegue as 50 e as
    deduz), e 1002 não tem mais estoque disponível — sem a correção, ambas
    seriam aprovadas para o mesmo saldo de 50.
    """
    v = _validators()
    reduzido = 12345
    ob1 = v.coerce_ob_row(_ob_row(NUMERO_OB=1001, TOTAL_PECAS=50))
    ob2 = v.coerce_ob_row(_ob_row(NUMERO_OB=1002, TOTAL_PECAS=50))

    vivas = {"1001": _reserva("2026-08-25T08:00:00", reduzido=None, quantidade=0)}
    reservado = v.reservas_por_reduzido(vivas)
    assert reservado == {}, "reserva degradada nao entra em presos"

    avaliacoes = v.alocar_estoque(
        [ob1, ob2], {reduzido: _estoque(reduzido, 50)}, reservado, vivas
    )
    por_id = {a.ob.id_ob: a for a in avaliacoes}
    assert por_id[1001].notificar is True, "compete normalmente e consegue o saldo"
    assert por_id[1002].notificar is False, (
        "saldo ja foi consumido por 1001 — sem a correcao, ambas seriam "
        "aprovadas para as mesmas 50 pecas fisicas"
    )


def test_reserva_expira_e_a_ob_volta_a_concorrer_pelo_estoque() -> None:
    """Expiração remove a OB do `notified` POR COMPLETO — ela volta a concorrer e
    pode ser re-anunciada. Liberar o saldo mantendo a OB no state recriaria o bug
    original de forma invisível."""
    v = _validators()
    estado = {"1001": _reserva("2026-08-25T08:00:00", 12345, 60)}

    dentro = v.reservas_vivas(estado, "2026-08-26T07:59:00")
    assert dentro == estado
    assert v.reservas_por_reduzido(dentro) == {12345: 60}

    depois = v.reservas_vivas(estado, "2026-08-26T08:00:01")
    assert depois == {}, "após 24h a OB sai do state inteiro, não só a reserva"
    assert v.reservas_por_reduzido(depois) == {}


def test_janela_de_reserva_e_de_24_horas() -> None:
    assert _validators().JANELA_RESERVA_HORAS == 24


def test_reservas_por_reduzido_soma_e_ignora_reserva_desconhecida() -> None:
    v = _validators()
    estado = {
        "1": _reserva("2026-08-25T08:00:00", 12345, 60),
        "2": _reserva("2026-08-25T08:00:00", 12345, 40),
        "3": _reserva("2026-08-25T08:00:00", 999, 5),
        "4": _reserva("2026-08-25T08:00:00", None, 0),  # entrada legada
    }
    assert v.reservas_por_reduzido(estado) == {12345: 100, 999: 5}


def test_alocar_estoque_desconta_a_reserva_do_saldo_exibido() -> None:
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(TOTAL_PECAS=50))
    reduzido = ob.codigo_reduzido_cru
    avaliacao = v.alocar_estoque(
        [ob], {reduzido: _estoque(reduzido, 75)}, {reduzido: 40}
    )[0]
    assert avaliacao.disponivel == 35, "75 no depósito - 40 já reservadas"
    # Notificada como parcial sobre as 35 livres — jamais sobre as 40 que outra
    # OB já prometeu.
    assert avaliacao.notificar is True
    assert avaliacao.alocado == 35
    assert avaliacao.faltante == 15


def test_alocar_estoque_nao_produz_saldo_negativo() -> None:
    """Reserva maior que o saldo atual (estoque caiu) satura em zero."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(TOTAL_PECAS=1))
    reduzido = ob.codigo_reduzido_cru
    avaliacao = v.alocar_estoque(
        [ob], {reduzido: _estoque(reduzido, 10)}, {reduzido: 999}
    )[0]
    assert avaliacao.disponivel == 0


# --------------------------------------------------------------------------
# Formato do state em disco — migração do arquivo vivo em produção
# --------------------------------------------------------------------------

# Cópia literal do orb_state.json que está em produção no momento da mudança de
# formato: 6 OBs notificadas no formato ANTIGO (valor = carimbo em texto). Se o
# código novo lesse isto como state vazio, o grupo da Expedição receberia 6
# avisos duplicados na primeira execução após o deploy.
_STATE_LEGADO_PRODUCAO = {
    "notified": {
        "185719": "2026-08-25T16:54:40.000000",
        "185720": "2026-08-25T16:54:40.000000",
        "185721": "2026-08-25T16:54:40.000000",
        "185722": "2026-08-25T16:54:40.000000",
        "185723": "2026-08-25T16:54:40.000000",
        "185724": "2026-08-25T16:54:40.000000",
    },
    "updated_at": "2026-08-25T17:00:18.816171",
}


def test_parse_notified_state_le_o_formato_legado_sem_re_notificar() -> None:
    v = _validators()
    estado = v.parse_notified_state(_STATE_LEGADO_PRODUCAO["notified"])

    assert len(estado) == 6, "as 6 OBs já avisadas seguem no state"
    assert sorted(estado) == [
        "185719",
        "185720",
        "185721",
        "185722",
        "185723",
        "185724",
    ]
    for reserva in estado.values():
        assert reserva.em == "2026-08-25T16:54:40.000000"
        # Reserva de quantidade DESCONHECIDA: preserva a idempotência sem
        # inventar um saldo que o arquivo antigo não registrou.
        assert reserva.codigo_reduzido is None
        assert reserva.quantidade == 0
    assert v.reservas_por_reduzido(estado) == {}


def test_extract_orb_le_o_state_legado_do_disco(tmp_path: Any) -> None:
    """Caminho REAL de leitura (`_read_notified`) contra uma cópia do arquivo vivo."""
    extract = _load_module("extract_orb_state", AUTOMATION_DIR / "extract_orb.py")
    state_file = tmp_path / "orb_state.json"
    state_file.write_text(
        json.dumps(_STATE_LEGADO_PRODUCAO, ensure_ascii=False), encoding="utf-8"
    )

    estado = extract._read_notified(str(state_file))

    assert sorted(estado) == [
        "185719",
        "185720",
        "185721",
        "185722",
        "185723",
        "185724",
    ]


def test_read_notified_trata_json_invalido_como_vazio(tmp_path: Any) -> None:
    """Corrupção real continua sendo tratada como state vazio (re-notifica)."""
    extract = _load_module("extract_orb_state", AUTOMATION_DIR / "extract_orb.py")
    state_file = tmp_path / "orb_state.json"
    state_file.write_text("{nao é json", encoding="utf-8")
    assert extract._read_notified(str(state_file)) == {}


def _stub_extract_ate_fetch_obs(
    extract: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    fake_fetch_obs: Any,
    tmp_path: Any,
) -> None:
    """Substitui a camada Oracle de `extract_orb.py` por dublês, preservando a
    lógica real de `extract()` a partir da chamada a `_fetch_obs`.

    `resolve_oracle_credentials`/`init_thick_mode` nunca são exercitados por
    este arquivo de testes (ver docstring do módulo) — aqui eles só precisam
    não travar/levantar, pois o comportamento sob teste está inteiramente
    DEPOIS deles, na decisão sobre `obs`/`resumo.falhas`.

    `RESULT_FILE` é redirecionado para `tmp_path` AQUI (e não em cada teste)
    porque todo teste que chama `extract()` passa por este helper: sem o
    redirecionamento, `_write_result`/`_write_counts` gravam em
    `OBs Restricao Branco/orb_result.json` — o arquivo VIVO da automação em
    produção. Um `pytest` rodando entre o extract e o envio de um ciclo real
    faz o `run.ps1` ler um payload de teste, inclusive o `record_counts` que
    alimenta o evento `execution.end` (incidente observado em 01/09/2026).
    """
    monkeypatch.setattr(
        extract, "resolve_oracle_credentials", lambda log, exec_id: object()
    )
    monkeypatch.setattr(extract, "init_thick_mode", lambda creds, log, exec_id: None)
    monkeypatch.setattr(extract, "_fetch_obs", fake_fetch_obs)
    monkeypatch.setattr(extract, "RESULT_FILE", str(tmp_path / "orb_result.json"))
    monkeypatch.setattr(extract.sys, "argv", ["extract_orb.py", "TESTE"])


def test_extract_aborta_sem_tocar_state_quando_todas_as_linhas_falham_validacao(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Achado 3 da revisão de 26/08/2026: linhas que VIERAM da query mas
    nenhuma sobreviveu a `coerce_ob_row` não podem ser tratadas como "nada a
    notificar" (exit 2) — sem a correção, `extract()` commitava
    `orb_state.json.tmp` vazio por cima do state real, apagando TODAS as
    reservas de idempotência vivas; quando o dado normalizasse, as OBs já
    avisadas seriam re-anunciadas ao grupo.
    """
    extract = _load_module("extract_orb_state", AUTOMATION_DIR / "extract_orb.py")
    state_file = tmp_path / "orb_state.json"
    state_original = json.dumps(
        {"notified": {"185722": {"em": "x", "reduzido": 26, "reservado": 55}}}
    )
    state_file.write_text(state_original, encoding="utf-8")
    monkeypatch.setattr(extract, "STATE_FILE", str(state_file))

    def fake_fetch_obs(creds: Any, exec_id: str, resumo: Any) -> list[Any]:
        resumo.falhas.append("OB #1: CD_CLASSIFICACAO_COR=7, esperado 6 ou 9")
        return []

    _stub_extract_ate_fetch_obs(extract, monkeypatch, fake_fetch_obs, tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        extract.extract()

    assert excinfo.value.code == 1
    assert not (
        tmp_path / "orb_state.json.tmp"
    ).exists(), "sem a correcao, este exit(1) nao pode gravar state.tmp"
    assert (
        state_file.read_text(encoding="utf-8") == state_original
    ), "state original precisa permanecer intocado"


def test_extract_trata_query_realmente_vazia_como_nada_a_notificar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Guarda contra regressão do caminho legítimo: query sem nenhuma OB
    (`resumo.falhas` vazio) continua saindo com exit(2) e commitando state
    vazio — não deve ser confundida com o caso de validação acima."""
    extract = _load_module("extract_orb_state", AUTOMATION_DIR / "extract_orb.py")
    state_file = tmp_path / "orb_state.json"
    monkeypatch.setattr(extract, "STATE_FILE", str(state_file))

    def fake_fetch_obs(creds: Any, exec_id: str, resumo: Any) -> list[Any]:
        return []

    _stub_extract_ate_fetch_obs(extract, monkeypatch, fake_fetch_obs, tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        extract.extract()

    assert excinfo.value.code == 2
    assert (tmp_path / "orb_state.json.tmp").exists()
    # Prova de que `_write_counts` foi redirecionado: o payload do ciclo saiu em
    # tmp_path, nao por cima do orb_result.json vivo da automacao.
    assert (tmp_path / "orb_result.json").exists()


def test_record_counts_usa_chaves_canonicas_e_read_conta_linhas_cruas() -> None:
    """F3: `read` = linhas que vieram do Oracle (não o total pós-filtro), e as
    linhas descartadas por campo obrigatório nulo entram como `rejected` — nunca
    `failures`, que um agente de monitoramento lê como erro de execução."""
    extract = _load_module("extract_orb_state", AUTOMATION_DIR / "extract_orb.py")
    resumo = extract.ResumoExecucao()
    resumo.total_lidas = 14
    resumo.total_obs = 9
    resumo.total_notificaveis = 2
    resumo.total_sem_estoque = 9
    resumo.falhas = ["OB #185248: CD_CLASSIFICACAO_COR nulo"] * 5

    rc = extract._record_counts(resumo, novas_count=1)

    assert "failures" not in rc
    assert rc["read"] == 14
    assert rc["validated"] == 9
    assert rc["rejected"] == 5
    assert rc["qualified"] == 2
    assert rc["notified"] == 1
    assert rc["skipped"] == 9
    assert rc["suppressed"] == 1
    assert all(isinstance(v, int) and v >= 0 for v in rc.values())


def test_record_counts_read_cai_para_total_obs_quando_total_lidas_ausente() -> None:
    """Caminhos de saída antecipada não populam `total_lidas`; `read` degrada
    para `total_obs` em vez de reportar 0 linhas lidas."""
    extract = _load_module("extract_orb_state", AUTOMATION_DIR / "extract_orb.py")
    resumo = extract.ResumoExecucao()
    resumo.total_obs = 3
    rc = extract._record_counts(resumo, novas_count=0)
    assert rc["read"] == 3


def test_state_faz_round_trip_no_formato_novo() -> None:
    v = _validators()
    estado = {"1001": _reserva("2026-08-25T08:00:00", 26, 55)}
    serializado = v.serialize_notified_state(estado)
    assert serializado == {
        "1001": {"em": "2026-08-25T08:00:00", "reduzido": 26, "reservado": 55}
    }
    assert v.parse_notified_state(json.loads(json.dumps(serializado))) == estado


def test_parse_notified_state_degrada_entrada_malformada_sem_perder_a_ob() -> None:
    """Entrada corrompida vira reserva desconhecida — sumir dela re-avisaria a OB."""
    v = _validators()
    estado = v.parse_notified_state(
        {"1001": {"em": "2026-08-25T08:00:00", "reduzido": "xx", "reservado": "yy"}}
    )
    assert set(estado) == {"1001"}
    assert estado["1001"].quantidade == 0
    assert estado["1001"].codigo_reduzido is None


# --------------------------------------------------------------------------
# Queries — parametrização segura
# --------------------------------------------------------------------------


def test_build_estoque_sql_usa_bind_e_nao_interpola_valores() -> None:
    """Zero-Trust: o valor nunca entra na string SQL."""
    q = _queries()
    sql, params = q.build_estoque_sql([12345, 678], [1, 3, 4])
    assert q.IN_BINDS_MARKER not in sql
    assert q.FIN_BINDS_MARKER not in sql
    assert ":C0, :C1" in sql
    assert ":F0, :F1, :F2" in sql
    # As finalidades também são bind: o conjunto vem de COR_FINALIDADE em tempo
    # de execução, nunca interpolado nem fixo no .sql (subcontagem de 26/08/2026).
    assert params == {"C0": 12345, "C1": 678, "F0": 1, "F1": 3, "F2": 4}
    assert "12345" not in sql.split("GROUP BY")[0].split("IN (")[-1]


def test_build_estoque_sql_rejeita_lista_vazia_ou_grande_demais() -> None:
    q = _queries()
    with pytest.raises(ValueError):
        q.build_estoque_sql([], [1])
    with pytest.raises(ValueError):
        q.build_estoque_sql(list(range(q.MAX_IN_BINDS + 1)), [1])


def test_chunk_codigos_respeita_o_limite_do_oracle() -> None:
    """ORA-01795: lista IN não aceita mais de 1000 expressões."""
    q = _queries()
    lotes = q.chunk_codigos(list(range(2000)))
    assert len(lotes) == 3
    assert all(len(lote) <= q.MAX_IN_BINDS for lote in lotes)
    assert sum(len(lote) for lote in lotes) == 2000


def test_sql_diagnostico_classifica_aceites_e_rejeicoes() -> None:
    q = _queries()
    sql = Path(q.SQL_DIAGNOSTICO_CLASSIFICACOES_PATH).read_text(encoding="utf-8")
    assert "VW_EXC_OB_PROD_CLASS_COR" in sql
    assert "CD_CLASSIFICACAO_COR IN (6, 9)" in sql
    assert "THEN 'ACEITA'" in sql
    assert "ELSE 'REJEITA'" in sql
    assert "COUNT(DISTINCT OB.NUMERO_OB)" in sql


# --------------------------------------------------------------------------
# Mensagem
# --------------------------------------------------------------------------


def _row_mensagem(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "NUMERO_OB": 1001,
        "CODIGO_REDUZIDO_CRU": 12345,
        "CODIGO_ARTIGO_CRU": 489,
        "CODIGO_FLUXO": 102,
        "CODIGO_COR_TINGIMENTO": "00001",
        "CD_CLASSIFICACAO_COR": 6,
        "DS_CLASSIFICACAO_COR": "BRANCO",
        "RESTRICOES_DISPONIVEIS": [
            {"codigo": 4, "descricao": "BRANCO"},
        ],
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
    assert "Depósito 95 - OBs Restrição Branco" in msg
    assert "*OB: 1001*" in msg
    assert "Artigo: 489" in msg
    assert "Fluxo: 102" in msg
    assert "Cor programada: 01" in msg
    assert "Classificação: BRANCO" in msg
    assert "Restrição da peça: 4 — BRANCO" in msg
    assert "Reduzido: 12345" in msg
    assert "Quantidade necessária: 50 peças" in msg
    assert "Estoque disponível: 75 peças" in msg
    assert "Data de entrega: 20/07/2026" in msg
    assert "Filial destino: CR-LOJA BLUMENAU" in msg


def test_build_message_explica_o_estoque_ja_descontado_das_obs_anteriores() -> None:
    """Várias OBs disputando o mesmo reduzido faziam a linha "Estoque disponível"
    cair a cada bloco (809 → 754 → 699...), como se o mesmo depósito tivesse seis
    saldos diferentes na mesma mensagem. O número é o saldo no momento da
    avaliação daquela OB (ver `alocar_estoque`) — a ressalva torna isso legível.
    """
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    NUMERO_OB=1, CODIGO_REDUZIDO_CRU=26, QTD_PECAS_DISPONIVEIS=809
                ),
                _row_mensagem(
                    NUMERO_OB=2, CODIGO_REDUZIDO_CRU=26, QTD_PECAS_DISPONIVEIS=754
                ),
                _row_mensagem(
                    NUMERO_OB=3, CODIGO_REDUZIDO_CRU=99, QTD_PECAS_DISPONIVEIS=40
                ),
            ]
        }
    )
    # Primeira OB do reduzido: saldo cheio, sem ressalva.
    assert "Estoque disponível: 809 peças\n" in msg
    assert "Estoque disponível: 754 peças (após as OBs acima)" in msg
    # Reduzido diferente: saldo próprio, também sem ressalva.
    assert "Estoque disponível: 40 peças\n" in msg


def test_build_message_aceita_artigo_alfanumerico_sem_truncar() -> None:
    """`0A231` é o valor real que fazia a OB ser descartada na coerção."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message({"rows": [_row_mensagem(CODIGO_ARTIGO_CRU="0A231")]})
    assert "Artigo: 0A231" in msg


def test_build_message_normaliza_artigo_e_cor_para_o_padrao_interno() -> None:
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    CODIGO_ARTIGO_CRU=32,
                    CODIGO_COR_TINGIMENTO="00001",
                )
            ]
        }
    )
    assert "Artigo: 032" in msg
    assert "Cor programada: 01" in msg


def test_build_message_mostra_as_duas_finalidades_do_estoque() -> None:
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    RESTRICOES_DISPONIVEIS=[
                        {"codigo": 3, "descricao": "CORES CLARAS"},
                        {"codigo": 4, "descricao": "BRANCO"},
                    ]
                )
            ]
        }
    )
    assert "Restrições da peça: 3 — CORES CLARAS; 4 — BRANCO" in msg


def test_build_message_nao_expoe_tempo_de_consulta_nem_grupo() -> None:
    """Tempo de consulta e grupo destino sao observabilidade interna
    (orb_result.json/logs) — irrelevantes para os integrantes do grupo."""
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


# --------------------------------------------------------------------------
# Cobertura parcial (01/09/2026) — notificar mesmo sem estoque para a OB inteira
# --------------------------------------------------------------------------


def test_alocar_estoque_notifica_ob_com_estoque_parcial() -> None:
    """Caso que motivou a mudança: 5 peças restritas do reduzido 26 e uma OB de
    55. Antes a OB não era anunciada e a Montagem montava as 55 com peça sem
    restrição, deixando as 5 restritas paradas no depósito."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(NUMERO_OB=1, CODIGO_REDUZIDO_CRU=26, TOTAL_PECAS=55))
    avaliacao = v.alocar_estoque([ob], _estoques(r26=5))[0]
    assert avaliacao.notificar is True
    assert avaliacao.alocado == 5
    assert avaliacao.faltante == 50
    assert avaliacao.cobertura_total is False


def test_alocar_estoque_uma_peca_ja_basta_para_notificar() -> None:
    """MINIMO_PECAS_NOTIFICAVEL = 1: qualquer saldo aproveitável justifica o
    aviso; zero não gera nada."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(CODIGO_REDUZIDO_CRU=100, TOTAL_PECAS=500))
    assert v.alocar_estoque([ob], _estoques(r100=1))[0].notificar is True
    assert v.alocar_estoque([ob], _estoques(r100=0))[0].notificar is False


def test_alocar_estoque_prioriza_quem_fecha_cem_por_cento() -> None:
    """Duas lojas disputando 50 peças: a de entrega mais próxima precisa de 80
    (não fecha) e a seguinte precisa de exatamente 50. Quem fecha 100% aloca na
    primeira passada; a outra fica com o que sobrar — aqui, nada.

    A prioridade de negócio (loja → entrega) segue valendo dentro de cada
    passada: é o desempate entre parciais e entre integrais."""
    v = _validators()
    obs = v.priorizar_obs(
        [
            v.coerce_ob_row(
                _ob_row(
                    NUMERO_OB=1,
                    CODIGO_REDUZIDO_CRU=100,
                    TOTAL_PECAS=80,
                    DT_ENTREGA="2026-07-10T00:00:00",
                )
            ),
            v.coerce_ob_row(
                _ob_row(
                    NUMERO_OB=2,
                    CODIGO_REDUZIDO_CRU=100,
                    TOTAL_PECAS=50,
                    DT_ENTREGA="2026-07-20T00:00:00",
                )
            ),
        ]
    )
    avaliacoes = v.alocar_estoque(obs, _estoques(r100=50))
    por_id = {a.ob.id_ob: a for a in avaliacoes}
    assert por_id[2].alocado == 50, "fecha 100% e aloca antes"
    assert por_id[1].notificar is False, "não sobrou peça restrita para a parcial"
    # A ordem de retorno continua sendo a de prioridade, não a de alocação.
    assert [a.ob.id_ob for a in avaliacoes] == [1, 2]


def test_alocar_estoque_parciais_seguem_a_ordem_de_prioridade() -> None:
    """Nenhuma das duas fecha 100%: a primeira da fila de prioridade leva todo o
    saldo, a segunda fica sem — o saldo escoa inteiro, sem sobra guardada."""
    v = _validators()
    obs = v.priorizar_obs(
        [
            v.coerce_ob_row(
                _ob_row(
                    NUMERO_OB=1,
                    CODIGO_REDUZIDO_CRU=100,
                    TOTAL_PECAS=90,
                    DT_ENTREGA="2026-07-10T00:00:00",
                )
            ),
            v.coerce_ob_row(
                _ob_row(
                    NUMERO_OB=2,
                    CODIGO_REDUZIDO_CRU=100,
                    TOTAL_PECAS=80,
                    DT_ENTREGA="2026-07-20T00:00:00",
                )
            ),
        ]
    )
    avaliacoes = v.alocar_estoque(obs, _estoques(r100=20))
    assert [(a.ob.id_ob, a.alocado) for a in avaliacoes] == [(1, 20), (2, 0)]
    assert [a.notificar for a in avaliacoes] == [True, False]


def test_merge_notified_state_reserva_o_alocado_e_nao_o_necessario() -> None:
    """Numa cobertura parcial a reserva é do que a OB de fato segura (5), não do
    que ela precisa (55) — reservar 55 tiraria do pote peças que o depósito
    nunca teve e travaria as próximas OBs do mesmo reduzido."""
    v = _validators()
    ob = v.coerce_ob_row(_ob_row(NUMERO_OB=1, CODIGO_REDUZIDO_CRU=26, TOTAL_PECAS=55))
    avaliacoes = v.alocar_estoque([ob], _estoques(r26=5))
    estado = v.merge_notified_state({}, avaliacoes, avaliacoes, "2026-09-01T08:00:00")
    assert estado["1"].quantidade == 5
    assert estado["1"].codigo_reduzido == 26


def test_ob_parcial_ja_avisada_nao_e_reanunciada_no_ciclo_seguinte() -> None:
    """Idempotência por OB continua valendo para a parcial: mesmo que o estoque
    suba de 5 para 30 no ciclo seguinte, a OB já anunciada não volta ao grupo."""
    v = _validators()
    reduzido = 26
    ob = v.coerce_ob_row(
        _ob_row(NUMERO_OB=1, CODIGO_REDUZIDO_CRU=reduzido, TOTAL_PECAS=55)
    )

    avaliacoes1 = v.alocar_estoque([ob], _estoques(r26=5))
    novas1 = [a for a in avaliacoes1 if a.notificar]
    estado = v.merge_notified_state({}, avaliacoes1, novas1, "2026-09-01T08:00:00")

    agora = "2026-09-01T10:00:00"
    vivas = v.reservas_vivas(estado, agora)
    reservado = v.reservas_por_reduzido(vivas)
    assert reservado == {reduzido: 5}

    avaliacoes2 = v.alocar_estoque([ob], _estoques(r26=30), reservado, vivas)
    novas2 = [a for a in avaliacoes2 if a.notificar and str(a.ob.id_ob) not in vivas]
    assert novas2 == []
    assert avaliacoes2[0].alocado == 5, "mantém a reserva original, não a re-dimensiona"


def test_build_message_status_parcial_explica_o_complemento() -> None:
    """A Montagem precisa ler, no bloco, que aquela OB não fecha só com peça
    restrita — senão o '✅ Pronta para montagem' seria falso."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    NUMERO_OB=185719,
                    CODIGO_REDUZIDO_CRU=26,
                    TOTAL_PECAS=55,
                    QTD_PECAS_DISPONIVEIS=5,
                    QTD_PECAS_ALOCADAS=5,
                    QTD_PECAS_FALTANTES=50,
                )
            ]
        }
    )
    assert (
        "Status: ⚠️ Montagem parcial — usar as 5 peças com restrição e "
        "completar as 50 restantes com peças sem restrição" in msg
    )
    assert "✅" not in msg


def test_build_message_status_parcial_concorda_no_singular() -> None:
    """Saldo de uma peça só é o caso comum (o piso para notificar é 1): a
    primeira mensagem em produção com a regra nova saiu com "usar as 1 peças"."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    TOTAL_PECAS=50,
                    QTD_PECAS_DISPONIVEIS=1,
                    QTD_PECAS_ALOCADAS=1,
                    QTD_PECAS_FALTANTES=49,
                )
            ]
        }
    )
    assert (
        "usar a 1 peça com restrição e completar as 49 restantes "
        "com peças sem restrição" in msg
    )

    unica_faltante = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    TOTAL_PECAS=50,
                    QTD_PECAS_DISPONIVEIS=49,
                    QTD_PECAS_ALOCADAS=49,
                    QTD_PECAS_FALTANTES=1,
                )
            ]
        }
    )
    assert (
        "usar as 49 peças com restrição e completar a 1 restante "
        "com peças sem restrição" in unica_faltante
    )


def test_build_message_status_integral_quando_nada_falta() -> None:
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    TOTAL_PECAS=50, QTD_PECAS_ALOCADAS=50, QTD_PECAS_FALTANTES=0
                )
            ]
        }
    )
    assert "Status: ✅ Pronta para montagem" in msg
    assert "Montagem parcial" not in msg


def test_build_message_subtitulo_conta_completas_e_parciais() -> None:
    """Com parcial na lista, '2 OBs prontas para montagem' seria falso."""
    module = _load_module("format_message", AUTOMATION_DIR / "format_message.py")
    msg = module.build_message(
        {
            "rows": [
                _row_mensagem(
                    NUMERO_OB=1, QTD_PECAS_ALOCADAS=50, QTD_PECAS_FALTANTES=0
                ),
                _row_mensagem(
                    NUMERO_OB=2, QTD_PECAS_ALOCADAS=5, QTD_PECAS_FALTANTES=45
                ),
            ]
        }
    )
    assert "2 OBs com peças restritas disponíveis (1 completa, 1 parcial)" in msg

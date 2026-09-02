# pylint: disable=broad-exception-caught, duplicate-code, import-error, wrong-import-position
# pylint: disable=too-many-locals
# {
#   "version": "1.0.0",
#   "skill": "protocolo-valeg",
#   "contract": "exit-0=todas-validacoes-ok, exit-1=alguma-validacao-falhou",
#   "description": "Simulacao somente leitura do ORB-07 contra Oracle real"
# }
"""Simulação somente leitura de dados do ORB-07 em produção.

Executa as queries reais contra o Oracle, passa os retornos pelas MESMAS
funcoes de validators.py que a producao usa, e imprime o relatorio para
conferencia humana.

SOMENTE LEITURA: nao escreve state, nao gera message.txt e nao envia WhatsApp.
Rodar quantas vezes for preciso, sem efeito colateral.

    .venv\\Scripts\\python.exe "OBs Restricao Branco\\test_orb_simulation.py"
    .venv\\Scripts\\python.exe "OBs Restricao Branco\\test_orb_simulation.py" --codigo 12345

Nao contem funcoes `test_*`: e um runner de linha de comando, nao uma suite
pytest (os testes automatizados vivem em Orchestrator/tests/test_orb.py).
"""

import argparse
import os
import sys
import time
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from automation_log import ensure_utf8_streams, make_logger
from dotenv import load_dotenv
from errors import DadoIncompletoError
from models import (
    CLASSIFICACOES_BRANCO_ALVO,
    FINALIDADES_COMPLEMENTO,
    FINALIDADES_PECA_ALVO,
    ObRestricaoBranco,
)
from oracle_extract import (
    OracleCredentials,
    fetch_all,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from queries import (
    SQL_DIAGNOSTICO_CLASSIFICACOES_PATH,
    SQL_OBS_PATH,
    build_estoque_sql,
    build_finalidades_sql,
    chunk_codigos,
    load_sql,
)
from validators import (
    alocar_estoque,
    priorizar_obs,
    validate_estoque_query,
    validate_estoque_rows,
    validate_finalidades_query,
    validate_ob_query,
)

ensure_utf8_streams()

# Script pensado para execucao standalone (fora do run.ps1/Import-HubEnv), entao
# carrega o .env diretamente — mesmo padrao de Montagem de Terceirizados/extract_oracle.py.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

log = make_logger("ORB-SIM")
EXEC_ID = "simulacao"

OK = "✓"
FALHA = "✗"
AVISO = "!"


def _linha(marcador: str, texto: str) -> None:
    print(f"{marcador} {texto}")


def _fetch_obs(creds: OracleCredentials) -> tuple[list[str], list[dict[str, Any]]]:
    columns, rows = fetch_all(
        creds, load_sql(SQL_OBS_PATH), EXEC_ID, log, batch_size=1000
    )
    return columns, serialize_rows(
        columns, rows, sort_key=lambda r: r.get("NUMERO_OB") or 0
    )


def simular_classificacoes(creds: OracleCredentials) -> None:
    """Mostra aceites e rejeições do mesmo universo, agrupados por classe."""
    print("\n=== Diagnóstico: aceites e rejeições por classificação ===")
    columns, rows = fetch_all(
        creds,
        load_sql(SQL_DIAGNOSTICO_CLASSIFICACOES_PATH),
        EXEC_ID,
        log,
        batch_size=1000,
    )
    data = serialize_rows(columns, rows)
    if not data:
        print("    nenhuma OB no universo STATUS=1 e não montada")
        return
    for row in data:
        codigo = row.get("CD_CLASSIFICACAO_COR")
        descricao = row.get("DS_CLASSIFICACAO_COR") or "SEM CLASSIFICAÇÃO"
        qtd_classes = row.get("QTD_CLASSIFICACOES_COR")
        print(
            f"    {row.get('DECISAO')}: classe {codigo if codigo is not None else '—'} "
            f"{descricao} | resoluções={qtd_classes} | OBs={row.get('TOTAL_OBS')}"
        )


def _fetch_finalidades(creds: OracleCredentials) -> dict[int, str]:
    """Finalidades que a ORB-07 contabiliza — as MESMAS da producao.

    `COR_FINALIDADE` e lido so' para resolver as descricoes oficiais e falhar de
    forma observavel se 3 ou 4 sumirem do cadastro; o conjunto contabilizado e
    fixo em `FINALIDADES_PECA_ALVO` (CONTEXT.md, item 1). Ate 01/09/2026 esta
    simulacao usava o cadastro INTEIRO ({1, 3, 4, 6, 8, 12, 13}) e somava a
    finalidade 1 (SEM RESTRICAO) ao saldo — exatamente o que a regra de negocio
    proibe. O simulador entao aprovava OB que a producao reprovava, com um saldo
    que nao existia para esta automacao.
    """
    sql, params = build_finalidades_sql(CLASSIFICACOES_BRANCO_ALVO)
    columns, rows = fetch_all(creds, sql, EXEC_ID, log, batch_size=1000, params=params)
    cadastro = validate_finalidades_query(
        CLASSIFICACOES_BRANCO_ALVO, serialize_rows(columns, rows)
    )
    return {f: cadastro[f] for f in FINALIDADES_PECA_ALVO if f in cadastro}


def _finalidades_complemento(cadastro_alvo: dict[int, str]) -> dict[int, str]:
    """Finalidades tratadas como SEM RESTRICAO (1 e 8), usadas so' para saber se
    a OB parcial e montavel. Nao dependem de COR_FINALIDADE — descricao com
    fallback, mesma regra da producao (extract_orb._fetch_finalidades)."""
    del cadastro_alvo  # mantido por simetria com a producao
    rotulos = {1: "SEM RESTRICAO", 8: "FIO C/ RESIDUO"}
    return {f: rotulos.get(f, f"FINALIDADE {f}") for f in FINALIDADES_COMPLEMENTO}


def _fetch_estoque_rows(
    creds: OracleCredentials, codigos: list[int], finalidades: dict[int, str]
) -> list[dict[str, Any]]:
    todas: list[dict[str, Any]] = []
    for lote in chunk_codigos(codigos):
        sql, params = build_estoque_sql(lote, sorted(finalidades))
        columns, rows = fetch_all(
            creds, sql, EXEC_ID, log, batch_size=1000, params=params
        )
        todas.extend(serialize_rows(columns, rows))
    return todas


def _agrupar_por_reduzido(
    rows: list[dict[str, Any]],
) -> dict[Any, list[dict[str, Any]]]:
    """O GROUPING SETS devolve linha total + parciais; validar exige as duas juntas."""
    por_codigo: dict[Any, list[dict[str, Any]]] = {}
    for record in rows:
        por_codigo.setdefault(record.get("CODIGO_REDUZIDO_PROD"), []).append(record)
    return por_codigo


def simular_ob_query(
    creds: OracleCredentials,
) -> tuple[list[ObRestricaoBranco], list[str], list[str]]:
    """Validacao 1 — schema e dominio da query de OBs."""
    print(
        "\n=== Validação 1: OBs STATUS=1, não montadas, classes 6/9, sem pedidos R/S ==="
    )
    columns, data = _fetch_obs(creds)
    relatorio = validate_ob_query(columns, data)

    falhas = [] if relatorio.schema_ok else list(relatorio.problemas)
    rejeicoes = list(relatorio.problemas) if relatorio.schema_ok else []
    if falhas:
        for problema in falhas:
            _linha(FALHA, f"Validação OB Query: {problema}")
    else:
        _linha(
            OK,
            f"Validação OB Query: {relatorio.total} linha(s) retornada(s)",
        )
    for problema in rejeicoes:
        _linha(AVISO, f"OB rejeitada sem notificação: {problema}")

    classe_6 = sum(ob.codigo_classificacao_cor == 6 for ob in relatorio.obs)
    classe_9 = sum(ob.codigo_classificacao_cor == 9 for ob in relatorio.obs)
    print(
        f"    classificações válidas -> 6=BRANCO: {classe_6} | 9=BRANCO 2 FIBRAS: {classe_9}"
    )

    for amostra in relatorio.amostra:
        identificacao = (
            f"OB #{amostra.get('NUMERO_OB')} | "
            f"peça {amostra.get('CODIGO_REDUZIDO_CRU')}"
        )
        print(
            f"    amostra -> {identificacao} "
            f"| classe {amostra.get('CD_CLASSIFICACAO_COR')} {amostra.get('DS_CLASSIFICACAO_COR')} "
            f"| cor {amostra.get('CODIGO_COR_TINGIMENTO') or '—'} "
            f"| {amostra.get('TOTAL_PECAS')} un | {amostra.get('KILOS_PROGRAMADOS')} kg"
        )

    # relatorio.obs ja vem coagido por validate_ob_query — nao ha necessidade
    # de rodar coerce_ob_row de novo sobre o retorno cru.
    return relatorio.obs, rejeicoes, falhas


def simular_estoque_query(
    creds: OracleCredentials, codigo: int, finalidades: dict[int, str]
) -> bool:
    """Validacao 2 — query de estoque parametrizada por UM codigo conhecido."""
    rotulo = ", ".join(f"{c}={d}" for c, d in finalidades.items())
    print(f"\n=== Validação 2: Estoque das finalidades {rotulo} (Peça {codigo}) ===")
    resultado = validate_estoque_query(
        codigo, _fetch_estoque_rows(creds, [codigo], finalidades), finalidades
    )
    marcador = OK if resultado["validado"] else FALHA
    _linha(
        marcador,
        f"Validação Estoque Query (Peça {codigo}): {resultado['quantidade']} unidades disponíveis",
    )
    restricoes = resultado.get("restricoes", [])
    if restricoes:
        descricao_restricoes = "; ".join(
            f"{item['codigo']}={item['descricao']}" for item in restricoes
        )
        print(f"    finalidades com saldo: {descricao_restricoes}")
    if resultado["motivo"] != "ok":
        print(f"    obs: {resultado['motivo']}")
    if resultado["fan_out"]:
        _linha(
            FALHA,
            "ATENÇÃO: joins duplicam linhas — COUNT simples superestimaria o estoque.",
        )
    return bool(resultado["validado"])


def simular_comparacoes(
    creds: OracleCredentials,
    obs: list[ObRestricaoBranco],
    finalidades: dict[int, str],
) -> tuple[int, int]:
    """Validacao 3 — priorizacao (lojas antes da matriz) + alocacao sequencial
    de estoque, a MESMA cadeia que a producao roda em extract_orb.py."""
    print(
        "\n=== Validação 3: Priorização + Alocação de Estoque "
        "(integral primeiro, depois parcial) ==="
    )
    reduzidos = sorted({ob.codigo_reduzido_cru for ob in obs})

    def _saldos(finalidades_alvo: dict[int, str]) -> dict[int, Any]:
        rows = _fetch_estoque_rows(creds, reduzidos, finalidades_alvo)
        saldos: dict[int, Any] = {}
        for registros in _agrupar_por_reduzido(rows).values():
            try:
                estoque = validate_estoque_rows(registros, finalidades_alvo)
                saldos[estoque.codigo_reduzido] = estoque
            except DadoIncompletoError as exc:
                _linha(FALHA, f"Estoque inválido: {exc}")
        return saldos

    estoques = _saldos(finalidades)
    complementos = _saldos(_finalidades_complemento(finalidades))
    print(
        "    complemento sem restrição por reduzido: "
        + (
            "; ".join(f"{c}={e.quantidade} un" for c, e in sorted(complementos.items()))
            or "nenhum"
        )
    )

    notificar = 0
    for avaliacao in alocar_estoque(
        priorizar_obs(obs), estoques, complementos=complementos
    ):
        ob = avaliacao.ob
        destino = f" | {ob.nome_cliente or '—'} entrega {ob.dt_entrega or '—'}"
        cabecalho = f"OB #{ob.id_ob} precisa {ob.total_pecas} un, saldo {avaliacao.disponivel} un"
        if avaliacao.notificar and avaliacao.cobertura_total:
            notificar += 1
            _linha(OK, f"{cabecalho}{destino} → Notificar ✅ (integral)")
        elif avaliacao.notificar:
            notificar += 1
            _linha(
                AVISO,
                f"{cabecalho}{destino} → Notificar ⚠️ (parcial: "
                f"{avaliacao.alocado} un restritas + {avaliacao.faltante} un sem restrição)",
            )
        else:
            _linha(
                FALHA,
                f"{cabecalho}{destino} → Sem peça restrita ❌",
            )
    return notificar, len(obs) - notificar


def main() -> None:
    """Executa as validações somente leitura contra o Oracle."""
    parser = argparse.ArgumentParser(
        description="Simulação de dados OBs Restrição Branco (somente leitura — não envia WhatsApp)"
    )
    parser.add_argument(
        "--codigo",
        type=int,
        default=None,
        help="CODIGO_REDUZIDO_CRU conhecido para a Validação 2. Default: a 1a OB retornada.",
    )
    args = parser.parse_args()

    creds = resolve_oracle_credentials(log, EXEC_ID)
    if creds is None:
        print(f"{FALHA} Credenciais Oracle ausentes/inválidas. Confira o .env.")
        sys.exit(1)
    init_thick_mode(creds, log, EXEC_ID)

    inicio = time.perf_counter()
    print("=" * 70)
    print("SIMULAÇÃO OBs RESTRIÇÃO BRANCO (ORB-07) — somente leitura")
    print("=" * 70)

    try:
        simular_classificacoes(creds)
        obs, rejeicoes, falhas = simular_ob_query(creds)
        if not obs:
            print(f"\n{FALHA} Nenhuma OB válida retornada — nada a simular adiante.")
            sys.exit(1 if falhas else 0)

        finalidades = _fetch_finalidades(creds)
        codigo = args.codigo if args.codigo is not None else obs[0].codigo_reduzido_cru
        estoque_ok = simular_estoque_query(creds, codigo, finalidades)
        notificar, sem_estoque = simular_comparacoes(creds, obs, finalidades)
        decorrido = time.perf_counter() - inicio

        print("\n" + "-" * 70)
        print(
            f"Relatório Final: {OK} {len(obs)} OBs válidas, "
            f"{AVISO} {len(rejeicoes)} OBs rejeitadas, {FALHA} {len(falhas)} falhas | "
            f"{notificar} a notificar, {sem_estoque} sem estoque | tempo total: {decorrido:.1f}s"
        )
        for rejeicao in rejeicoes:
            print(f"    {AVISO} {rejeicao}")
        for falha in falhas:
            print(f"    {FALHA} {falha}")
        print("-" * 70)
        print("\nNenhum WhatsApp foi enviado — esta é uma simulação de leitura.")

        sys.exit(0 if estoque_ok and not falhas else 1)

    except Exception as e:
        print(f"\n{FALHA} Falha na simulação: {e}")
        log(f"Erro fatal na simulacao: {e}", "ERROR", EXEC_ID)
        sys.exit(1)


if __name__ == "__main__":
    main()

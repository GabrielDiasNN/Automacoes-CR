# pylint: disable=broad-exception-caught, import-error, wrong-import-position
# {
#   "version": "1.0.0",
#   "skill": "protocolo-valeg",
#   "contract": "exit-0=todas-validacoes-ok, exit-1=alguma-validacao-falhou",
#   "description": "Simulacao FASE 1 do OFST-06 contra Oracle real — somente leitura, nunca envia WhatsApp"
# }
"""Simulacao de dados do OFST-06 (FASE 1 — antes de ativar o job).

Executa as queries reais contra o Oracle, passa os retornos pelas MESMAS
funcoes de validators.py que a producao usa, e imprime o relatorio para
conferencia humana.

SOMENTE LEITURA: nao escreve state, nao gera message.txt e nao envia WhatsApp.
Rodar quantas vezes for preciso, sem efeito colateral.

    .venv\\Scripts\\python.exe "OBs Fluxo Sem Tingimento\\test_ofst_simulation.py"
    .venv\\Scripts\\python.exe "OBs Fluxo Sem Tingimento\\test_ofst_simulation.py" --codigo 12345

Nao contem funcoes `test_*`: e um runner de linha de comando, nao uma suite
pytest (os testes automatizados vivem em Orchestrator/tests/test_ofst.py).
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
from models import ObSemTingimento
from oracle_extract import (
    OracleCredentials,
    fetch_all,
    init_thick_mode,
    resolve_oracle_credentials,
    serialize_rows,
)
from queries import SQL_OBS_PATH, build_estoque_sql, chunk_codigos, load_sql
from validators import (
    alocar_estoque,
    priorizar_obs,
    validate_estoque_query,
    validate_estoque_row,
    validate_ob_query,
)

ensure_utf8_streams()

# Script pensado para execucao standalone (fora do run.ps1/Import-HubEnv), entao
# carrega o .env diretamente — mesmo padrao de Montagem de Terceirizados/extract_oracle.py.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

log = make_logger("OFST-SIM")
EXEC_ID = "simulacao"

OK = "✓"
FALHA = "✗"


def _linha(marcador: str, texto: str) -> None:
    print(f"{marcador} {texto}")


def _fetch_obs(creds: OracleCredentials) -> tuple[list[str], list[dict[str, Any]]]:
    columns, rows = fetch_all(
        creds, load_sql(SQL_OBS_PATH), EXEC_ID, log, batch_size=1000
    )
    return columns, serialize_rows(
        columns, rows, sort_key=lambda r: r.get("NUMERO_OB") or 0
    )


def _fetch_estoque_rows(
    creds: OracleCredentials, codigos: list[int]
) -> list[dict[str, Any]]:
    todas: list[dict[str, Any]] = []
    for lote in chunk_codigos(codigos):
        sql, params = build_estoque_sql(lote)
        columns, rows = fetch_all(
            creds, sql, EXEC_ID, log, batch_size=1000, params=params
        )
        todas.extend(serialize_rows(columns, rows))
    return todas


def simular_ob_query(
    creds: OracleCredentials,
) -> tuple[list[ObSemTingimento], list[str]]:
    """Validacao 1 — schema e dominio da query de OBs."""
    print("\n=== Validação 1: Query de OBs (FLUXO=204, STATUS=1, OBMONTADA='0') ===")
    columns, data = _fetch_obs(creds)
    relatorio = validate_ob_query(columns, data)

    if relatorio.problemas:
        for problema in relatorio.problemas:
            _linha(FALHA, f"Validação OB Query: {problema}")
    else:
        _linha(
            OK,
            f"Validação OB Query: {relatorio.total} OBs encontradas (STATUS=1, FLUXO=204)",
        )

    for amostra in relatorio.amostra:
        print(
            f"    amostra -> OB #{amostra.get('NUMERO_OB')} | peça {amostra.get('CODIGO_REDUZIDO_CRU')} "
            f"| {amostra.get('TOTAL_PECAS')} un | {amostra.get('KILOS_PROGRAMADOS')} kg"
        )

    # relatorio.obs ja vem coagido por validate_ob_query — nao ha necessidade
    # de rodar coerce_ob_row de novo sobre o retorno cru.
    return relatorio.obs, relatorio.problemas


def simular_estoque_query(creds: OracleCredentials, codigo: int) -> bool:
    """Validacao 2 — query de estoque parametrizada por UM codigo conhecido."""
    print(f"\n=== Validação 2: Query de Estoque (Peça {codigo}) ===")
    resultado = validate_estoque_query(codigo, _fetch_estoque_rows(creds, [codigo]))
    marcador = OK if resultado["validado"] else FALHA
    _linha(
        marcador,
        f"Validação Estoque Query (Peça {codigo}): {resultado['quantidade']} unidades disponíveis",
    )
    if resultado["motivo"] != "ok":
        print(f"    obs: {resultado['motivo']}")
    if resultado["fan_out"]:
        _linha(
            FALHA,
            "ATENÇÃO: joins duplicam linhas — COUNT simples superestimaria o estoque.",
        )
    return bool(resultado["validado"])


def simular_comparacoes(
    creds: OracleCredentials, obs: list[ObSemTingimento]
) -> tuple[int, int]:
    """Validacao 3 — priorizacao (lojas antes da matriz) + alocacao sequencial
    de estoque, a MESMA cadeia que a producao roda em extract_ofst.py."""
    print(
        "\n=== Validação 3: Priorização + Alocação de Estoque (saldo >= necessidade) ==="
    )
    estoque_rows = _fetch_estoque_rows(
        creds, sorted({ob.codigo_reduzido_cru for ob in obs})
    )
    estoques = {}
    for record in estoque_rows:
        try:
            estoque = validate_estoque_row(record)
            estoques[estoque.codigo_reduzido] = estoque
        except DadoIncompletoError as exc:
            _linha(FALHA, f"Estoque inválido: {exc}")

    notificar = 0
    for avaliacao in alocar_estoque(priorizar_obs(obs), estoques):
        ob = avaliacao.ob
        destino = f" | {ob.nome_cliente or '—'} entrega {ob.dt_entrega or '—'}"
        if avaliacao.notificar:
            notificar += 1
            _linha(
                OK,
                f"OB #{ob.id_ob} precisa {ob.total_pecas} un, saldo {avaliacao.disponivel} un"
                f"{destino} → Notificar ✅",
            )
        else:
            _linha(
                FALHA,
                f"OB #{ob.id_ob} precisa {ob.total_pecas} un, saldo {avaliacao.disponivel} un"
                f"{destino} → Sem estoque ❌",
            )
    return notificar, len(obs) - notificar


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulação de dados OBs Fluxo Sem Tingimento (somente leitura — não envia WhatsApp)"
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
    print("SIMULAÇÃO OBs FLUXO SEM TINGIMENTO (OFST-06) — somente leitura")
    print("=" * 70)

    try:
        obs, erros = simular_ob_query(creds)
        if not obs:
            print(f"\n{FALHA} Nenhuma OB válida retornada — nada a simular adiante.")
            sys.exit(1 if erros else 0)

        codigo = args.codigo if args.codigo is not None else obs[0].codigo_reduzido_cru
        estoque_ok = simular_estoque_query(creds, codigo)
        notificar, sem_estoque = simular_comparacoes(creds, obs)
        decorrido = time.perf_counter() - inicio

        print("\n" + "-" * 70)
        print(
            f"Relatório Final: {OK} {len(obs)} OBs válidas, {FALHA} {len(erros)} OBs com erro | "
            f"{notificar} a notificar, {sem_estoque} sem estoque | tempo total: {decorrido:.1f}s"
        )
        for erro in erros:
            print(f"    {FALHA} {erro}")
        print("-" * 70)
        print("\nNenhum WhatsApp foi enviado — esta é uma simulação de leitura.")

        sys.exit(0 if estoque_ok and not erros else 1)

    except Exception as e:
        print(f"\n{FALHA} Falha na simulação: {e}")
        log(f"Erro fatal na simulacao: {e}", "ERROR", EXEC_ID)
        sys.exit(1)


if __name__ == "__main__":
    main()

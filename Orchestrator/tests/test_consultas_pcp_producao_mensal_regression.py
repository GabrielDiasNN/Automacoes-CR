#!/usr/bin/env python3
"""Suíte de Testes de Regressão e Proteção de Invariantes para:
pcp_producao_mensal_por_fase_comparativo.sql

Arquitetura de Testes:
1. Testes de Invariantes Permanentes (Executáveis em qualquer competência):
   - Integridade de cardinalidade (OB_FASES, BD_PRD_MOVPROD).
   - Unicidade estrita dos JOINs dimensionais de receita (LCR, CR, CL).
   - Ausência de itens de fluxo não classificado (ou linha 94 condicional e alerta de qualidade).
   - Cobertura de 100% dos 4 grupos de mix de cores na Tinturaria normal.
   - Detecção de anomalias de tempos (previsto <= 0 ou real <= 0).
   - Unicidade da coluna ORDEM e presença de linhas obrigatórias.
   - Reconciliação aditiva dos totais (Tinturaria, Partidas, Turnos, Mix, Fluxo).
   - Validação matemática dos KPIs de gestão (00A a 00F, 12C, 93).
   - Consistência de tempos derivados (DESVIO_TEMPO_MIN, EFIC_TEMPO_PCT).

2. Testes de Snapshot / Regressão Histórica:
   - Comparação contra baseline congelada e versionada em fixtures:
     `Orchestrator/tests/fixtures/pcp_producao_mensal/baseline_pcp_producao_mensal_YYYY_MM_vs_YYYY_MM.json`
   - O snapshot numérico SÓ é confrontado se a COMPETENCIA do SQL for idêntica à da baseline.
   - Suporte a teste de janela fixa reproduzível (substituição transparente da CTE JANELA),
     permitindo validar o SQL operacional contra dados históricos imutáveis sem modificar o arquivo de produção.

3. Classificação de Severidade:
   - PASS: Teste executado com sucesso e integridade plena.
   - WARN: Alertas operacionais/cadastrais (ex: 3 UPs com início=fim no tempo real, competência divergente).
   - FAIL: Quebra de cardinalidade, integridade de joins, erro de fórmula ou divergência de snapshot.

Uso:
    python Orchestrator/tests/test_consultas_pcp_producao_mensal_regression.py [--live-oracle] [--fixed-window] [--benchmark]
    pytest Orchestrator/tests/test_consultas_pcp_producao_mensal_regression.py -s
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "Produção Beneficimento" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from beneficiamento.oracle import execute_query  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("regression_test")

SQL_FILE = (
    REPO_ROOT
    / "docs"
    / "oracle-schema"
    / "consultas"
    / "09_pcp_kpis_gestao"
    / "pcp_producao_mensal_por_fase_comparativo.sql"
)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "pcp_producao_mensal"
DEFAULT_BASELINE_FILE = (
    FIXTURES_DIR / "baseline_pcp_producao_mensal_2026_09_vs_2025_09.json"
)


def load_baseline_fixture(path: Path | None = None) -> dict[str, Any]:
    """Carrega o fixture de baseline congelada com metadados."""
    target_path = path or DEFAULT_BASELINE_FILE
    if not target_path.exists():
        raise FileNotFoundError(f"Arquivo de baseline não encontrado: {target_path}")
    data: dict[str, Any] = json.loads(target_path.read_text(encoding="utf-8"))
    return data


@pytest.fixture(name="baseline_fixture", scope="session")
def _baseline_fixture() -> dict[str, Any]:
    return load_baseline_fixture()


# Os testes marcados com `oracle_live` consultam o Oracle de PRODUÇÃO: só rodam
# com a variável abaixo igual a "1" (sem ela, ficam *skipped* e não abrem conexão).
LIVE_ORACLE_ENV = "BENEFICIAMENTO_LIVE_ORACLE"
ORACLE_BUDGET_SECONDS = 120.0
oracle_live = pytest.mark.skipif(
    os.environ.get(LIVE_ORACLE_ENV) != "1",
    reason=f"Consulta o Oracle de produção; exporte {LIVE_ORACLE_ENV}=1 para executar.",
)


def run_oracle_with_retry(
    sql_text: str,
) -> tuple[list[str], list[tuple[Any, ...]], float]:
    """Executa SQL no Oracle via `beneficiamento.oracle.execute_query`.

    Reaproveita conexão com prazo, retry só para queda de sessão, watchdog de
    cancelamento e fechamento garantido; devolve (colunas, linhas, duração em ms).
    """
    clean_sql = sql_text.strip().rstrip(";").strip()
    result = execute_query(
        clean_sql,
        oracle_timeout_ms=int(ORACLE_BUDGET_SECONDS * 1000) - 1000,
        wall_clock_budget_seconds=ORACLE_BUDGET_SECONDS,
    )
    return (
        result.columns,
        result.rows,
        float(result.metadata["elapsed_seconds"]) * 1000.0,
    )


def build_fixed_window_sql(
    raw_sql: str,
    dt_inicio: str = "01-09-2026",
    dt_fim: str = "01-10-2026",
    dt_inicio_ant: str = "01-09-2025",
    dt_fim_ant: str = "01-10-2025",
) -> str:
    """Substitui transparentemente a CTE JANELA por datas fixas para teste histórico reproduzível."""
    for data in (dt_inicio, dt_fim, dt_inicio_ant, dt_fim_ant):
        datetime.strptime(data, "%d-%m-%Y")  # só datas DD-MM-AAAA entram no SQL
    nova_janela = f"""WITH JANELA AS (
    SELECT TO_DATE('{dt_inicio}', 'DD-MM-YYYY') AS DT_INICIO,
           TO_DATE('{dt_fim}', 'DD-MM-YYYY') AS DT_FIM,
           TO_DATE('{dt_inicio_ant}', 'DD-MM-YYYY') AS DT_INICIO_ANT,
           TO_DATE('{dt_fim_ant}', 'DD-MM-YYYY') AS DT_FIM_ANT
      FROM DUAL
),
BASE_FASES_AGR"""  # nosec B608 - datas validadas por strptime acima

    def _substituir(match: re.Match[str]) -> str:
        # O `.*?` atravessa CTEs inseridas entre JANELA e BASE_FASES_AGR e as
        # apagaria em silêncio: se o corpo casado contém outra CTE, aborta.
        if re.search(r"\)\s*,\s*\w+\s+AS\s*\(", match.group(1)):
            raise ValueError(
                "Há outra CTE entre JANELA e BASE_FASES_AGR: a substituição a apagaria."
            )
        return nova_janela

    sub_sql, substituicoes = re.subn(
        r"WITH\s+JANELA\s+AS\s*\((.*?)\)\s*,\s*BASE_FASES_AGR",
        _substituir,
        raw_sql,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if substituicoes != 1:
        # Sem substituição o SQL volta com SYSDATE e o teste de janela fixa
        # compararia outra competência: falha fechada em vez de passar vazio.
        raise ValueError(
            "CTE JANELA seguida de BASE_FASES_AGR não encontrada: a janela fixa não foi aplicada."
        )
    return sub_sql


# =============================================================================
# 1. TESTES DE INVARIANTES PERMANENTES (Validação Estrutural e Regras de Negócio)
# =============================================================================


Rows = dict[str, dict[str, Any]]

ORDENS_OBRIGATORIAS = [
    "00A",
    "00B",
    "00C",
    "00D",
    "00E",
    "00F",
    "01",
    "02",
    "03",
    "04A",
    "04B",
    "04C",
    "04D",
    "04E",
    "04F",
    "04G",
    "04H",
    "04I",
    "04J",
    "04K",
    "04L",
    "04M",
    "04N",
    "05A",
    "05B",
    "05C",
    "05D",
    "06A",
    "06B",
    "06C",
    "07",
    "08",
    "09",
    "10",
    "11A",
    "11B",
    "11C",
    "12A",
    "12B",
    "12C",
    "12D",
    "12E",
    "12F",
    "90",
    "91",
    "92",
    "93",
]
LINHAS_TEMPO = [
    "04A",
    "04B",
    "04C",
    "04D",
    "04E",
    "04F",
    "04G",
    "04H",
    "04I",
    "04J",
    "04K",
    "04L",
    "04M",
    "04N",
]
TINTURARIA = ("04D", "04E", "04F")  # normal, reprocesso interno, reprocesso externo
MIX_CORES = ("04H", "04I", "04J", "04K")
MIN_LINHAS = 47  # 47 no padrão, 48 se houver a linha 94


# (ordem do KPI, rótulo, (linha, coluna) do numerador, (linha, coluna) do
# denominador, multiplicador, casas decimais, tolerância, TIPO_VARIACAO_YOY).
class Kpi(NamedTuple):
    ordem: str
    rotulo: str
    numerador: tuple[str, str]  # (linha, coluna)
    denominador: tuple[str, str]  # (linha, coluna)
    multiplicador: int
    casas: int
    tolerancia: float
    tipo_variacao: str | None  # TIPO_VARIACAO_YOY esperado


KPIS = (
    Kpi("00A", "RFT", ("04D", "QT_KG"), ("04G", "QT_KG"), 100, 2, 0.02, "DIF_PP"),
    Kpi(
        "00B",
        "Reprocesso Interno",
        ("04E", "QT_KG"),
        ("04D", "QT_KG"),
        100,
        2,
        0.02,
        None,
    ),
    Kpi(
        "00C",
        "Reprocesso Externo",
        ("04F", "QT_KG"),
        ("04D", "QT_KG"),
        100,
        2,
        0.02,
        None,
    ),
    Kpi("00D", "Escoamento", ("12A", "QT_KG"), ("04G", "QT_KG"), 100, 2, 0.02, None),
    Kpi(
        "00E",
        "Balanço de Fluxo",
        ("12A", "QT_KG"),
        ("01", "QT_KG"),
        100,
        2,
        0.02,
        None,
    ),
    Kpi(
        "00F",
        "Peso Médio por Partida",
        ("04G", "QT_KG"),
        ("04G", "QT_PARTIDAS"),
        1,
        0,
        1.0,
        "DIF_ABS",
    ),
    Kpi(
        "12C",
        "Peso Médio por Peça",
        ("12A", "QT_KG"),
        ("12B", "QT_KG"),
        1,
        2,
        0.02,
        "DIF_ABS",
    ),
    Kpi(
        "93",
        "Proporção Tubular/Ramado",
        ("90", "QT_KG"),
        ("91", "QT_KG"),
        100,
        2,
        0.02,
        None,
    ),
)


def _soma(rows: Rows, ordens: tuple[str, ...], coluna: str) -> float:
    return sum((rows[o][coluna] or 0) for o in ordens)


def _checar_estrutura(
    rows: list[dict[str, Any]], rows_by_ordem: Rows, report: dict[str, Any]
) -> None:
    """Unicidade de ORDEM, linhas obrigatórias, linha 94 e quantidade mínima."""
    ordens = [r["ORDEM"] for r in rows]
    if len(ordens) != len(set(ordens)):
        report["fails"].append("Coluna ORDEM não é estritamente única no relatório.")

    for o in ORDENS_OBRIGATORIAS:
        if o not in rows_by_ordem:
            report["fails"].append(f"Linha obrigatória ausente: {o}")

    if "94" in rows_by_ordem:
        kg_94 = rows_by_ordem["94"].get("QT_KG", 0) or 0
        report["warns"].append(
            f"Linha 94 (FLUXO N/C AUDITORIA) presente com {kg_94} kg. Alerta de qualidade cadastral!"
        )
    else:
        logger.info(
            "  Linha 94 ausente (zero ocorrências de itens sem classificação T/R - cenário saudável)."
        )

    if len(rows) < MIN_LINHAS:
        report["fails"].append(
            f"Quantidade de linhas inferior ao mínimo obrigatório: {len(rows)} < {MIN_LINHAS}"
        )


def _checar_somas(rows: Rows, fails: list[str]) -> None:
    """Reconciliação aditiva: Tinturaria, Mix de Cores e Fluxo de Produto Acabado."""
    if all(rows.get(o) for o in (*TINTURARIA, "04G")):
        total = rows["04G"]
        soma_ting = round(_soma(rows, TINTURARIA, "QT_KG"), 2)
        if not math.isclose(soma_ting, total["QT_KG"] or 0, abs_tol=0.05):
            fails.append(
                f"Soma Tinturaria (Normal + Rep): {soma_ting} != Total {total['QT_KG']}"
            )
        soma_part = _soma(rows, TINTURARIA, "QT_PARTIDAS")
        if soma_part != (total["QT_PARTIDAS"] or 0):
            fails.append(
                f"Soma Partidas Tinturaria: {soma_part} != Total {total['QT_PARTIDAS']}"
            )

    if all(rows.get(o) for o in (*MIX_CORES, "04D")):
        soma_mix = round(_soma(rows, MIX_CORES, "QT_KG"), 2)
        if not math.isclose(soma_mix, rows["04D"]["QT_KG"] or 0, abs_tol=0.05):
            fails.append(
                f"Mix de cores não fecha 100% da produção normal: {soma_mix} != {rows['04D']['QT_KG']}"
            )

    if all(rows.get(o) for o in ("90", "91", "12A")):
        fluxo = ("90", "91", "94") if "94" in rows else ("90", "91")
        soma_fluxo = round(_soma(rows, fluxo, "QT_KG"), 2)
        if not math.isclose(soma_fluxo, rows["12A"]["QT_KG"] or 0, abs_tol=0.05):
            fails.append(
                f"Fluxo Tubular + Ramado (+ NC) não fecha produto acabado total: {soma_fluxo} != {rows['12A']['QT_KG']}"
            )


def _checar_kpi(rows: Rows, fails: list[str], kpi: Kpi) -> None:
    """Recalcula um KPI de gestão a partir das linhas-base e compara com o reportado."""
    (n_linha, n_col), (d_linha, d_col) = kpi.numerador, kpi.denominador
    num, den, alvo = rows.get(n_linha), rows.get(d_linha), rows.get(kpi.ordem)
    if not num or not den or not den.get(d_col) or alvo is None:
        return  # operando ausente/zerado: a ausência já é reprovada em `_checar_estrutura`
    calculado = round((num[n_col] or 0) / den[d_col] * kpi.multiplicador, kpi.casas)
    reportado = alvo.get("QT_KG")
    if reportado is None or not math.isclose(
        calculado, reportado, abs_tol=kpi.tolerancia
    ):
        fails.append(f"Cálculo {kpi.rotulo} divergente: {calculado} vs {reportado}")
    if kpi.tipo_variacao and alvo.get("TIPO_VARIACAO_YOY") != kpi.tipo_variacao:
        fails.append(
            f"{kpi.ordem} deve possuir TIPO_VARIACAO_YOY = '{kpi.tipo_variacao}'"
        )


def _checar_tempo(ordem: str, linha: dict[str, Any], fails: list[str]) -> None:
    """Desvio e eficiência de tempo derivados de previsto x real."""
    t_prev, t_real = linha.get("TEMPO_PREV_HORAS"), linha.get("TEMPO_REAL_HORAS")
    if t_prev is None or t_real is None:
        return
    desvio, efic = linha.get("DESVIO_TEMPO_MIN"), linha.get("EFIC_TEMPO_PCT")

    desvio_calc = round((t_real - t_prev) * 60, 0)
    if desvio is None:
        fails.append(f"DESVIO_TEMPO_MIN ausente em {ordem}")
    elif not math.isclose(desvio, desvio_calc, abs_tol=1.0):
        fails.append(
            f"Desvio de tempo divergente em {ordem}: {desvio} vs {desvio_calc}"
        )

    if t_real > 0 and t_prev > 0:
        efic_calc = round((t_prev / t_real) * 100, 1)
        if efic is None:
            fails.append(f"EFIC_TEMPO_PCT ausente em {ordem}")
        elif not math.isclose(efic, efic_calc, abs_tol=0.2):
            fails.append(
                f"Eficiência de tempo divergente em {ordem}: {efic} vs {efic_calc}"
            )


def validate_dataset_invariants(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Valida as regras lógicas e invariantes sobre qualquer conjunto de resultados retornado."""
    logger.info("Auditando invariantes do conjunto de dados (%d linhas)...", len(rows))
    report: dict[str, Any] = {"status": "PASS", "fails": [], "warns": []}
    rows_by_ordem: Rows = {r["ORDEM"]: r for r in rows}
    fails: list[str] = report["fails"]

    _checar_estrutura(rows, rows_by_ordem, report)
    _checar_somas(rows_by_ordem, fails)
    for spec in KPIS:
        _checar_kpi(rows_by_ordem, fails, spec)
    for ordem in LINHAS_TEMPO:
        if rows_by_ordem.get(ordem):
            _checar_tempo(ordem, rows_by_ordem[ordem], fails)

    if fails:
        report["status"] = "FAIL"
    elif report["warns"]:
        report["status"] = "WARN"

    return report


def test_invariants_on_baseline(baseline_fixture: dict[str, Any]) -> None:
    """Testa se a baseline estática armazenada é internamente válida e consistente."""
    report = validate_dataset_invariants(baseline_fixture["rows"])
    assert (
        report["status"] != "FAIL"
    ), f"Falha nas invariantes da baseline: {report['fails']}"


@oracle_live
def test_oracle_database_invariants() -> None:
    """Executa consultas sentinelas diretamente no Oracle e classifica em PASS, WARN ou FAIL."""
    logger.info("Executando verificação de integridade física e cadastral no Oracle...")

    sql_inv = """
    WITH JANELA AS (
        SELECT ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1)  AS DT_INICIO,
               TRUNC(SYSDATE, 'MM')                  AS DT_FIM,
               ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -13) AS DT_INICIO_ANT,
               ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) AS DT_FIM_ANT
          FROM DUAL
    )
    SELECT
        -- 1. Cardinalidade das fases
        (SELECT COUNT(*) - COUNT(DISTINCT OBF.CODIGO_FASE || '-' || OBF.NUMERO_OB || '-' || TO_CHAR(OBF.SEQUENCIA))
           FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
           JOIN SGTPRD.UP_ORDEM_MVTO UOM ON UOM.NUMEROUP = UPR.NUMEROUP
           JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
           CROSS JOIN JANELA JAN
          WHERE UPR.SETOR = 5 AND UPR.EXCLUIDA = 0 AND UPR.TIPOUP = 0 AND UPR.STATUS = 0
            AND ((UPR.DTPRODFIM >= JAN.DT_INICIO AND UPR.DTPRODFIM < JAN.DT_FIM)
              OR (UPR.DTPRODFIM >= JAN.DT_INICIO_ANT AND UPR.DTPRODFIM < JAN.DT_FIM_ANT))
            AND OBF.CODIGO_FASE IN (10, 20, 26, 40, 50, 55, 60, 65, 70, 80, 90, 100, 110)
        ) AS DUP_FASES,
        -- 2. Unicidade de peças no produto acabado
        (SELECT COUNT(MVP.IDPECASPRODUTO) - COUNT(DISTINCT MVP.IDPECASPRODUTO)
           FROM SGTPRD.BD_PRD_MOVPROD MVP
           CROSS JOIN JANELA JAN
          WHERE MVP.NUM_TIPO_MOVIMENTO = 37 AND MVP.CODIGO IN (1, 8)
            AND ((MVP.PRODUCAO_DATA >= JAN.DT_INICIO AND MVP.PRODUCAO_DATA < JAN.DT_FIM)
              OR (MVP.PRODUCAO_DATA >= JAN.DT_INICIO_ANT AND MVP.PRODUCAO_DATA < JAN.DT_FIM_ANT))
        ) AS DUP_PECAS_ACABADO,
        -- 3. Fluxo: contagem de itens não classificados (N/C)
        (SELECT COUNT(*)
           FROM SGTPRD.BD_PRD_MOVPROD MVP
           LEFT JOIN SGTPRD.ENGEITEMESTONIVELGE9 E9 ON E9.CDREDUZIDO = MVP.REDUZIDO_ITEM
           CROSS JOIN JANELA JAN
          WHERE MVP.NUM_TIPO_MOVIMENTO = 37 AND MVP.CODIGO IN (1, 8)
            AND ((MVP.PRODUCAO_DATA >= JAN.DT_INICIO AND MVP.PRODUCAO_DATA < JAN.DT_FIM)
              OR (MVP.PRODUCAO_DATA >= JAN.DT_INICIO_ANT AND MVP.PRODUCAO_DATA < JAN.DT_FIM_ANT))
            AND NVL(TRIM(E9.CDNIVELGENERICO), 'N/C') NOT IN ('T', 'R')
        ) AS FLUXO_NC,
        -- 4. Mix de cores: volume fora dos 4 grupos
        (SELECT NVL(SUM(OBF.KILOS_PRODUZIDOS), 0)
           FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
           JOIN SGTPRD.UP_ORDEM_MVTO UOM ON UOM.NUMEROUP = UPR.NUMEROUP
           JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
           LEFT JOIN SGTPRD.LIGA_CADREC_ITEMREC LCR ON LCR.ID_LIGA_CADREC_ITEMR = OBF.ID_LIGA_CADREC_ITEMR AND OBF.CODIGO_FASE = 40
           LEFT JOIN SGTPRD.CADASTRO_RECEITAS CR ON CR.CODIGO_REDUZIDO_RECE = LCR.CODIGO_REDUZIDO_RECE
           CROSS JOIN JANELA JAN
          WHERE UPR.SETOR = 5 AND UPR.EXCLUIDA = 0 AND UPR.TIPOUP = 0 AND UPR.STATUS = 0
            AND ((UPR.DTPRODFIM >= JAN.DT_INICIO AND UPR.DTPRODFIM < JAN.DT_FIM)
              OR (UPR.DTPRODFIM >= JAN.DT_INICIO_ANT AND UPR.DTPRODFIM < JAN.DT_FIM_ANT))
            AND OBF.CODIGO_FASE = 40 AND NVL(OBF.DESTINO_RECEITA, 1) = 1
            AND NVL(CR.CODIGO_CLASSIFICACAO, -1) NOT IN (1, 6, 7, 10, 18, 2, 5, 14, 3, 8, 9, 11, 12, 15)
        ) AS KG_MIX_NAO_COBERTO,
        -- 5. Tempos previstos inválidos
        (SELECT COUNT(*)
           FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
           JOIN SGTPRD.UP_ORDEM_MVTO UOM ON UOM.NUMEROUP = UPR.NUMEROUP
           JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
           LEFT JOIN SGTPRD.LIGA_CADREC_ITEMREC LCR ON LCR.ID_LIGA_CADREC_ITEMR = OBF.ID_LIGA_CADREC_ITEMR AND OBF.CODIGO_FASE = 40
           LEFT JOIN SGTPRD.CADASTRO_RECEITAS CR ON CR.CODIGO_REDUZIDO_RECE = LCR.CODIGO_REDUZIDO_RECE
           CROSS JOIN JANELA JAN
          WHERE UPR.SETOR = 5 AND UPR.EXCLUIDA = 0 AND UPR.TIPOUP = 0 AND UPR.STATUS = 0
            AND ((UPR.DTPRODFIM >= JAN.DT_INICIO AND UPR.DTPRODFIM < JAN.DT_FIM)
              OR (UPR.DTPRODFIM >= JAN.DT_INICIO_ANT AND UPR.DTPRODFIM < JAN.DT_FIM_ANT))
            AND OBF.CODIGO_FASE = 40
            AND (CR.TEMPO_RECEITA IS NULL OR CR.TEMPO_RECEITA <= 0)
        ) AS QTD_TEMPO_PREV_INVALIDO,
        -- 6. Tempos reais inválidos
        (SELECT COUNT(*)
           FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
           JOIN SGTPRD.UP_ORDEM_MVTO UOM ON UOM.NUMEROUP = UPR.NUMEROUP
           JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
           CROSS JOIN JANELA JAN
          WHERE UPR.SETOR = 5 AND UPR.EXCLUIDA = 0 AND UPR.TIPOUP = 0 AND UPR.STATUS = 0
            AND ((UPR.DTPRODFIM >= JAN.DT_INICIO AND UPR.DTPRODFIM < JAN.DT_FIM)
              OR (UPR.DTPRODFIM >= JAN.DT_INICIO_ANT AND UPR.DTPRODFIM < JAN.DT_FIM_ANT))
            AND OBF.CODIGO_FASE = 40
            AND (UPR.DTTEMPOFINALCONFIRMA IS NULL OR UPR.DTTEMPOINICONFIRMADO IS NULL OR UPR.DTTEMPOFINALCONFIRMA <= UPR.DTTEMPOINICONFIRMADO)
        ) AS QTD_TEMPO_REAL_INVALIDO
    FROM DUAL
    """

    cols, rows, _ = run_oracle_with_retry(sql_inv)
    res = dict(zip(cols, rows[0], strict=True))
    logger.info("  Contadores das invariantes físicas do Oracle: %s", res)

    # 1. Checagens de Integridade Crítica (FAIL se violado)
    assert (
        res["DUP_FASES"] == 0
    ), f"[FAIL] Duplicação física detectada em OB_FASES: {res['DUP_FASES']}"
    assert (
        res["DUP_PECAS_ACABADO"] == 0
    ), f"[FAIL] Duplicação de IDPECASPRODUTO detectada: {res['DUP_PECAS_ACABADO']}"

    # 2. Unicidade das tabelas dimensionais de receitas (FAIL se violado)
    sql_dim = """
    SELECT
        (SELECT COUNT(*) - COUNT(DISTINCT ID_LIGA_CADREC_ITEMR) FROM SGTPRD.LIGA_CADREC_ITEMREC) AS DUP_LCR,
        (SELECT COUNT(*) - COUNT(DISTINCT CODIGO_REDUZIDO_RECE) FROM SGTPRD.CADASTRO_RECEITAS) AS DUP_CR,
        (SELECT COUNT(*) - COUNT(DISTINCT CODIGO_CLASSIFICACAO) FROM SGTPRD.CLASSIFICACAO_COR) AS DUP_CL
    FROM DUAL
    """
    cols_d, rows_d, _ = run_oracle_with_retry(sql_dim)
    res_d = dict(zip(cols_d, rows_d[0], strict=True))
    assert (
        res_d["DUP_LCR"] == 0
    ), "[FAIL] Chave primária de LIGA_CADREC_ITEMREC duplicada"
    assert res_d["DUP_CR"] == 0, "[FAIL] Chave primária de CADASTRO_RECEITAS duplicada"
    assert res_d["DUP_CL"] == 0, "[FAIL] Chave primária de CLASSIFICACAO_COR duplicada"

    # 3. Alertas de Qualidade Cadastral e Operacional (WARN)
    warns = []
    if res["FLUXO_NC"] > 0:
        warns.append(
            f"[WARN] Itens de produto acabado sem classificação de fluxo (N/C): {res['FLUXO_NC']}"
        )
    if res["KG_MIX_NAO_COBERTO"] > 0:
        warns.append(
            f"[WARN] Volume fora dos 4 grupos de mix de cores: {res['KG_MIX_NAO_COBERTO']} kg"
        )
    if res["QTD_TEMPO_PREV_INVALIDO"] > 0:
        warns.append(
            f"[WARN] Apontamentos com tempo previsto nulo/inválido: {res['QTD_TEMPO_PREV_INVALIDO']}"
        )

    qtd_tempo_real_invalido = res["QTD_TEMPO_REAL_INVALIDO"]
    if qtd_tempo_real_invalido > 0:
        # Detalha as anomalias de tempo real conhecidas
        sql_det_tempo = """
        WITH JANELA AS (
            SELECT ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1)  AS DT_INICIO,
                   TRUNC(SYSDATE, 'MM')                  AS DT_FIM,
                   ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -13) AS DT_INICIO_ANT,
                   ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) AS DT_FIM_ANT
              FROM DUAL
        )
        SELECT UPR.NUMEROUP,
               OBF.NUMERO_OB,
               OBF.SEQUENCIA,
               UPR.NUMERO_MAQUINA,
               OBF.KILOS_PRODUZIDOS,
               TO_CHAR(UPR.DTTEMPOINICONFIRMADO, 'YYYY-MM-DD HH24:MI:SS') AS DT_INI,
               TO_CHAR(UPR.DTTEMPOFINALCONFIRMA, 'YYYY-MM-DD HH24:MI:SS') AS DT_FIM
          FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
          JOIN SGTPRD.UP_ORDEM_MVTO UOM ON UOM.NUMEROUP = UPR.NUMEROUP
          JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
         CROSS JOIN JANELA JAN
         WHERE UPR.SETOR = 5 AND UPR.EXCLUIDA = 0 AND UPR.TIPOUP = 0 AND UPR.STATUS = 0
           AND ((UPR.DTPRODFIM >= JAN.DT_INICIO AND UPR.DTPRODFIM < JAN.DT_FIM)
             OR (UPR.DTPRODFIM >= JAN.DT_INICIO_ANT AND UPR.DTPRODFIM < JAN.DT_FIM_ANT))
           AND OBF.CODIGO_FASE = 40
           AND (UPR.DTTEMPOFINALCONFIRMA IS NULL OR UPR.DTTEMPOINICONFIRMADO IS NULL OR UPR.DTTEMPOFINALCONFIRMA <= UPR.DTTEMPOINICONFIRMADO)
        """
        cols_t, rows_t, _ = run_oracle_with_retry(sql_det_tempo)
        detalhes = [dict(zip(cols_t, r, strict=True)) for r in rows_t]
        warns.append(
            f"[WARN] QTD_TEMPO_REAL_INVALIDO = {qtd_tempo_real_invalido} (início >= fim tratado pelo filtro estrito). Detalhes: {detalhes}"
        )

    if warns:
        for w in warns:
            logger.warning("  %s", w)
        logger.info(
            "  [CLASSIFICAÇÃO: WARN] Invariantes críticas aprovadas, com alertas operacionais conhecidos."
        )
    else:
        logger.info(
            "  [CLASSIFICAÇÃO: PASS] Invariantes críticas e cadastrais totalmente limpas."
        )


# =============================================================================
# 2. TESTES DE SNAPSHOT E REGRESSÃO HISTÓRICA REPRODUZÍVEL
# =============================================================================


def compare_results_against_fixture(
    live_rows: list[dict[str, Any]], fixture_data: dict[str, Any]
) -> None:
    """Compara os números de uma execução contra a fixture da MESMA competência.

    Competência divergente ou resultado vazio é falha: se a comparação fosse
    pulada, o teste passaria sem confrontar nenhum número.
    """
    if not live_rows:
        raise AssertionError(
            "[FAIL] Consulta retornou 0 linhas; nada para comparar com a baseline."
        )
    comp_live = live_rows[0].get("COMPETENCIA")
    comp_fixture = fixture_data.get("competencia")

    if comp_live != comp_fixture:
        raise AssertionError(
            f"[FAIL] Competência retornada ({comp_live}) difere da baseline ({comp_fixture}): "
            "a janela fixa não foi aplicada ou a baseline é de outro mês."
        )

    logger.info("Confrontando execução contra baseline da competência %s...", comp_live)
    live_by_ordem = {r["ORDEM"]: r for r in live_rows}
    base_by_ordem = {r["ORDEM"]: r for r in fixture_data["rows"]}

    divergencias = []
    cols_numericas = [
        "QT_KG",
        "QT_KG_ANO_ANT",
        "VAR_YOY_PCT",
        "MEDIA_KG_DIA",
        "MEDIA_KG_DIA_ANT",
        "VAR_RITMO_PCT",
        "QT_PARTIDAS",
        "CARGA_MEDIA_KG",
        "PERC_ESPECIFICO",
        "TEMPO_PREV_HORAS",
        "TEMPO_REAL_HORAS",
        "DESVIO_TEMPO_MIN",
        "EFIC_TEMPO_PCT",
    ]

    for ordem, base_r in base_by_ordem.items():
        if ordem not in live_by_ordem:
            divergencias.append(f"Linha {ordem} ausente na execução ao vivo")
            continue
        live_r = live_by_ordem[ordem]

        if base_r.get("TIPO_VARIACAO_YOY") != live_r.get("TIPO_VARIACAO_YOY"):
            divergencias.append(
                f"{ordem}.TIPO_VARIACAO_YOY: base={base_r.get('TIPO_VARIACAO_YOY')} vs live={live_r.get('TIPO_VARIACAO_YOY')}"
            )

        for col in cols_numericas:
            v_base = base_r.get(col)
            v_live = live_r.get(col)
            if v_base is None and v_live is None:
                continue
            if v_base is None or v_live is None:
                divergencias.append(f"{ordem}.{col}: base={v_base} vs live={v_live}")
                continue
            if not math.isclose(float(v_base), float(v_live), abs_tol=0.01):
                divergencias.append(f"{ordem}.{col}: base={v_base} vs live={v_live}")

    if divergencias:
        for d in divergencias:
            logger.error("  Divergência de Snapshot: %s", d)
        raise AssertionError(
            f"[FAIL] Detectadas {len(divergencias)} divergências contra a baseline da competência {comp_live}!"
        )

    logger.info("  [OK] Snapshot idêntico à baseline congelada (0 divergências).")


@oracle_live
def test_fixed_window_historical_regression(baseline_fixture: dict[str, Any]) -> None:
    """Executa a lógica operacional sob janela fixa (09/2026 vs 09/2025) e compara com a baseline."""
    logger.info(
        "Executando teste histórico reproduzível via Janela Fixa (09/2026 vs 09/2025)..."
    )
    raw_sql = SQL_FILE.read_text(encoding="utf-8")
    sql_fixa = build_fixed_window_sql(
        raw_sql, "01-09-2026", "01-10-2026", "01-09-2025", "01-10-2025"
    )

    cols, rows, dur_ms = run_oracle_with_retry(sql_fixa)
    logger.info("  Janela fixa executada em %.1f ms (%d linhas)", dur_ms, len(rows))
    live_rows = [dict(zip(cols, r, strict=True)) for r in rows]

    # 1. Valida invariantes do dataset
    report = validate_dataset_invariants(live_rows)
    assert (
        report["status"] != "FAIL"
    ), f"Falha nas invariantes da execução de janela fixa: {report['fails']}"

    # 2. Compara snapshot numérico
    compare_results_against_fixture(live_rows, baseline_fixture)


@oracle_live
def test_live_oracle_execution() -> None:
    """Executa o SQL operacional original (com SYSDATE) e valida invariantes e competência."""
    logger.info("Executando consulta operacional original no Oracle...")
    raw_sql = SQL_FILE.read_text(encoding="utf-8")

    cols, rows, dur_ms = run_oracle_with_retry(raw_sql)
    logger.info(
        "  Consulta operacional executada em %.1f ms (%d linhas)", dur_ms, len(rows)
    )
    live_rows = [dict(zip(cols, r, strict=True)) for r in rows]

    # Só invariantes: dados vivos mudam (lançamento tardio) e, no mês da baseline,
    # a janela SYSDATE coincide com a competência congelada. A baseline é
    # confrontada apenas em `test_fixed_window_historical_regression`.
    assert live_rows, "[FAIL] Consulta operacional retornou 0 linhas."
    report = validate_dataset_invariants(live_rows)
    assert (
        report["status"] != "FAIL"
    ), f"Falha nas invariantes da consulta operacional: {report['fails']}"


def run_performance_benchmark(runs: int = 5) -> None:
    """Executa benchmark de referência no Oracle e relata estatísticas de tempo."""
    logger.info("Iniciando benchmark de performance (%d execuções)...", runs)
    raw_sql = SQL_FILE.read_text(encoding="utf-8")
    tempos: list[float] = []

    for i in range(1, runs + 1):
        _, rows, dur_ms = run_oracle_with_retry(raw_sql)
        tempos.append(dur_ms)
        logger.info("  Rodada %d: %.1f ms (%d linhas)", i, dur_ms, len(rows))

    med = statistics.median(tempos)
    v_min = min(tempos)
    v_max = max(tempos)
    media = statistics.mean(tempos)
    stdev = statistics.stdev(tempos) if len(tempos) > 1 else 0.0

    logger.info("--- RESULTADO BENCHMARK ---")
    logger.info("  Execuções: %d", len(tempos))
    logger.info("  Mediana:   %.1f ms", med)
    logger.info("  Mínimo:    %.1f ms", v_min)
    logger.info("  Máximo:    %.1f ms", v_max)
    logger.info("  Média:     %.1f ms", media)
    logger.info("  DesvPad:   %.1f ms", stdev)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suíte de Testes de Regressão e Invariantes - PCP Produção Mensal"
    )
    parser.add_argument(
        "--live-oracle",
        action="store_true",
        help="Executa testes diretamente contra o banco Oracle",
    )
    parser.add_argument(
        "--fixed-window",
        action="store_true",
        help="Executa teste histórico com janela fixa reproduzível",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Executa rodada de benchmark de performance",
    )
    args = parser.parse_args()

    logger.info(
        "=== SUÍTE DE TESTES DE REGRESSÃO E INVARIANTES (PCP PRODUÇÃO MENSAL) ==="
    )

    # 1. Carrega baseline versionada em fixture
    fixture = load_baseline_fixture()
    test_invariants_on_baseline(fixture)
    logger.info(
        "  [OK] Invariantes internas da fixture baseline integralmente aprovadas."
    )

    # 2. Testes ao vivo no Oracle
    if args.live_oracle or args.fixed_window:
        test_oracle_database_invariants()

    if args.fixed_window:
        test_fixed_window_historical_regression(fixture)

    if args.live_oracle:
        test_live_oracle_execution()

    # 3. Benchmark opcional
    if args.benchmark:
        run_performance_benchmark(runs=5)

    logger.info("=== SUÍTE DE TESTES CONCLUÍDA COM SUCESSO! ===")


if __name__ == "__main__":
    main()

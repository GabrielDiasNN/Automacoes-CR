# pylint: disable=line-too-long, broad-exception-caught, import-error, wrong-import-position
"""Testes dedicados de equivalência para a correção de performance de
vw_sql_px015.sql (20/09/2026).

Não é um teste pytest do acervo (esta pasta é orientada a snapshot, sem
suíte formal) — é um script standalone, para rodar manualmente sempre que
`vw_sql_px015.sql` for alterado de novo, comparando a versão ORIGINAL de
cada bloco reescrito (OPTSTRAGGR/joins diretos) contra a versão NOVA
(LISTAGG/joins decompostos), em OBs reais do Oracle.

Cada `check*` roda a consulta e falha alto se algum valor divergir,
imprimindo o NUMERO_OB e os valores. Não corrige nada sozinho — é só
verificação. Nome sem prefixo `test_` de propósito: conecta no Oracle real e
não deve ser coletado pelo pytest.

Uso (a partir da raiz do repositório):
    .venv/Scripts/python "docs/oracle-schema/consultas/11_views_referencia_sgt/verificar_equivalencia_vw_sql_px015.py"
"""

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "lib" / "python"))
import oracledb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from oracle_extract import init_thick_mode, resolve_oracle_credentials  # noqa: E402

FAILURES: list[str] = []
CREDS: Any = None


def _log(msg: str, level: str = "INFO", exec_id: str = "teste-px015") -> None:
    del exec_id
    print(f"[{level}] {msg}")


def _connect() -> Any:
    return oracledb.connect(user=CREDS.user, password=CREDS.password, dsn=CREDS.dsn)


def _scalar(sql: str) -> Any:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None


def _record(
    nome: str, label: str, value: Any, pair: tuple[Any, Any], lados: tuple[str, str]
) -> None:
    left, right = pair
    status = "OK" if left == right else "DIVERGENTE"
    print(
        f"  [{status}] {nome} ({label}={value}): {lados[0]}={left!r} {lados[1]}={right!r}"
    )
    if left != right:
        FAILURES.append(
            f"{nome} ({label}={value}): {lados[0]}={left!r} != {lados[1]}={right!r}"
        )


def check(nome: str, sql_original: str, sql_novo: str, params: dict[str, Any]) -> None:
    """Compara o valor escalar de duas queries (uma por chave em `params`)."""
    for label, value in params.items():
        original = _scalar(sql_original.format(v=value))
        novo = _scalar(sql_novo.format(v=value))
        _record(nome, label, value, (original, novo), ("original", "novo"))


def check_expected(nome: str, sql: str, params: dict[str, tuple[Any, Any]]) -> None:
    """Confere UMA query contra um valor esperado conhecido. Usado quando não
    há versão "original" para comparar — comparar a query com ela mesma seria
    tautologia e passaria sempre."""
    for label, (value, esperado) in params.items():
        obtido = _scalar(sql.format(v=value))
        _record(nome, label, value, (esperado, obtido), ("esperado", "obtido"))


def _caso_1() -> None:
    print("=" * 70)
    print("1) OBQ — LISTAGG com dedupe vs OPTSTRAGGR(DISTINCT) original")
    print("   (regressão do bug achado em 20/09/2026: perda de DISTINCT)")
    print("=" * 70)
    obq_original = """
        SELECT SGTPRD.OPTSTRAGGR(DISTINCT OBQ1.SEQUENCIA_OB_QUALIDA)
          FROM SGTPRD.OB_QUALIDADE OBQ1
         WHERE OBQ1.SEQUENCIA_OB_QUALIDA = (SELECT MAX(OBQ2.SEQUENCIA_OB_QUALIDA) FROM SGTPRD.OB_QUALIDADE OBQ2 WHERE OBQ2.NUMERO_OB = OBQ1.NUMERO_OB AND OBQ2.SEQUENCIA_FASE<>0)
           AND OBQ1.NUMERO_OB = {v}
    """
    obq_novo = """
        SELECT LISTAGG(v, ',' ON OVERFLOW TRUNCATE) WITHIN GROUP (ORDER BY v) FROM (
          SELECT DISTINCT TO_CHAR(OBQ1D.SEQUENCIA_OB_QUALIDA) v FROM SGTPRD.OB_QUALIDADE OBQ1D
           WHERE OBQ1D.SEQUENCIA_OB_QUALIDA = (SELECT MAX(OBQ2D.SEQUENCIA_OB_QUALIDA) FROM SGTPRD.OB_QUALIDADE OBQ2D WHERE OBQ2D.NUMERO_OB = OBQ1D.NUMERO_OB AND OBQ2D.SEQUENCIA_FASE<>0)
             AND OBQ1D.NUMERO_OB = {v})
    """
    # OBs com múltiplos registros de qualidade no mesmo SEQUENCIA_OB_QUALIDA
    # (caso que expôs o bug original) + algumas OBs "normais" (1 registro só).
    check(
        "OBQ.SQ_OB_QUALIDADE",
        obq_original,
        obq_novo,
        {
            "ob_com_duplicata_conhecida_1": 188005,
            "ob_com_duplicata_conhecida_2": 185185,
            "ob_com_duplicata_conhecida_3": 184949,
            "ob_com_duplicata_conhecida_4": 184948,
        },
    )


def _caso_2() -> None:
    print("=" * 70)
    print("2) TIN — RECEITA_PESADA_NATIVA (única coluna mantida após remover REF)")
    print("=" * 70)
    # Só a subconsulta NATIVA (a fórmula em si). O DECODE por OBFT.STATUS do
    # bloco TIN devolve NULL para OBs fora de STATUS 1/2 — como as OBs de
    # referência avançam de status, comparar o bloco inteiro consigo mesmo
    # dava NULL == NULL e passava sem testar nada.
    receita_sql = """
        SELECT (SELECT CASE WHEN NVL(SUM(MRE.QUANTIDADEPESADA),0) = 0 THEN 0 ELSE 1 END
                  FROM SGTPRD.MOVTO_RECEITA MRE
                 WHERE MRE.NUMEROORDEM = OBFT.NUMERO_OB AND MRE.SEQUENCIAFASEOB = OBFT.SEQUENCIA)
          FROM SGTPRD.OB_FASES OBFT
         WHERE OBFT.NUMERO_OB = {v}
           AND OBFT.CODIGO_FASE = 40
           AND OBFT.SEQUENCIA = (SELECT MAX(OBFT2.SEQUENCIA) FROM SGTPRD.OB_FASES OBFT2 WHERE OBFT2.CODIGO_FASE=40 AND OBFT2.NUMERO_OB = OBFT.NUMERO_OB)
    """
    # Esperados conferidos no Oracle em 24/09/2026. 188135 é o caso
    # documentado no cabeçalho de vw_sql_px015.sql (pesagem só em
    # SEQUENCIAFASEOB=0, nenhuma na sequência atual da fase 40).
    check_expected(
        "TIN.RECEITA_PESADA_NATIVA",
        receita_sql,
        {
            "ob_pesada": (187899, 1),
            "ob_nao_pesada_na_sequencia_atual": (188135, 0),
        },
    )


def _caso_3() -> None:
    print("=" * 70)
    print("3) QT1 — subqueries escalares vs join com GROUP BY original")
    print("=" * 70)
    qt1_original = """
        SELECT SUM(NVL(O4.QTPESOLIQUORIG,0))
          FROM SGTPRD.GERAPECAORIGEMOB O1, SGTPRD.GERAPECACOMPLPECA O4
         WHERE O4.IDPECASPRODUTO(+) = O1.IDPECASPRODUTO AND O1.NUMERO_OB = {v}
    """
    qt1_novo = """
        SELECT SUM(NVL(O4.QTPESOLIQUORIG,0))
          FROM SGTPRD.GERAPECAORIGEMOB O1
          LEFT JOIN SGTPRD.GERAPECACOMPLPECA O4 ON O4.IDPECASPRODUTO = O1.IDPECASPRODUTO
         WHERE O1.NUMERO_OB = {v}
    """
    check(
        "QT1.QT_CRU_ORIG_OB",
        qt1_original,
        qt1_novo,
        {
            "ob_172557": 172557,
            "ob_187623": 187623,
        },
    )


def _caso_4() -> None:
    print("=" * 70)
    print("4) DEFP — CTE deduplicada/sem nulos vs OPTSTRAGGR direto original")
    print("=" * 70)
    defp_original = """
        SELECT SGTPRD.OPTSTRAGGR(DISTINCT GPR9.GRUPO_DEFEITO)
          FROM SGTPRD.GERAPECAORIGEMOB OBQ9, SGTPRD.GERAPECAREVISAO GPR9
         WHERE GPR9.IDPECASPRODUTO = OBQ9.IDPECASPRODUTO AND OBQ9.NUMERO_OB = {v}
    """
    defp_novo = """
        SELECT LISTAGG(TO_CHAR(GRUPO_DEFEITO), ',' ON OVERFLOW TRUNCATE) WITHIN GROUP (ORDER BY TO_CHAR(GRUPO_DEFEITO)) FROM (
          SELECT DISTINCT OBQ9.NUMERO_OB, GPR9.GRUPO_DEFEITO
            FROM SGTPRD.GERAPECAORIGEMOB OBQ9, SGTPRD.GERAPECAREVISAO GPR9
           WHERE GPR9.IDPECASPRODUTO = OBQ9.IDPECASPRODUTO
             AND (GPR9.GRUPO_DEFEITO IS NOT NULL OR GPR9.TIPO_DEFEITO IS NOT NULL)
             AND OBQ9.NUMERO_OB = {v})
    """
    # 187426/187425: 2 grupos de defeito distintos (exercita DISTINCT e ordem
    # do LISTAGG). 18439 não tem mais revisão e dava None == None.
    check(
        "DEFP.GR_DEFEITO",
        defp_original,
        defp_novo,
        {
            "ob_com_2_grupos_defeito_1": 187426,
            "ob_com_2_grupos_defeito_2": 187425,
        },
    )


def _caso_5() -> None:
    print("=" * 70)
    print("5) OB_FAT_TOTAL — CTEs pré-agregadas vs GROUP BY+HAVING original")
    print("=" * 70)
    obft_original = """
        SELECT COUNT(*) FROM (
          SELECT DE1.NUMERO_OB NR_OB, COUNT(DE1.IDPECASPRODUTO) QT_PC_OB, DE5.QT_PC_ROM_FAT
            FROM SGTPRD.GERAPECADESTINOOB DE1,
                 (SELECT DE4.NUMERO_OB NR_OB, COUNT(DE2.IDPECASPRODUTO) QT_PC_ROM_FAT
                    FROM SGTPRD.PECAS_ROMANEIO_SAIDA DE2, SGTPRD.ROMANEIO DE3, SGTPRD.GERAPECADESTINOOB DE4
                   WHERE DE3.NUMERO_ROMANEIO = DE2.NUMERO_ROMANEIO_SAID AND DE4.IDPECASPRODUTO = DE2.IDPECASPRODUTO AND DE3.STATUS IN (4,6)
                   GROUP BY DE4.NUMERO_OB) DE5
           WHERE DE5.NR_OB = DE1.NUMERO_OB AND DE1.NUMERO_OB = {v}
           GROUP BY DE1.NUMERO_OB, DE5.QT_PC_ROM_FAT
          HAVING COUNT(DE1.IDPECASPRODUTO)= DE5.QT_PC_ROM_FAT
        )
    """
    obft_novo = """
        SELECT COUNT(*) FROM (
          SELECT DE1.NUMERO_OB, COUNT(DE1.IDPECASPRODUTO) QT_PC_OB
            FROM SGTPRD.GERAPECADESTINOOB DE1 WHERE DE1.NUMERO_OB = {v} GROUP BY DE1.NUMERO_OB
        ) A
        JOIN (
          SELECT DE4.NUMERO_OB NR_OB, COUNT(DE2.IDPECASPRODUTO) QT_PC_ROM_FAT
            FROM SGTPRD.PECAS_ROMANEIO_SAIDA DE2, SGTPRD.ROMANEIO DE3, SGTPRD.GERAPECADESTINOOB DE4
           WHERE DE3.NUMERO_ROMANEIO = DE2.NUMERO_ROMANEIO_SAID AND DE4.IDPECASPRODUTO = DE2.IDPECASPRODUTO AND DE3.STATUS IN (4,6) AND DE4.NUMERO_OB = {v}
           GROUP BY DE4.NUMERO_OB
        ) D ON D.NR_OB = A.NUMERO_OB
        WHERE A.QT_PC_OB = D.QT_PC_ROM_FAT
    """
    # 188200: 48/48 peças faturadas (entra, COUNT=1).
    # 187335: faturada 50/50 em 29/09/2026 (entra, COUNT=1).
    # 188005: 0/16 faturadas (não entra, COUNT=0).
    check(
        "OB_FAT_TOTAL (aparece só se contagens batem)",
        obft_original,
        obft_novo,
        {
            "ob_100pct_faturada_1": 188200,
            "ob_100pct_faturada_2": 187335,
            "ob_nao_faturada": 188005,
        },
    )
    check_expected(
        "OB_FAT_TOTAL (novo) contra esperado",
        obft_novo,
        {
            "ob_100pct_faturada_1": (188200, 1),
            "ob_100pct_faturada_2": (187335, 1),
            "ob_nao_faturada": (188005, 0),
        },
    )


def _caso_6() -> None:
    print("=" * 70)
    print("6) TERC — ST_TERCEIROS direto (F.STATUS) vs SYSENUMERATE original")
    print("=" * 70)
    terc_original = """
        SELECT MAX(ENU.SEQENUMVALUE)
          FROM SGTPRD.OB_FASES F
          JOIN SGTPRD.FASES_FLUXO FF ON FF.CODIGO_FASE = F.CODIGO_FASE
          JOIN SGTPRD.SYSENUMERATE ENU ON ENU.SEQENUMVALUE = F.STATUS AND TRIM(ENU.ENUMERATE) = 'TOBFASESSTATUS'
         WHERE F.NUMERO_OB = {v} AND FF.PROCESSOTERCEIROS = '1'
           AND F.SEQUENCIA = (SELECT MAX(L.SEQUENCIA) FROM SGTPRD.OB_FASES L WHERE L.NUMERO_OB = F.NUMERO_OB AND L.CODIGO_FASE = F.CODIGO_FASE)
    """
    terc_novo = """
        SELECT MAX(F.STATUS)
          FROM SGTPRD.OB_FASES F
          JOIN SGTPRD.FASES_FLUXO FF ON FF.CODIGO_FASE = F.CODIGO_FASE
         WHERE F.NUMERO_OB = {v} AND FF.PROCESSOTERCEIROS = '1'
           AND F.SEQUENCIA = (SELECT MAX(L.SEQUENCIA) FROM SGTPRD.OB_FASES L WHERE L.NUMERO_OB = F.NUMERO_OB AND L.CODIGO_FASE = F.CODIGO_FASE)
    """
    check(
        "TERC.ST_TERCEIROS",
        terc_original,
        terc_novo,
        {
            "ob_terceiro_1": 188005,
            "ob_terceiro_2": 188200,
            "ob_terceiro_3": 187335,
        },
    )


def _caso_7() -> None:
    print("=" * 70)
    print("7) TIN — Bloco Lateral Direto vs 3 níveis de subqueries original")
    print("=" * 70)
    tin_original = """
        SELECT M.CODIGO_GRUPO
          FROM (
                SELECT J.NUMERO_OB, J.CODIGO_GRUPO
                  FROM (
                        SELECT OBFT.NUMERO_OB, OBFT.SEQUENCIA, OBFT.CODIGO_GRUPO
                          FROM SGTPRD.OB_FASES          OBFT
                          JOIN SGTPRD.MOVIMENTO_MAQUINA MOV
                            ON MOV.NUMERO_ORDEM = DECODE(OBFT.CODIGO_GRUPO, 0, OBFT.NUMERO_OB, OBFT.CODIGO_GRUPO)
                           AND MOV.SEQUENCIA    = DECODE(OBFT.CODIGO_GRUPO, 0, OBFT.SEQUENCIA, 0)
                         WHERE OBFT.CODIGO_FASE = 40
                       ) J
                  JOIN (
                        SELECT OBFT.NUMERO_OB, OBFT.SEQUENCIA
                          FROM SGTPRD.OB_FASES OBFT
                         WHERE OBFT.CODIGO_FASE = 40
                           AND OBFT.SEQUENCIA   = (SELECT MAX(OBFT2.SEQUENCIA) FROM SGTPRD.OB_FASES OBFT2 WHERE OBFT2.CODIGO_FASE = 40 AND OBFT2.NUMERO_OB = OBFT.NUMERO_OB)
                       ) S ON S.NUMERO_OB = J.NUMERO_OB AND S.SEQUENCIA = J.SEQUENCIA
               ) M
         WHERE M.NUMERO_OB = {v}
    """
    tin_novo = """
        SELECT OBFT.CODIGO_GRUPO
          FROM SGTPRD.OB_FASES OBFT
          JOIN SGTPRD.MOVIMENTO_MAQUINA MOV
            ON MOV.NUMERO_ORDEM = DECODE(OBFT.CODIGO_GRUPO, 0, OBFT.NUMERO_OB, OBFT.CODIGO_GRUPO)
           AND MOV.SEQUENCIA    = DECODE(OBFT.CODIGO_GRUPO, 0, OBFT.SEQUENCIA, 0)
         WHERE OBFT.NUMERO_OB = {v}
           AND OBFT.CODIGO_FASE = 40
         ORDER BY OBFT.SEQUENCIA DESC
         FETCH FIRST 1 ROWS ONLY
    """
    check(
        "TIN.CD_GR_TINGIMENTO",
        tin_original,
        tin_novo,
        {
            "ob_tingimento_1": 188005,
            "ob_tingimento_2": 188200,
            "ob_tingimento_3": 187335,
        },
    )


def main() -> None:
    global CREDS  # pylint: disable=global-statement
    load_dotenv(REPO_ROOT / ".env", override=True)
    CREDS = resolve_oracle_credentials(_log, "teste-px015")
    if CREDS is None:
        print("Credenciais Oracle ausentes/invalidas no ambiente (.env).")
        sys.exit(1)
    init_thick_mode(CREDS, _log, "teste-px015")
    _caso_1()
    print()
    _caso_2()
    print()
    _caso_3()
    print()
    _caso_4()
    print()
    _caso_5()
    print()
    _caso_6()
    print()
    _caso_7()

    print()
    print("=" * 70)
    if FAILURES:
        print(f"RESULTADO: {len(FAILURES)} DIVERGÊNCIA(S) ENCONTRADA(S)")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("RESULTADO: todas as comparações bateram (original == novo).")


if __name__ == "__main__":
    main()

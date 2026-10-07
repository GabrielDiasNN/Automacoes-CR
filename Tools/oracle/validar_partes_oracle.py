"""Valida partes pequenas das consultas pesadas do acervo SQL.

Este utilitário é complementar a ``validar_sql_oracle.py``: quando o relatório
inteiro é cancelado pelo Oracle por custo de parse/plano, ele confronta os
joins e filtros físicos mais importantes em SELECTs limitados a uma linha.
Cada instrução passa pelo ``guard_sql.py`` antes de chegar ao banco.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from oracle_catalog import _raise_if_expired, _run_with_timeout  # noqa: E402
from oracle_extract import init_thick_mode, resolve_oracle_credentials  # noqa: E402
from oracle_session import connect_within, is_session_drop  # noqa: E402
from validar_sql_oracle import portable_command, resolve_guard  # noqa: E402

VALIDATOR_VERSION = "2.1.0"


def _log(*_args: Any, **_kwargs: Any) -> None:
    """Não imprime DSN, usuário ou dados retornados."""


def _guard(sql: str, guard: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(guard), "--sql", sql],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = (result.stdout or result.stderr).strip()
    return result.returncode, output[-1000:]


def _summary(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:500]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _retryable(exc: BaseException) -> bool:
    return is_session_drop(exc)


def _case(name: str, file: str, sql: str, timeout_ms: int = 15000) -> dict[str, Any]:
    return {"name": name, "file": file, "sql": sql, "timeout_ms": timeout_ms}


def _saldo_case(name: str, file: str, filtro: str) -> dict[str, Any]:
    """Valida o núcleo físico que substitui GERASALDOESTOQUE.

    A expressão reproduz a regra observada na view legada: somente movimentos
    ativos (STMOVIMENTO = 0), com saída negativa para TIOPERACAO = 2, e
    separação entre saldo disponível e bloqueado.
    """
    sql = f"""
        WITH SALDO_ESTOQUE AS (
            SELECT M.CDREDUZIDO,
                   M.CDDEPOSITO,
                   M.IDGERAATRIESTO,
                   ROUND(SUM(CASE
                                 WHEN M.STGERAESTOBLOQ = '0' AND M.STMOVIMENTO = 0
                                 THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END
                                 ELSE 0
                             END), 6) AS QTDISPONIVEL,
                   ROUND(SUM(CASE
                                 WHEN M.STGERAESTOBLOQ = '1' AND M.STMOVIMENTO = 0
                                 THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END
                                 ELSE 0
                             END), 6) AS QTBLOQUEADA,
                   TRUNC(GREATEST(0, SUM(CASE
                                              WHEN M.STGERAESTOBLOQ = '0' AND M.STMOVIMENTO = 0
                                              THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.NRVOLUMES ELSE M.NRVOLUMES END
                                              ELSE 0
                                          END))) AS NRVOLUMES
              FROM SGTPRD.GERAMOVIMENTOESTOQUE M
              JOIN SGTPRD.GERAPARAMSISTFILIAL G ON G.CDFILIAL = M.CDFILIAL
             WHERE {filtro}
               AND ((M.DTDOCUMENTO > G.DATA_FECHAMENTO_EST) OR G.DATA_FECHAMENTO_EST IS NULL)
               AND M.DTDOCUMENTO > (SELECT MIN(X.DATA_FECHAMENTO_EST)
                                       FROM SGTPRD.GERAPARAMSISTFILIAL X)
               AND NOT (M.NRTIPOMOVIMENTO = 999
                        AND M.DTDOCUMENTO > G.DATA_FECHAMENTO_EST + 2)
             GROUP BY M.CDREDUZIDO, M.CDDEPOSITO, M.IDGERAATRIESTO
        )
        SELECT CDREDUZIDO, CDDEPOSITO, IDGERAATRIESTO,
               QTDISPONIVEL, QTBLOQUEADA, NRVOLUMES
          FROM SALDO_ESTOQUE
         WHERE QTDISPONIVEL <> 0
         FETCH FIRST 1 ROWS ONLY
    """  # nosec B608 - `filtro` vem só de literais de `_cases()`, nunca de entrada externa
    return _case(name, file, sql, timeout_ms=30000)


def _cases() -> list[dict[str, Any]]:
    qld = "06_qualidade_auditoria_obs/qld_conferencia_ob_montada_conferir_se_usaram_as_pecas_com_restricao.sql"
    monitor = (
        "06_qualidade_auditoria_obs/qld_monitoramento_nf_entrada_ciclo_completo.sql"
    )
    com = "07_expedicao_pedidos_comercial/com_obs_e_romaneios_em_aberto.sql"
    atrasados = "07_expedicao_pedidos_comercial/com_consulta_pedidos_atrasados.sql"
    mal = "03_malharia_teares/mal_necessidade_critica_somente_faltas.sql"
    detalhado = "templates/bnf_producao_beneficiamento_detalhado.sql"  # runtime: Produção Beneficimento/sql/templates
    return [
        _saldo_case(
            "stock_saldo_quimico",
            "01_beneficiamento_tingimento/bnf_monitoramento_atributos_produtos_quimicos.sql",
            "M.CDDEPOSITO = 20 AND M.IDGERAATRIESTO = 4",
        ),
        _saldo_case(
            "stock_saldo_fibras",
            "04_fiacao_fios/fia_estoque_de_fibras_disponiveis_atual.sql",
            "M.CDDEPOSITO IN (307, 311, 310, 313, 321, 320, 323, 337)",
        ),
        _saldo_case(
            "stock_saldo_fios",
            "04_fiacao_fios/fia_estoque_de_fios_disponiveis_atual.sql",
            "M.CDDEPOSITO IN (114, 314, 324, 317, 327)",
        ),
        _case(
            "stock_saldo_fornecedor",
            "04_fiacao_fios/fia_lotes_fios_fornecedor.sql",
            """
            WITH LOTES_ALVO AS (
                SELECT /*+ MATERIALIZE */ DISTINCT L.CODIGO_REDUZIDO_FIO
                  FROM SGTPRD.LOTES_FIO_PRODUTO L
                 WHERE TRIM(L.LOTE_FIO) IN ('C053SI0006', 'CO535I0006')
            ), SALDO_ESTOQUE AS (
                SELECT /*+ LEADING(A M G) USE_NL(M) INDEX(M GME_IND_GERAMOVIESTOREDU) */
                       M.CDREDUZIDO,
                       ROUND(SUM(CASE
                                     WHEN M.STGERAESTOBLOQ = '0' AND M.STMOVIMENTO = 0
                                     THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END
                                     ELSE 0
                                 END), 6) AS QTDISPONIVEL,
                       ROUND(SUM(CASE
                                     WHEN M.STGERAESTOBLOQ = '1' AND M.STMOVIMENTO = 0
                                     THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END
                                     ELSE 0
                                 END), 6) AS QTBLOQUEADA
                  FROM LOTES_ALVO A
                  JOIN SGTPRD.GERAMOVIMENTOESTOQUE M
                    ON M.CDREDUZIDO = A.CODIGO_REDUZIDO_FIO
                  JOIN SGTPRD.GERAPARAMSISTFILIAL G ON G.CDFILIAL = M.CDFILIAL
                 WHERE ((M.DTDOCUMENTO > G.DATA_FECHAMENTO_EST) OR G.DATA_FECHAMENTO_EST IS NULL)
                   AND M.DTDOCUMENTO > (SELECT MIN(X.DATA_FECHAMENTO_EST)
                                           FROM SGTPRD.GERAPARAMSISTFILIAL X)
                   AND NOT (M.NRTIPOMOVIMENTO = 999
                            AND M.DTDOCUMENTO > G.DATA_FECHAMENTO_EST + 2)
                 GROUP BY M.CDREDUZIDO
            )
            SELECT L.CODIGO_REDUZIDO_FIO,
                   S.QTDISPONIVEL + S.QTBLOQUEADA AS QT_KG
              FROM SGTPRD.LOTES_FIO_PRODUTO L
              JOIN SALDO_ESTOQUE S ON S.CDREDUZIDO = L.CODIGO_REDUZIDO_FIO
             WHERE TRIM(L.LOTE_FIO) IN ('C053SI0006', 'CO535I0006')
             FETCH FIRST 1 ROWS ONLY
            """,
            timeout_ms=30000,
        ),
        _case(
            "stock_enum_physical",
            "06_qualidade_auditoria_obs/qld_conferencia_pecas_com_peso_menor_que_17kg.sql",
            """
            SELECT ENI.SEQUENCE, UPPER(ENI.DESCRIPTION)
              FROM SGTPRD.XX2_ENUMERATES ENU
              JOIN SGTPRD.XX2_ENUMITEM ENI ON ENI.IDENUMERATE = ENU.ID
             WHERE ENU.NAME LIKE '%TTIPODOCUMENTOENTRADAPECA%'
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "qld_fase_atual",
            qld,
            """
            SELECT NUMERO_OB, DESCRICAO_FASE
              FROM (
                    SELECT OBF.NUMERO_OB,
                           TRIM(FFL.DESCRICAO_FASE) AS DESCRICAO_FASE,
                           ROW_NUMBER() OVER (
                               PARTITION BY OBF.NUMERO_OB
                               ORDER BY OBF.SEQUENCIA DESC
                           ) AS RN
                      FROM SGTPRD.OB_FASES OBF
                      JOIN SGTPRD.FASES_FLUXO FFL
                        ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
                     WHERE OBF.NUMERO_OB = (
                               SELECT MIN(NUMERO_OB) FROM SGTPRD.OB_FASES
                           )
                   )
             WHERE RN = 1
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "qld_operador_fase",
            qld,
            """
            WITH ALVO AS (
                SELECT MIN(NUMERO_OB) AS NUMERO_OB
                  FROM SGTPRD.OB_FASES
            ), F10 AS (
                SELECT OBF.NUMERO_OB, MIN(OBF.SEQUENCIA) AS SEQUENCIA
                  FROM SGTPRD.OB_FASES OBF
                  JOIN ALVO A ON A.NUMERO_OB = OBF.NUMERO_OB
                 WHERE OBF.CODIGO_FASE = 10
                 GROUP BY OBF.NUMERO_OB
            )
            SELECT OBF.NUMERO_OB, MAX(TRIM(OPE.NOME)) AS OPERADOR
              FROM SGTPRD.OB_FASES OBF
              JOIN F10
                ON F10.NUMERO_OB = OBF.NUMERO_OB
               AND F10.SEQUENCIA = OBF.SEQUENCIA
              JOIN SGTPRD.OPERADOR OPE
                ON OPE.CODIGO = OBF.OPERADOR_FINAL
              JOIN ALVO A
                ON A.NUMERO_OB = OBF.NUMERO_OB
             WHERE OBF.CODIGO_FASE = 10
             GROUP BY OBF.NUMERO_OB
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "qld_pecas_qualidade",
            qld,
            """
            SELECT ORI.NUMERO_OB, ORI.IDPECASPRODUTO,
                   GPP.QTLIQUIDA, GPC.FINALIDADE
              FROM SGTPRD.GERAPECAORIGEMOB ORI
              JOIN SGTPRD.GERAPECASPRODUTO GPP
                ON GPP.IDPECASPRODUTO = ORI.IDPECASPRODUTO
              JOIN SGTPRD.GERAPECACOMPLPECA GPC
                ON GPC.IDPECASPRODUTO = ORI.IDPECASPRODUTO
             WHERE GPP.PADRAO_QUALIDADE_SIN = 1
               AND GPP.DATA_DA_ENTRADA_PECA >= TO_NUMBER(TO_CHAR(SYSDATE - 90, 'YYYYMMDD'))
               AND GPP.TIDOCUMENTOENTRADA <> 8
               AND ORI.NUMERO_OB = (
                       SELECT MIN(NUMERO_OB) FROM SGTPRD.GERAPECAORIGEMOB
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "qld_base_filtrada",
            qld,
            """
            SELECT OB.NUMERO_OB, OBP.TOTAL_PECAS_CONFIRM,
                   OBF.STATUS, CORX.CODIGO_CLASSIFICACAO
              FROM SGTPRD.OB OB
              JOIN SGTPRD.OB_PRODUTO OBP
                ON OBP.NUMERO_OB = OB.NUMERO_OB
              JOIN SGTPRD.OB_FASES OBF
                ON OBF.NUMERO_OB = OB.NUMERO_OB
               AND OBF.CODIGO_FASE = 10
              JOIN SGTPRD.ENGEITEMESTOCOR COR
                ON COR.CDREDUZIDO = OB.CODIGO_REDUZIDO
              JOIN SGTPRD.COR CORX
                ON CORX.CODIGO_COR = COR.CDCOR
             WHERE OBF.STATUS = 4
               AND OB.TIPO_ORDEM = 0
               AND OB.TIPO_GERACAO = 0
               AND OBF.DATA_EMISSAO >= TO_NUMBER(TO_CHAR(SYSDATE - 180, 'YYYYMMDD'))
               AND CORX.CODIGO_CLASSIFICACAO IN (6, 9)
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "monitor_nf_cru",
            monitor,
            """
            SELECT GNE.IDPECASPRODUTO, GNE.NUMERO_NOTA,
                   GP.QTLIQUIDA, GP.CODIGO_DEPOSITO, GOB.NUMERO_OB
              FROM SGTPRD.GERAPECANOTAENTRADA GNE
              JOIN SGTPRD.GERAPECASPRODUTO GP
                ON GP.IDPECASPRODUTO = GNE.IDPECASPRODUTO
              LEFT JOIN SGTPRD.GERAPECAORIGEMOB GOB
                ON GOB.IDPECASPRODUTO = GNE.IDPECASPRODUTO
             WHERE GNE.NUMERO_NOTA = 35919
               AND GNE.IDPESSOAFJ = 1
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "monitor_movimento_peca",
            monitor,
            """
            SELECT GPM.IDPECASPRODUTO, MOV.NRTIPOMOVIMENTO,
                   GMEO.DTOPERACAO
              FROM SGTPRD.GERAPECAMOVIMENTO GPM
              JOIN SGTPRD.GERAMOVIMENTOESTOQUE MOV
                ON MOV.ID = GPM.NUMERO_MOVIMENTO
              JOIN SGTPRD.GERAMOVIESTOOPER GMEO
                ON GMEO.IDGERAMOVIESTO = MOV.ID
               AND GMEO.TIOPERACAO = 0
             WHERE GPM.IDPECASPRODUTO IN (
                       SELECT GNE.IDPECASPRODUTO
                         FROM SGTPRD.GERAPECANOTAENTRADA GNE
                        WHERE GNE.NUMERO_NOTA = 35919
                          AND GNE.IDPESSOAFJ = 1
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "monitor_qualidade_ob",
            monitor,
            """
            SELECT OBQ.NUMERO_OB, OBQ.QUANTIDADE_REJEITADA,
                   OBQ.DESTINO, OBQ.TIPO_DEFEITO
              FROM SGTPRD.OB_QUALIDADE OBQ
             WHERE OBQ.NUMERO_OB IN (
                       SELECT DISTINCT GOB.NUMERO_OB
                         FROM SGTPRD.GERAPECANOTAENTRADA GNE
                         JOIN SGTPRD.GERAPECAORIGEMOB GOB
                           ON GOB.IDPECASPRODUTO = GNE.IDPECASPRODUTO
                        WHERE GNE.NUMERO_NOTA = 35919
                          AND GNE.IDPESSOAFJ = 1
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "monitor_ob_info",
            monitor,
            """
            SELECT O.NUMERO_OB, O.STATUS, O.CODIGO_REDUZIDO,
                   OBF.CODIGO_FASE, OBF.STATUS AS STATUS_FASE
              FROM SGTPRD.OB O
              LEFT JOIN SGTPRD.OB_FASES OBF
                ON OBF.NUMERO_OB = O.NUMERO_OB
             WHERE O.NUMERO_OB IN (
                       SELECT DISTINCT GOB.NUMERO_OB
                         FROM SGTPRD.GERAPECANOTAENTRADA GNE
                         JOIN SGTPRD.GERAPECAORIGEMOB GOB
                           ON GOB.IDPECASPRODUTO = GNE.IDPECASPRODUTO
                        WHERE GNE.NUMERO_NOTA = 35919
                          AND GNE.IDPESSOAFJ = 1
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "monitor_destino_ob",
            monitor,
            """
            SELECT GDO.NUMERO_OB, GP.IDPECASPRODUTO,
                   GP.QTLIQUIDA, PRS.NUMERO_ROMANEIO_SAID
              FROM SGTPRD.GERAPECADESTINOOB GDO
              JOIN SGTPRD.GERAPECASPRODUTO GP
                ON GP.IDPECASPRODUTO = GDO.IDPECASPRODUTO
              LEFT JOIN SGTPRD.PECAS_ROMANEIO_SAIDA PRS
                ON PRS.IDPECASPRODUTO = GP.IDPECASPRODUTO
             WHERE GDO.NUMERO_OB IN (
                       SELECT DISTINCT GOB.NUMERO_OB
                         FROM SGTPRD.GERAPECANOTAENTRADA GNE
                         JOIN SGTPRD.GERAPECAORIGEMOB GOB
                           ON GOB.IDPECASPRODUTO = GNE.IDPECASPRODUTO
                        WHERE GNE.NUMERO_NOTA = 35919
                          AND GNE.IDPESSOAFJ = 1
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "com_status_enums",
            com,
            """
            SELECT ENI.SEQUENCE, ENI.DESCRIPTION
              FROM SGTPRD.XX2_ENUMERATES ENU
              JOIN SGTPRD.XX2_ENUMITEM ENI ON ENI.IDENUMERATE = ENU.ID
             WHERE ENU.NAME LIKE 'TSITUACAOPEDCOM%'
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "com_pedidos",
            com,
            """
            SELECT PPOB.NUMEROOB, IPG.PEDIDO, IPG.ITEMPEDIDO,
                   ITP.SITUACAOITEM, PED.PEDIDOCLIENTE
              FROM SGTPRD.PEDPRODUCAOOB PPOB
              JOIN SGTPRD.PEDPRODUCAO PP ON PP.NUMERO = PPOB.NUMERO
              JOIN SGTPRD.OFORDENS OFO
                ON OFO.NUMEROPEDPRODUCAO = PP.NUMERO
               AND OFO.REDUZIDO = PPOB.REDUZIDO
              JOIN SGTPRD.OFPEDIDO OFP
                ON OFP.NUMEROOF = OFO.NUMEROOF
               AND OFP.NIVEL = OFO.NIVEL
              JOIN SGTPRD.ITENSPEDIDOQTDES IPQ
                ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
              JOIN SGTPRD.ITENSPEDIDOGRADE IPG
                ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
              JOIN SGTPRD.ITENSPEDIDOCOMERCIAL ITP
                ON ITP.PEDIDO = IPG.PEDIDO AND ITP.ITEMPEDIDO = IPG.ITEMPEDIDO
              JOIN SGTPRD.PEDIDOCOMERCIAL PED ON PED.PEDIDO = IPG.PEDIDO
             WHERE PPOB.NUMEROOB = (
                       SELECT MIN(NUMEROOB) FROM SGTPRD.PEDPRODUCAOOB
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "com_ob_base",
            com,
            """
            SELECT OB.NUMERO_OB, OB.CODIGO_REDUZIDO,
                   OP.TOTAL_PECAS, OP.KILOS_PROGRAMADOS,
                   PPOB.OBMONTADA
              FROM SGTPRD.OB OB
              JOIN SGTPRD.OB_PRODUTO OP ON OP.NUMERO_OB = OB.NUMERO_OB
              LEFT JOIN SGTPRD.PEDPRODUCAOOB PPOB
                ON PPOB.NUMEROOB = OB.NUMERO_OB AND PPOB.SETOR = 5
             WHERE OB.TIPO_ORDEM IN (0, 6)
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "com_pecas_acabadas",
            com,
            """
            SELECT DES.NUMERO_OB, GPP.IDPECASPRODUTO, GPP.QTLIQUIDA
              FROM SGTPRD.GERAPECADESTINOOB DES
              JOIN SGTPRD.GERAPECASPRODUTO GPP
                ON GPP.IDPECASPRODUTO = DES.IDPECASPRODUTO
             WHERE DES.NUMERO_OB = (
                       SELECT MIN(NUMERO_OB) FROM SGTPRD.GERAPECADESTINOOB
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "com_pecas_cruas",
            com,
            """
            SELECT ORI.NUMERO_OB, GPP.IDPECASPRODUTO,
                   GPP.QTLIQUIDA, GPP.LOTE_PRODUTO
              FROM SGTPRD.GERAPECAORIGEMOB ORI
              JOIN SGTPRD.GERAPECASPRODUTO GPP
                ON GPP.IDPECASPRODUTO = ORI.IDPECASPRODUTO
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "com_romaneio",
            com,
            """
            SELECT RSA.IDPECASPRODUTO, RSA.NUMERO_ROMANEIO_SAID,
                   PRO.NUMERO_PEDIDO, ROM.STATUS
              FROM SGTPRD.GERAPECAROMSAIDA RSA
              JOIN SGTPRD.PRODUTO_ROMANEIO PRO
                ON PRO.IDPRODUTO_ROMANEIO = RSA.IDPRODUTO_ROMANEIO
              JOIN SGTPRD.ROMANEIO ROM
                ON ROM.NUMERO_ROMANEIO = RSA.NUMERO_ROMANEIO_SAID
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "atrasados_pedido_ob",
            atrasados,
            """
            SELECT IPG.PEDIDO, IPG.ITEMPEDIDO, PPOB.NUMEROOB,
                   PED.PEDIDOCLIENTE, OB.STATUS
              FROM SGTPRD.PEDPRODUCAOOB PPOB
              JOIN SGTPRD.PEDPRODUCAO PP ON PP.NUMERO = PPOB.NUMERO
              JOIN SGTPRD.OFORDENS OFO
                ON OFO.NUMEROPEDPRODUCAO = PP.NUMERO
               AND OFO.REDUZIDO = PPOB.REDUZIDO
              JOIN SGTPRD.OFPEDIDO OFP ON OFP.NUMEROOF = OFO.NUMEROOF
              JOIN SGTPRD.ITENSPEDIDOQTDES IPQ
                ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
              JOIN SGTPRD.ITENSPEDIDOGRADE IPG
                ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
              JOIN SGTPRD.PEDIDOCOMERCIAL PED ON PED.PEDIDO = IPG.PEDIDO
              JOIN SGTPRD.OB OB ON OB.NUMERO_OB = PPOB.NUMEROOB
             WHERE OFP.QUANTIDADE_ATUAL <> 0
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "atrasados_fase",
            atrasados,
            """
            SELECT OBF.NUMERO_OB, OBF.CODIGO_FASE,
                   FFL.DESCRICAO_FASE, OBF.STATUS
              FROM SGTPRD.OB_FASES OBF
              JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
             WHERE OBF.STATUS <> 4
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "atrasados_origem_ob",
            atrasados,
            """
            SELECT ORI.NUMERO_OB, GPP.QTLIQUIDA
              FROM SGTPRD.GERAPECAORIGEMOB ORI
              JOIN SGTPRD.GERAPECASPRODUTO GPP
                ON GPP.IDPECASPRODUTO = ORI.IDPECASPRODUTO
             WHERE ORI.NUMERO_OB = (
                       SELECT MIN(NUMERO_OB) FROM SGTPRD.GERAPECAORIGEMOB
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "atrasados_ob_produto",
            atrasados,
            """
            SELECT OBE.NUMERO_OB, OBP.KILOS_PROGRAMADOS,
                   OBP.METROS_PROGRAMADOS, ITE.IDUNIDADEMEDIDA
              FROM SGTPRD.OB OBE
              JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = OBE.NUMERO_OB
              JOIN SGTPRD.ITENS_ESTOQUE ITE
                ON ITE.CODIGO_REDUZIDO = OBE.CODIGO_REDUZIDO
              JOIN SGTPRD.UNIDADE_MEDIDA UND
                ON UND.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "mal_opm_rel",
            mal,
            """
            SELECT M.NUMERO_MAQUINA,
                   MIN(O.NUMERO_ORDEM) AS NUMERO_ORDEM
              FROM SGTPRD.MAQUINA M
              LEFT JOIN SGTPRD.ORDEM_PRODUCAO_MALHA O
                ON O.NUMERO_MAQUINA = M.NUMERO_MAQUINA
               AND O.STATUS IN (1, 2, 3)
             WHERE M.SETOR IN (4, 7)
               AND M.CODIGO_UNIDADE_FABRI = '00005'
               AND M.TIPO_MAQUINA IN (145, 146)
             GROUP BY M.NUMERO_MAQUINA
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "mal_peso_padrao",
            mal,
            """
            SELECT ART.CDREDUZIDO, AVG(PCR.PESO_METROS_PECA) AS PESO_PADRAO
              FROM SGTPRD.PESO_PADRAO_PECA PCR
              JOIN SGTPRD.ENGEITEMESTOARTCRU ART
                ON ART.CDREDUZIDO = PCR.CODIGO_REDUZIDO_PROD
             GROUP BY ART.CDREDUZIDO
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "mal_pedido",
            mal,
            """
            SELECT PPOB.NUMEROOB, PED.PEDIDOCLIENTE
              FROM SGTPRD.OFPEDIDO OFP
              JOIN SGTPRD.ITENSPEDIDOQTDES IPQ
                ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
              JOIN SGTPRD.ITENSPEDIDOGRADE IPG
                ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
              JOIN SGTPRD.OFORDENS OFO ON OFO.NUMEROOF = OFP.NUMEROOF
              JOIN SGTPRD.PEDPRODUCAO PP
                ON PP.NUMERO = OFO.NUMEROPEDPRODUCAO
              JOIN SGTPRD.PEDPRODUCAOOB PPOB ON PPOB.NUMERO = PP.NUMERO
              JOIN SGTPRD.PEDIDOCOMERCIAL PED ON PED.PEDIDO = IPG.PEDIDO
             WHERE PPOB.NUMEROOB = (
                       SELECT MIN(NUMEROOB) FROM SGTPRD.PEDPRODUCAOOB
                   )
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "mal_estoque",
            mal,
            """
            SELECT GPP.CODIGO_REDUZIDO_PROD,
                   GPP.CODIGO_DEPOSITO, GPP.IDPECASPRODUTO
              FROM SGTPRD.GERAPECASPRODUTO GPP
              JOIN SGTPRD.GERAPECACOMPLPECA GPC
                ON GPP.IDPECASPRODUTO = GPC.IDPECASPRODUTO
             WHERE GPP.CODIGO_REGISTRO = 1
               AND GPP.STPECAPRODUTO IN (0, 16, 18)
               AND GPP.IDPESSOAFJESTOQUE = 2
               AND GPP.PADRAO_QUALIDADE_SIN = 1
               AND GPP.CODIGO_DEPOSITO IN (90, 95)
               AND GPC.FINALIDADE IN (1, 8)
               AND GPP.TIDOCUMENTOENTRADA <> 8
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "mal_producao",
            mal,
            """
            SELECT FMA.CODPROREDUZIDO, FMA.GRUPO,
                   FFI.AGULHAS, FFI.PONTOS_GRAMA_RAPORT,
                   FMA.RPM
              FROM SGTPRD.FICHA_MALHA FMA
              JOIN SGTPRD.FIOS_FICHA_MALHARIA_ FFI
                ON FFI.GRUPO_MAQUINA = FMA.GRUPO
               AND FFI.CODIGO_PRODUTO = FMA.CODPROREDUZIDO
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "detalhado_vup",
            detalhado,
            """
            SELECT UOM.NUMEROORDEMREAL, UPR.NUMEROUP,
                   UPR.NUMERO_MAQUINA, UPP.DATA_FIM
              FROM SGTPRD.UNIDADE_PROGR_PROD UPP
              JOIN SGTPRD.UNIDADE_PROGRAMACAO UPR
                ON UPR.NUMEROUP = UPP.NUMEROUP
              JOIN SGTPRD.UP_ORDEM_MVTO UOM
                ON UOM.NUMEROUP = UPR.NUMEROUP
             WHERE UPR.SETOR = 5
               AND UPR.EXCLUIDA = 0
               AND UPR.TIPOUP = 0
               AND UPP.DATA_FIM >= TRUNC(SYSDATE) - 7
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "detalhado_obf_base",
            detalhado,
            """
            SELECT OBFX.NUMERO_OB, OBFX.CODIGO_FASE,
                   CASE
                       WHEN REGEXP_LIKE(TRIM(OBFX.CBCORTELONGITUDINAL), '^[0-9]+$')
                           THEN TO_NUMBER(TRIM(OBFX.CBCORTELONGITUDINAL))
                       ELSE 0
                   END AS CORTE_LONGITUDINAL,
                   DECODE(OBFX.KILOS_PRODUZIDOS, 0, OBY.KILOS, OBFX.KILOS_PRODUZIDOS) AS KILOS
              FROM SGTPRD.OB_FASES OBFX
              JOIN SGTPRD.OB_PRODUTO OBY ON OBY.NUMERO_OB = OBFX.NUMERO_OB
              JOIN SGTPRD.MAQUINA MAQ
                ON MAQ.NUMERO_MAQUINA = OBFX.NUMERO_MAQUINA
               AND MAQ.SETOR = 5
             WHERE OBFX.NUMERO_OB = (
                       SELECT MIN(NUMERO_OB) FROM SGTPRD.OB_FASES
                   )
               AND OBFX.DESTINO_RECEITA IN (0, 1, 2, 4)
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "detalhado_percentual_grupo",
            detalhado,
            # Mesma expressão de PERC_GRUPO do CTE `OBF` da consulta de produção
            # (ramos kg por tipo de máquina/unidade, metros e o ELSE 100/N),
            # sobre as fases do grupo de programação mais recente.
            """
            WITH B AS (
                SELECT OBFX.CODIGO_GRUPO,
                       MAQ.TIPO_MAQUINA,
                       ITE.IDUNIDADEMEDIDA,
                       DECODE(OBFX.KILOS_PRODUZIDOS, 0, OBY.KILOS, OBFX.KILOS_PRODUZIDOS) AS KILOS_PRODUZIDOS,
                       DECODE(OBFX.METROS_PRODUZIDOS, 0, OBY.METROS, OBFX.METROS_PRODUZIDOS) AS METROS_PRODUZIDOS,
                       OBY.KILOS AS OBY_KILOS,
                       OBY.METROS AS OBY_METROS
                  FROM SGTPRD.OB_FASES OBFX
                  JOIN SGTPRD.OB_PRODUTO OBY ON OBY.NUMERO_OB = OBFX.NUMERO_OB
                  JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = OBY.CODPRO_REDUZIDO
                  JOIN SGTPRD.MAQUINA MAQ
                    ON MAQ.NUMERO_MAQUINA = OBFX.NUMERO_MAQUINA
                   AND MAQ.SETOR = 5
                 WHERE OBFX.CODIGO_GRUPO = (
                           SELECT MAX(X.CODIGO_GRUPO) FROM SGTPRD.OB_FASES X
                       )
                   AND OBFX.DESTINO_RECEITA IN (0, 1, 2, 4)
            )
            SELECT CASE
                       WHEN B.CODIGO_GRUPO = 0 THEN 100
                       WHEN B.CODIGO_GRUPO <> 0
                            AND B.TIPO_MAQUINA IN (17, 18, 19, 20, 21, 22, 60)
                            AND B.IDUNIDADEMEDIDA = 1
                            AND NVL(SUM(DECODE(B.KILOS_PRODUZIDOS, 0, B.OBY_KILOS, B.KILOS_PRODUZIDOS))
                                    OVER (PARTITION BY B.CODIGO_GRUPO), 0) <> 0 THEN
                           100 * B.KILOS_PRODUZIDOS / NULLIF(
                               SUM(DECODE(B.KILOS_PRODUZIDOS, 0, B.OBY_KILOS, B.KILOS_PRODUZIDOS))
                                   OVER (PARTITION BY B.CODIGO_GRUPO), 0)
                       WHEN NVL(SUM(DECODE(B.METROS_PRODUZIDOS, 0, B.OBY_METROS, B.METROS_PRODUZIDOS))
                                OVER (PARTITION BY B.CODIGO_GRUPO), 0) <> 0 THEN
                           100 * B.METROS_PRODUZIDOS / NULLIF(
                               SUM(DECODE(B.METROS_PRODUZIDOS, 0, B.OBY_METROS, B.METROS_PRODUZIDOS))
                                   OVER (PARTITION BY B.CODIGO_GRUPO), 0)
                       ELSE 100 / NULLIF(COUNT(*) OVER (PARTITION BY B.CODIGO_GRUPO), 0)
                   END AS PERC_GRUPO
              FROM B
             FETCH FIRST 1 ROWS ONLY
            """,
        ),
        _case(
            "acb_mix_receitas_corante",
            "02_acabamento_preparacao/acb_mix_programacoes.sql",
            """
            WITH RECEITAS_CORANTE AS (
                SELECT CR.CODCOR AS RECEITA,
                       TRIM(CR.DESCOR) AS DESCR_RECEITA,
                       CR.ESPECIFICACAO_PRODUT AS EP,
                       CR.PROCESSO_ESPECIFICO AS PE,
                       CR.PROCESSO_ATIVO_PRODU AS RECEITA_ATIVA,
                       TRIM(PI.DESCRICAO_PI) AS PROCESSO,
                       1 AS CORANTE
                  FROM SGTPRD.CADASTRO_RECEITAS CR
                  JOIN SGTPRD.LIGA_CADREC_ITEMREC LCR
                    ON LCR.CODIGO_REDUZIDO_RECE = CR.CODIGO_REDUZIDO_RECE
                  JOIN SGTPRD.ITENS_CADASTRO_RECEI ICR
                    ON ICR.ID_LIGA_CADREC_ITEMR = LCR.ID_LIGA_CADREC_ITEMR
                  JOIN SGTPRD.ITENS_ESTOQUE ITE
                    ON ITE.CODIGO_REDUZIDO = ICR.CODINSREDUZIDO_PADRA
                  LEFT JOIN SGTPRD.PROCESSO_INDUSTRIAL PI
                    ON PI.PROCESSO_INDUSTRIAL = CR.PROCESSOINDUSTRIAL
                 WHERE CR.PROCESSO_ATIVO_PRODU = 1
                   AND UPPER(TRIM(ITE.GRUPO_ESTOQUE)) LIKE 'CORANTE%'
            ), RECEITAS AS (
                SELECT RECEITA, DESCR_RECEITA, EP, PE, RECEITA_ATIVA, CORANTE,
                       LISTAGG(PROCESSO, ',' ON OVERFLOW TRUNCATE)
                           WITHIN GROUP (ORDER BY PROCESSO) AS PROCESSO
                  FROM (
                        SELECT DISTINCT RECEITA, DESCR_RECEITA, EP, PE,
                                        RECEITA_ATIVA, CORANTE, PROCESSO
                          FROM RECEITAS_CORANTE
                       )
                 GROUP BY RECEITA, DESCR_RECEITA, EP, PE, RECEITA_ATIVA, CORANTE
            )
            SELECT RECEITA, DESCR_RECEITA, EP, PE, RECEITA_ATIVA, CORANTE, PROCESSO
              FROM RECEITAS
             FETCH FIRST 1 ROWS ONLY
            """,
            timeout_ms=30000,
        ),
        _case(
            "acb_mix_itens_pedido",
            "02_acabamento_preparacao/acb_mix_programacoes.sql",
            """
            WITH ITENS_PEDIDO AS (
                SELECT IPC.PEDIDO AS NRPEDIDO,
                       IPC.ITEMPEDIDO,
                       IPC.ITEMPEDIDOCLIENTE AS ITEMCLIENTE,
                       IPC.CD_DESENHO_CLIENTE AS CAD_CLIENTE,
                       TRIM(ITE.CODIGO_ALTERNATIVO) AS CODALTERNATIVO,
                       IPC.REDUZIDOITEM AS CODREDUZIDO,
                       TRIM(ITE.CODIGO) AS CODINDUSTRIAL,
                       TRIM(ITE.DESCRICAO) AS DESCPRODUTO,
                       TRIM(COR.CODIGO_COR) AS CODCOR,
                       TRIM(COR.DESCRICAO) AS DESCCOR,
                       COR.TIPOCOR,
                       IPC.QUANTIDADE_DIGITACAO AS QTDEDIGITADA,
                       IPC.IDUMDIGITACAO AS IDUNIMEDDIG,
                       TRIM(UMD.DSSIGLA) AS SIGLAUNIMEDDIG,
                       IPC.QUANTIDADE AS QTDEPADRAO,
                       TRIM(UMP.DSSIGLA) AS SIGLAUNIMEDPADRAO,
                       IPC.SITUACAOITEM AS STATUS,
                       ITE.TIPO_ITEM,
                       CAST(DECODE(NVL(IPC.DTEMISSAO, 0), 0, DATE '1899-12-30',
                            TO_DATE(TO_CHAR(IPC.DTEMISSAO), 'YYYYMMDD')) AS DATE) AS DATAEMISSAO
                  FROM SGTPRD.ITENSPEDIDOCOMERCIAL IPC
                  JOIN SGTPRD.PEDIDOCOMERCIAL PED ON PED.PEDIDO = IPC.PEDIDO
                  JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = IPC.REDUZIDOITEM
                  LEFT JOIN SGTPRD.ENGEITEMESTOCOR EIC ON EIC.CDREDUZIDO = IPC.REDUZIDOITEM
                  LEFT JOIN SGTPRD.COR COR ON COR.CODIGO_COR = EIC.CDCOR
                  LEFT JOIN SGTPRD.UNIDADE_MEDIDA UMD ON UMD.IDUNIDADEMEDIDA = IPC.IDUMDIGITACAO
                  LEFT JOIN SGTPRD.UNIDADE_MEDIDA UMP ON UMP.IDUNIDADEMEDIDA = IPC.IDUNIDADEMEDIDA
                 WHERE IPC.SITUACAOITEM <> 6
                   AND IPC.IDUMDIGITACAO <> 1
                   AND ITE.TIPO_ITEM = 10
            )
            SELECT NRPEDIDO, ITEMPEDIDO, ITEMCLIENTE, CAD_CLIENTE, CODALTERNATIVO,
                   CODREDUZIDO, CODINDUSTRIAL, DESCPRODUTO, CODCOR, DESCCOR,
                   TIPOCOR, QTDEDIGITADA, IDUNIMEDDIG, SIGLAUNIMEDDIG,
                   QTDEPADRAO, SIGLAUNIMEDPADRAO, STATUS, TIPO_ITEM, DATAEMISSAO
              FROM ITENS_PEDIDO
             FETCH FIRST 1 ROWS ONLY
            """,
            timeout_ms=30000,
        ),
    ]


def _execute_case(
    sql: str, creds: Any, holder: dict[str, Any], timeout_s: float
) -> dict[str, Any]:
    """Parse + execução limitada. Grava a conexão em `holder` para o watchdog
    de `_run_with_timeout` poder cancelá-la."""
    connection = connect_within(
        lambda: oracledb.connect(
            user=creds.user, password=creds.password, dsn=creds.dsn
        ),
        timeout_s,
    )
    # Fechada por `run_with_cancel` (owns_connection), nunca aqui.
    holder["connection"] = connection
    _raise_if_expired(holder)
    cursor = connection.cursor()
    started = time.perf_counter()
    cursor.parse(sql)
    holder["parse_ms"] = round((time.perf_counter() - started) * 1000, 1)
    started = time.perf_counter()
    cursor.execute(sql)
    rows = cursor.fetchmany(1)
    return {
        "parse": "pass",
        "parse_ms": holder["parse_ms"],
        "status": "validated",
        "execute_ms": round((time.perf_counter() - started) * 1000, 1),
        "rows": len(rows),
        "columns": len(cursor.description or []),
    }


def _attempt(
    sql: str, creds: Any, timeout_ms: int
) -> tuple[dict[str, Any], BaseException | None]:
    """Uma tentativa. O Oracle Client 12.2 desta máquina não suporta
    `connection.call_timeout` (exige 18.1+): o prazo é imposto por watchdog."""
    holder: dict[str, Any] = {}
    try:
        timeout_s = max(1, timeout_ms // 1000)
        outcome: dict[str, Any] = _run_with_timeout(
            lambda: _execute_case(sql, creds, holder, timeout_s),
            timeout_s,
            holder=holder,
        )
        return outcome, None
    except TimeoutError as exc:
        return {"status": "timeout", "error": _summary(exc)}, None
    except (oracledb.Error, OSError, RuntimeError, TypeError, ValueError) as exc:
        parsed = "parse_ms" in holder
        status = "parse_ok_smoke_error" if parsed else "oracle_error"
        return {"status": status, "error": _summary(exc)}, exc


def _run_one(case: dict[str, Any], creds: Any, guard: Path) -> dict[str, Any]:
    sql = str(case["sql"]).strip()
    started_clock = time.perf_counter()
    sql_hash = _sha256(sql.encode("utf-8"))
    guard_code, guard_output = _guard(sql, guard)
    result: dict[str, Any] = {
        "name": case["name"],
        "file": case["file"],
        "input_kind": "inline_case",
        "normalized_sha256": sql_hash,
        "guard_input_sha256": sql_hash,
        "parse_input_sha256": sql_hash,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "validator_version": VALIDATOR_VERSION,
        "guard_exit": guard_code,
        "guard_output": guard_output,
    }
    if guard_code != 0:
        result["status"] = "blocked_guard"
    else:
        for attempt in range(1, 4):
            outcome, exc = _attempt(sql, creds, int(case["timeout_ms"]))
            result.update(outcome)
            result["attempts"] = attempt
            if exc is None or attempt == 3 or not _retryable(exc):
                break
            result.pop("error", None)
            time.sleep(0.2 * attempt)
    result["finished_at_utc"] = datetime.now(UTC).isoformat()
    result["duration_ms"] = round((time.perf_counter() - started_clock) * 1000, 1)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    creds = resolve_oracle_credentials(_log, "validar-partes-acervo-sql")
    if creds is None:
        print(json.dumps({"status": "credentials_unavailable"}, ensure_ascii=False))
        return 2
    init_thick_mode(creds, _log, "validar-partes-acervo-sql")
    guard = resolve_guard()
    results = [_run_one(case, creds, guard) for case in _cases()]
    summary: dict[str, int] = {}
    for item in results:
        status = str(item.get("status", "unknown"))
        summary[status] = summary.get(status, 0) + 1
    payload = {
        "schema": "oracle-sql-parts-validation/v2",
        "validator_version": VALIDATOR_VERSION,
        "status": "complete",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "command": portable_command(sys.argv),
        "summary": summary,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "complete", "summary": summary}, ensure_ascii=False))
    return 0 if all(item.get("status") == "validated" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

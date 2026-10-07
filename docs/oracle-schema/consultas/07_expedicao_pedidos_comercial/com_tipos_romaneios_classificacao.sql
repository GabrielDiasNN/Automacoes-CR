/* =============================================================================
OBJETIVO: Classificação de tipos de romaneios do sistema SGT
DOMÍNIO: 07_expedicao_pedidos_comercial
ARQUIVO ORIGINAL: 07_expedicao_pedidos_comercial/com_tipos_de_romaneios.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.GERAREQUESTOTIPO, SGTPRD.TIPO_MOVIMENTO
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
REVISÃO (20/09/2026 - Onda 1): Junção legada Oracle (+) migrada para LEFT JOIN ANSI.
  guard_sql.py: exit 0. Equivalência estrutural garantida — mesma semântica de outer join.
============================================================================= */

SELECT G.ID,
       TRIM(G.DSTIPOREQUESTO) DESCR_TIPO_ROMANEIO,
       G.NRTIPOMOVIMENTO,
       TRIM(T.DESCRICAO) DESCR_TIPO_MOVIMENTO,
       T.OPERACAO,
       T.MOVIMENTONOTAFISCAL,
       T.TIPOMVTOENTRADASAIDA,
       G.TICONTTERC,
       G.TIINTERNO,
       G.TIEXIGECONDPAGAMENTO,
       G.TIDEVOLUCAO,
       G.TIEXIGCONFPECA,
       G.TIRETORNOINDUSTRIALI,
       G.TIEXIGPRECITEM,
       G.TIBAIXTERCROMARETO,
       G.TICTRLQTDECONFPROD,
       G.TICONTAGRUFATUTIPROM,
       G.TICONSIDPESOBRUTOLIQ,
       G.TIFATUQTDEBAIXAORIG
  FROM SGTPRD.GERAREQUESTOTIPO G
  LEFT JOIN SGTPRD.TIPO_MOVIMENTO T ON T.NUM_TIPO_MOVIMENTO = G.NRTIPOMOVIMENTO
 WHERE G.CDTIPOROMA IS NOT NULL
 ORDER BY 1;

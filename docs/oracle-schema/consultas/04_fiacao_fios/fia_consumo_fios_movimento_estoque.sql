/* =============================================================================
OBJETIVO: Movimentação de estoque de fios na fiação
DOMÍNIO: 04_fiacao_fios
ARQUIVO ORIGINAL: 04_fiacao_fios/fia_fios_consumos_ficha_tecnica_reserva_de_fio_para_baixa.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.GERAMOVIESTOCOMP, SGTPRD.GERAMOVIMENTOESTOQUE
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT gme.*
  FROM SGTPRD.GERAMOVIESTOCOMP     DOC, 
       SGTPRD.GERAMOVIMENTOESTOQUE GME
 WHERE GME.ID = DOC.IDGERAMOVIESTO
   AND DOC.NRDOCUMENTO = 4791989
   AND GME.CDDEPOSITO = 165;

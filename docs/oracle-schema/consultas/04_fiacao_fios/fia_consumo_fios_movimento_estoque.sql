/* =============================================================================
OBJETIVO: Movimentação de estoque de fios na fiação
DOMÍNIO: 04_fiacao_fios
ARQUIVO ORIGINAL: 04_fiacao_fios/fia_fios_consumos_ficha_tecnica_reserva_de_fio_para_baixa.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.GERAMOVIESTOCOMP, SGTPRD.GERAMOVIMENTOESTOQUE
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT GME.ID,
       GME.CDFILIAL,
       GME.CDREDUZIDO,
       GME.CDDEPOSITO,
       GME.IDGERAATRIESTO,
       GME.STMOVIMENTO,
       GME.TIOPERACAO,
       GME.NRTIPOMOVIMENTO,
       GME.STGERAESTOBLOQ,
       GME.STMOVCONFIRMADO,
       GME.DTDOCUMENTO,
       GME.QTMOVIMENTO,
       GME.NRVOLUMES
  FROM SGTPRD.GERAMOVIESTOCOMP DOC
  INNER JOIN SGTPRD.GERAMOVIMENTOESTOQUE GME
    ON GME.ID = DOC.IDGERAMOVIESTO
 WHERE DOC.NRDOCUMENTO = 4791989
   AND GME.CDDEPOSITO = 165;

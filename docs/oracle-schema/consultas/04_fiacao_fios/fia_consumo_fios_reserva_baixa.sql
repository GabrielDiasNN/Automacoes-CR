/* =============================================================================
OBJETIVO: Reserva de fios para baixa por ficha técnica
DOMÍNIO: 04_fiacao_fios
ARQUIVO ORIGINAL: 04_fiacao_fios/fia_fios_consumos_ficha_tecnica_reserva_de_fio_para_baixa.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.FIOS_FICHA_MALHARIA_, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
REVISÃO (20/09/2026 - Onda 3): a projeção usa aliases explícitos (`F.*` e
  `ITE.*`) para preservar o contrato histórico sem ambiguidade de colunas.
============================================================================= */

SELECT F.UN_TEMP,
       F.CODIGO_PRODUTO,
       F.GRUPO_MAQUINA,
       F.CODIGO_FIO,
       F.CONES,
       F.AGULHAS,
       F.PONTOS_GRAMA_RAPORT,
       F.TENSAO_ENTRADA,
       F.TAMANHO_PONTO_RETILI,
       F.NUMERO_CABOS,
       F.PERCENTUAL_PERDA,
       F.PERCPARTICIPACAO,
       F.INDIESTITITULO,
       F.VELOCIDADEFIO,
       F.POLIA,
       ITE.CODIGO_REDUZIDO,
       ITE.CODIGO,
       ITE.DESCRICAO,
       ITE.LINHA_PRODUTO,
       ITE.IDMASCARATIPOINSUMO,
       ITE.IDUNIDADEMEDIDA,
       ITE.STATUS_ATIVACAO,
       ITE.SITUACAO
  FROM SGTPRD.FIOS_FICHA_MALHARIA_ F
  INNER JOIN SGTPRD.ITENS_ESTOQUE ITE
    ON ITE.CODIGO_REDUZIDO = F.CODIGO_PRODUTO
 WHERE ITE.LINHA_PRODUTO IN (30)
   AND F.CODIGO_FIO IN (9111,8537,5461,11019,5653,5462,5460,5478,5463)
 ORDER BY F.CODIGO_PRODUTO;

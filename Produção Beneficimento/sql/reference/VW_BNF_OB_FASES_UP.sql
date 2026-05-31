--CREATE OR REPLACE VIEW VW_BNF_OB_FASES_UP AS
SELECT NUMERO_OB,
       SEQ,
       NUMERO_MAQUINA,
       NOME_MAQUINA,
       DATA_HORA_INICIO,
       DATA_HORA_FINAL,
       DATA_INI,
       TURNO_INI,
       DATA_FIM,
       TURNO_FIM,
       MIN_PAR_PROC,
       MIN_PREV,
       CASE
         WHEN ((TEMPOFINAL - TEMPOINICIAL) * 1440) <= 1 THEN
          1
         ELSE
          (TEMPOFINAL - TEMPOINICIAL) * 1440 - MIN_PAR_PROC + 1
       END MIN_REAL,
       TIPO_MAQUINA,
       PROGRAM_POR_LEADTIME PROG_LEAD_TIME,
       NUMEROUP,
       CDFILIAL,
       STATUS_UP
  FROM (SELECT UOM.NUMEROORDEMREAL NUMERO_OB,
               UOM.SEQUENCIAORDEMREAL SEQ,
               UPR.NUMERO_MAQUINA,
               MAQ.NOME_MAQUINA,
               UPR.TEMPOFINAL,
               UPR.TEMPOINICIAL,
               UPP.DATA_HORA_INICIO,
               UPP.DATA_HORA_FINAL,
               UPP.DATA_INI,
               UPP.TURNO_INI,
               UPP.DATA_FIM,
               UPP.TURNO_FIM,
               NVL((SELECT TRUNC(SUM(UPA.TEMPOFINAL - UPA.TEMPOINICIAL) * 1440)
                     FROM UNIDADE_PROGRAMACAO UPA
                    WHERE UPA.EXCLUIDA = 0
                      AND UPA.SETOR = UPR.SETOR
                      AND UPA.STATUS = 0
                      AND UPA.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA
                      AND UPA.TEMPOFINAL >= UPR.TEMPOINICIAL
                      AND UPA.TEMPOINICIAL >= UPR.TEMPOINICIAL
                      AND UPA.TEMPOFINAL <= UPR.TEMPOFINAL
                      AND UPA.TIPOUP = 5),
                   0) MIN_PAR_PROC,
               CASE
                 WHEN UPR.DURACAO_PREVISTA <> 0 THEN
                  UPR.DURACAO_PREVISTA * 1440
                 ELSE
                  DECODE(UPR.TEMPOFINALPROGRAMADO,
                         0,
                         (UPR.TEMPOFINALPLANEJADO - UPR.TEMPOINIPLANEJADO) * 1440,
                         (UPR.TEMPOFINALPROGRAMADO - UPR.TEMPOINIPROGRAMADO) * 1440)
               END MIN_PREV,
               UPP.TIPO_MAQUINA,
               UPP.CDFILIAL,
               MAQ.PROGRAM_POR_LEADTIME,
               UPR.NUMEROUP,
               UPR.STATUS STATUS_UP
          FROM UNIDADE_PROGR_PROD  UPP,
               UNIDADE_PROGRAMACAO UPR,
               UP_ORDEM_MVTO       UOM,
               MAQUINA             MAQ
         WHERE UPR.NUMEROUP = UPP.NUMEROUP
           AND UPR.SETOR = 5
           AND UPR.EXCLUIDA = 0
           AND UPR.TIPOUP = 0
           AND UOM.NUMEROUP = UPR.NUMEROUP
           AND MAQ.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA)


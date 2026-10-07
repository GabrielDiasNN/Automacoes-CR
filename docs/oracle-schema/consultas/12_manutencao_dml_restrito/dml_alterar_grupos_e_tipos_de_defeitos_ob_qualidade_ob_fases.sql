/* =============================================================================
OBJETIVO: Alterar grupos e tipos de defeitos (OB_QUALIDADE, OB_FASES)
DOMÍNIO: 12_manutencao_dml_restrito
ARQUIVO ORIGINAL: Comandos SQL - CR\Alterar grupos e tipos de defeitos (OB_QUALIDADE, OB_FASES).sql
TIPO: DML - Atualização Controlada
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.OB_FASES, SGTPRD.OB_QUALIDADE
CUIDADOS OPERACIONAIS: ESTE ARQUIVO CONTÉM DML (UPDATE) e NÃO é somente leitura. Execução apenas
  manual, por operador autorizado: rode antes o SELECT de conferência, valide as linhas afetadas e
  só então execute o UPDATE, com COMMIT consciente (ou ROLLBACK se o rowcount divergir). Ver AVISO_SEGURANCA.md.
============================================================================= */

/* =============================================================================
!!! REGISTRO HISTÓRICO -- NÃO REEXECUTAR EM BLOCO !!!
Este arquivo reúne 36 UPDATEs de correções PONTUAIS já aplicadas, cada uma para uma OB
fixa (18 OBs distintas). Reexecutar o arquivo inteiro sobrescreve GRUPO_DEFEITO e
TIPO_DEFEITO com valores antigos. Use como referência de padrão: copie apenas o UPDATE da OB
desejada, confira com o SELECT abaixo e faça COMMIT consciente.
============================================================================= */

-- CONFERÊNCIA (somente leitura): estado atual de TODAS as OBs alteradas neste arquivo.
SELECT OBQ.NUMERO_OB, OBQ.GRUPO_DEFEITO, OBQ.TIPO_DEFEITO
FROM   SGTPRD.OB_QUALIDADE OBQ
WHERE  OBQ.NUMERO_OB IN (
  90904, 92440, 92448, 96606, 96607, 97299, 97301, 97573, 97756, 97757, 97758, 98098, 98102, 98104,
  98685, 98686, 99791, 99798
)
ORDER BY OBQ.NUMERO_OB;

SELECT OBF.NUMERO_OB, OBF.GRUPO_DEFEITO, OBF.TIPO_DEFEITO
FROM   SGTPRD.OB_FASES OBF
WHERE  OBF.NUMERO_OB IN (
  90904, 92440, 92448, 96606, 96607, 97299, 97301, 97573, 97756, 97757, 97758, 98098, 98102, 98104,
  98685, 98686, 99791, 99798
)
ORDER BY OBF.NUMERO_OB;



UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '8 ', OBF.TIPO_DEFEITO = 9
WHERE OBF.NUMERO_OB = 99791;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '8 ', OBQ.TIPO_DEFEITO = 9
WHERE OBQ.NUMERO_OB = 99791;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 99798;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 99798;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 92448;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 92448;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 92440;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 92440;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 97757;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 97757;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 90904;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 90904;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 97573;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 97573;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 98685;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 98685;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 98686;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 98686;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 97301;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 97301;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 97758;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 97758;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 98104;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 98104;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 96606;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 96606;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 98102;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 98102;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 97756;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 97756;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 98098;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 98098;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 96607;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 96607;

----------------------------------------------------------------

UPDATE OB_FASES OBF
SET OBF.GRUPO_DEFEITO = '7 ', OBF.TIPO_DEFEITO = 2
WHERE OBF.NUMERO_OB = 97299;


UPDATE OB_QUALIDADE OBQ
SET OBQ.GRUPO_DEFEITO = '7 ', OBQ.TIPO_DEFEITO = 2
WHERE OBQ.NUMERO_OB = 97299;



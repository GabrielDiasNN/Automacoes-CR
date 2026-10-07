/* =============================================================================
OBJETIVO: Update Grupo de Programações - Observações da Fase
DOMÍNIO: 12_manutencao_dml_restrito
ARQUIVO ORIGINAL: Comandos SQL - CR\Update Grupo de Programações - Observações da Fase.sql
TIPO: DML - Atualização Controlada
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: Não identificadas explicitamente
CUIDADOS OPERACIONAIS: ESTE ARQUIVO CONTÉM DML (UPDATE) e NÃO é somente leitura. Execução apenas
  manual, por operador autorizado: rode antes o SELECT de conferência, valide as linhas afetadas e
  só então execute o UPDATE, com COMMIT consciente (ou ROLLBACK se o rowcount divergir). Ver AVISO_SEGURANCA.md.
============================================================================= */

-- Conferência dos UPDATEs abaixo (mesmos filtros: fluxo + sequência)
SELECT GF.CODIGO_FLUXO, GFF.SEQUENCIA, GFF.OBSERVACAO, COUNT(*) AS LINHAS
FROM   SGTPRD.GRUPO_FLUXO_FASES GFF
JOIN   SGTPRD.GRUPO_FLUXO       GF ON GF.IDGRUPOFLUXO = GFF.IDGRUPOFLUXO
WHERE  (GF.CODIGO_FLUXO = 303 AND GFF.SEQUENCIA = 50)
   OR  (GF.CODIGO_FLUXO IN (306, 308) AND GFF.SEQUENCIA = 60)
GROUP BY GF.CODIGO_FLUXO, GFF.SEQUENCIA, GFF.OBSERVACAO
ORDER BY GF.CODIGO_FLUXO;

update grupo_fluxo_fases gff
set gff.observacao = 'Enfraldar P/Felpar            '
where  gff.idgrupofluxo in (select gf.idgrupofluxo from grupo_fluxo gf where gf.codigo_fluxo=303)
and gff.sequencia = 50;

update grupo_fluxo_fases gff
set gff.observacao = 'Termofixar P/Estampar         '
where  gff.idgrupofluxo in (select gf.idgrupofluxo from grupo_fluxo gf where gf.codigo_fluxo=306)
and gff.sequencia = 60;

update grupo_fluxo_fases gff
set gff.observacao = 'Termofixar P/Estampar         '
where  gff.idgrupofluxo in (select gf.idgrupofluxo from grupo_fluxo gf where gf.codigo_fluxo=308)
and gff.sequencia = 60;
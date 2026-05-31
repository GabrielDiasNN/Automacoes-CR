...CREATE OR REPLACE VIEW VW_PI_CBPAP02_PRODBENEF AS
SELECT vup.CDFILIAL FILIAL,
       vup.DATA_FIM DATA_PROD,
       vup.TURNO_FIM TURNO_PROD,
       OBe.CODIGO_REDUZIDO REDUZ,
       eng.DESCR_ITEM,
       VUP.NUMERO_OB,
       VUP.SEQ,
       obf.CODIGO_FASE FASE,
       (select TRIM(FFL.DESCRICAO_FASE) from fases_fluxo ffl where ffl.codigo_fase=obf.CODIGO_FASE) DESCR_FASE,
       eng.TIPO,
       eng.ARTIGO,
       eng.DESCR_ARTIGO,
       eng.LARG LARGURA,
       ENG.RENDIMENTO,
       eng.COR,
       eng.DESCR_COR,
       eng.ACABAMENTO,
       ENG.DESENHO,
       ENG.DESCR_DESENHO,
       ENG.VARIANTE,
       ENG.DIMENSAO,
       ENG.DESCR_DIMENSAO,
       ENG.DESCR_ACABAMENTO,
       ENG.DESCR_ATRIB1,
       ENG.DESCR_ATRIB2,
       ENG.DESCR_ATRIB3,
       eng.CODIND,
       ENG.CODIGO_ALTERNATIVO,
       eng.DESCR_CLASSIFICACAO_COR,
       ENG.DESCR_LINHA_PRODUTO,
       (SELECT TRIM(BPA.DESCR_UM) FROM VW_F7_PRD_BPA_UND_MED BPA WHERE BPA.TPUNIDADEMEDIDA=eng.TPUNIDADEMEDIDA) DESCR_UM,
       Case
          When obf.TIPO_DESTINO = 1 AND obf.CARGA_MAXIMA = 0 THEN (DECODE(eng.tpunidademedida,1,obf.KILOS,obf.METROS))  * obf.PERC_GRUPO / 100
          Else obf.CARGA_MAXIMA * obf.PERC_GRUPO / 100
       END CARGA_PREV_GRUPO,
       DECODE(eng.tpunidademedida,1,obf.KILOS,obf.METROS) * OBF.perc_parcial / 100 QUANT_PROD,
       Case
          When obf.TIPO_DESTINO = 1 AND obf.CARGA_MAXIMA = 0 THEN 100
          When obf.TIPO_DESTINO <> 1 AND obf.CARGA_MAXIMA = 0 THEN 0
          Else  (DECODE(obf.CARGA_MAXIMA,0,0,
                   DECODE(obf.PERC_GRUPO,0,0,
                      ((DECODE(eng.tpunidademedida,1,obf.KILOS,obf.METROS))/(obf.CARGA_MAXIMA*obf.PERC_GRUPO/100))))) *100
       end EFIC_CARGA,
     Case
         When obf.velocidade <> 0 then obf.velocidade
         When (SELECT (MAX(GFM.VELOCIDADE)) FROM GRUPO_FLUXO GFL, GRUPO_FLUXO_FASES GFF, GRUPO_FLUXO_MAQUINAS GFM WHERE OBE.NUMERO_OB = obf.NUMERO_OB
       AND GFL.NUMERO_GRUPO_PROGRAM = OBE.NUMERO_GRUPO_PROGRAM
       AND GFL.CODIGO_FLUXO = OBE.CODIGO_FLUXO
       AND GFF.IDGRUPOFLUXO = GFL.IDGRUPOFLUXO
       AND GFF.SEQUENCIA = obf.SEQUENCIA
       AND GFM.IDGRUPOFLUXOFASE = GFF.IDGRUPOFLUXOFASE
       AND GFM.NUMERO_MAQUINA = obf.NUMERO_MAQUINA
       AND GFM.ATIVA = 1) <> 0  then (SELECT (MAX(GFM.VELOCIDADE)) FROM GRUPO_FLUXO GFL, GRUPO_FLUXO_FASES GFF, GRUPO_FLUXO_MAQUINAS GFM WHERE OBE.NUMERO_OB = obf.NUMERO_OB
                                     AND GFL.NUMERO_GRUPO_PROGRAM = OBE.NUMERO_GRUPO_PROGRAM
                                     AND GFL.CODIGO_FLUXO = OBE.CODIGO_FLUXO
                                     AND GFF.IDGRUPOFLUXO = GFL.IDGRUPOFLUXO
                                     AND GFF.SEQUENCIA = obf.SEQUENCIA
                                     AND GFM.IDGRUPOFLUXOFASE = GFF.IDGRUPOFLUXOFASE
                                     AND GFM.NUMERO_MAQUINA = obf.NUMERO_MAQUINA
                                     AND GFM.ATIVA = 1)
         When (SELECT (MAX(GFM.VELOCIDADE)) FROM GRUPO_FLUXO GFL, GRUPO_FLUXO_FASES GFF, GRUPO_FLUXO_MAQUINAS GFM WHERE OBE.NUMERO_OB = obf.NUMERO_OB
       AND GFL.NUMERO_GRUPO_PROGRAM = OBE.NUMERO_GRUPO_PROGRAM
       AND GFL.CODIGO_FLUXO = OBE.CODIGO_FLUXO
       AND GFF.IDGRUPOFLUXO = GFL.IDGRUPOFLUXO
       AND GFM.IDGRUPOFLUXOFASE = GFF.IDGRUPOFLUXOFASE
       and GFF.CODIGO_FASE = obf.CODIGO_FASE
       AND GFM.NUMERO_MAQUINA = obf.NUMERO_MAQUINA
       AND GFM.ATIVA = 1) <> 0 then (SELECT (MAX(GFM.VELOCIDADE)) FROM GRUPO_FLUXO GFL, GRUPO_FLUXO_FASES GFF, GRUPO_FLUXO_MAQUINAS GFM WHERE OBE.NUMERO_OB = obf.NUMERO_OB
                                       AND GFL.NUMERO_GRUPO_PROGRAM = OBE.NUMERO_GRUPO_PROGRAM
                                       AND GFL.CODIGO_FLUXO = OBE.CODIGO_FLUXO
                                       AND GFF.IDGRUPOFLUXO = GFL.IDGRUPOFLUXO
                                       AND GFM.IDGRUPOFLUXOFASE = GFF.IDGRUPOFLUXOFASE
                                       and GFF.CODIGO_FASE = obf.CODIGO_FASE
                                       AND GFM.NUMERO_MAQUINA = obf.NUMERO_MAQUINA
                                       AND GFM.ATIVA = 1)
         else obf.velocidade_maquina
     end VELOCIDADE,
       VUP.MIN_REAL * obf.PERC_GRUPO / 100 * OBF.perc_parcial / 100 MIN_REAL,
       VUP.MIN_PREV * obf.PERC_GRUPO / 100 * OBF.perc_parcial / 100 MIN_PREV,
       --PAULO                                                                     --Fabiano Barbosa 14/12/2017 - inicio tarefa 120594
       /*TRUNC(VUP.MIN_PREV) + TRUNC(OBF.Tempo_Troca_Banho / 60) + (trunc(OBF.HORAMAQUINA_CARGA_DE)*60 + (trunc
       (decode(trunc(OBF.HORAMAQUINA_CARGA_DE),0,
               trunc(OBF.HORAMAQUINA_CARGA_DE*100),
               trunc((OBF.HORAMAQUINA_CARGA_DE-trunc(OBF.HORAMAQUINA_CARGA_DE))*100)
               )
               )
               ))*/
       pkgbenf0001.FNC_RETORNA_TEMPO_TOTAL_GRAF(OBF.numero_ob, OBF.sequencia) TOTAL_MIN_PREV, --Fabiano Barbosa 14/12/2017 - fim tarefa 120594
       OBF.MIN_SETUP * obf.PERC_GRUPO / 100 * OBF.perc_parcial / 100 MIN_SETUP,
       (VUP.MIN_PREV-OBF.MIN_SETUP) * obf.PERC_GRUPO / 100 * OBF.perc_parcial / 100 MIN_PROCESSO,
       VUP.MIN_PAR_PROC * obf.PERC_GRUPO / 100 MIN_PAR_PROC,
       DECODE(VUP.MIN_PREV,0,100,
       VUP.MIN_PREV / VUP.MIN_REAL * 100) EFIC_TEMPO,
       obf.METROS * OBF.perc_parcial / 100 METROS,
       obf.KILOS * OBF.perc_parcial / 100 QUILOS,
       PKGBENF0001.FNC_RETORNA_PC_ORIGEM_OB (10,VUP.NUMERO_OB,0) * OBF.perc_parcial / 100 PECAS,
       (SELECT TRIM(GFA.DESCRICAO) FROM GRUPO_FASES GFA, FASES_FLUXO FFL WHERE FFL.CODIGO_FASE=obf.CODIGO_FASE AND GFA.CODIGO = FFL.CODIGO_GRUPO) DESCR_GRUPO_FASE,
       (select TRIM(STI.DESCRICAO) from  GRUPO_FASES GFA, FASES_FLUXO FFL, setor_industrial sti where FFL.CODIGO_FASE=obf.CODIGO_FASE AND GFA.CODIGO = FFL.CODIGO_GRUPO AND sti.setor_sequencia=gfa.setor_sequencia) DESCR_SETOR_INDUST,
       LTRIM(OBF.NUMERO_MAQUINA,'0') NUMERO_MAQUINA,
       OBF.DESCR_MAQ,
       (SELECT TRIM(VTM.DESCRICAO) FROM VW_ENU_TIPO_DE_MAQUINAS_SETOR VTM WHERE VTM.TIPO_MAQUINA=vup.TIPO_MAQUINA) DESCR_TIPO_MAQ,
       obf.CARGA_MAXIMA * OBF.perc_parcial / 100 CARGA_MAXIMA,
       obf.GRUPO,
       obf.codigo_grupo,
       eng.UM,
-- William Mello - Início - 19/01/2018 - Erro na consulta - TR 126841
       cast( Decode(vup.data_fim,'rrrrmmdd',null,
              0,
              PKGUTIL0001.FNC_SEMANA_CAL_ANO(to_char(vup.data_fim,'rrrrmmdd'))) as integer) ANO_SEM,
-- William Mello - Fim - 19/01/2018 - Erro na consulta - TR 126841
       TO_NUMBER(obf.PI_REC) PI_REC,
        obf.COR_REC, obf.EP_REC, obf.PE_REC,
       obf.DESCR_DESTINO,
       (select trim(vtd.DESCRICAO) from vw_enu_tipo_destino vtd where vtd.TIPO_DESTINO = obf.tipo_destino) DESCR_TIPO_DESTINO,
       (select trim(vtd.COD_TIPO_DESTINO) from vw_enu_tipo_destino vtd where vtd.TIPO_DESTINO = obf.tipo_destino) COD_TIPO_DESTINO,
       obf.DESTINO_RECEITA,
        obf.TIPO_DESTINO,
       DECODE(obf.TIPO_DESTINO,1,1,0) REPROCESSO,
--       DECODE((select MAX(gr.id) from gerarequestoob g, gerarequesto gr
--            where g.numeroordemmovimento = OBF.NUMEROORDEMMOVIMENTO and g.sequenciaordemmovime = OBF.SEQUENCIAORDEMMOVIME and gr.id = g.idgerarequesto
--         and gr.strequisicao <>3),NULL,0,1) AJUSTE,
       Case
          When
            nvl((select max(mr.sequencia_ajuste) from movto_receita mr where mr.numeroordem = obf.NUMEROORDEMMOVIMENTO
               and mr.sequenciafaseob = obf.SEQUENCIAORDEMMOVIME),0) <> 0 then 1
          Else 0
       end AJUSTE,

       LTRIM(obf.operador_iniCIO,'0') OPERADOR_INI,
       (select trim(opx.nome) from operador opx where opx.codigo=obf.operador_inicio) NOME_OPERADOR_INI,
       LTRIM(obf.OPERADOR_FINAL,'0') OPERADOR_FIM,
       (select trim(opx.nome) from operador opx where opx.codigo=obf.operador_final) NOME_OPERADOR_FIM,
       obf.PERC_GRUPO/100*OBF.PERC_PARCIAL/100 PARTIDAS,
       obf.PERC_GRUPO,
       vup.TIPO_MAQUINA,
       (SELECT TRIM(OBQ.USUARIO_OBNAOCONFORM) FROM OB_QUALIDADE OBQ WHERE OBQ.CODIGO_REDUZIDO = obf.RED_OB_QUALIDADE) NOME_NC_BLOQ,
       (SELECT TRIM(OBQ.USUARIO_INDICOU_DEST) FROM OB_QUALIDADE OBQ WHERE OBQ.CODIGO_REDUZIDO = obf.RED_OB_QUALIDADE) NOME_NC_INDIC,
       (SELECT TRIM(GIP.DESCRICAO_GRUPO) FROM GRUPO_DEFEITO_QUALID GIP WHERE GIP.CODIGO_GRUPO = obf.GRUPO_DEFEITO) DESCR_GRUPO_DEF,
       (SELECT TRIM(TIP.DESCRICAO_TIPO) FROM TIPO_DEFEITO_QUALIDA TIP WHERE TIP.CODIGO_GRUPO = obf.GRUPO_DEFEITO
       AND TIP.CODIGO_TIPO = obf.TIPO_DEFEITO) DESCR_TIPO_DEF,
       obf.grupo_defeito,
       obf.tipo_defeito,
       obf.grupo_defeito||LPAD(obf.tipo_defeito,3,'0') GTDEF,
       DECODE(obf.GRUPO_DEFEITO,'  ',null,
          (select GDQ.SETOR_DEFEITO from grupo_defeito_qualid gdq where gdq.codigo_grupo = obf.GRUPO_DEFEITO)) SETOR_DEF,
       DECODE(obf.GRUPO_DEFEITO,'  ',null,
          (SELECT trim(vex.DESCRICAO) from grupo_defeito_qualid gdq, vw_enu_setor_defeito vex where gdq.codigo_grupo = obf.GRUPO_DEFEITO
          and vex.SETOR_DEF=gdq.setor_defeito)) DESCR_SETOR_DEFEITO,
       obf.FASE_PROGRAMADA_MANU INCLUIDA_MANUAL,
       vup.data_hora_inicio DATA_HORA_INI,
       vup.data_hora_final DATA_HORA_FIM,
       to_number(obf.CODIGO_FASE||obf.tipo_processo) PI,
       trim(obf.descricao_pi) DESCR_PI,
  (SELECT TRIM(VPI.DESCRICAO) FROM VW_ENU_TIPO_PI VPI WHERE VPI.TIPO_PROCESSO_INDUST = obf.TIPO_PROCESSO_INDUST) DESCR_TIPO_PI,
      obf.TIPO_PROCESSO_INDUST,
       to_CHAR(vup.data_fim,'dd') DIA,
       (select (VEX.DESCR_PRODUCAO_EXTERNA) from fases_fluxo ffl, vw_f7_prd_prod_externa vex
          where ffl.codigo_fase = obf.codigo_fase and vex.PROD_EXTERNA=ffl.processoterceiros) LOCAL_PRODUCAO,
       (select (VEX.DESCR_TIPO_PRODUCAO) from vw_f7_prd_TIPO_PRODUCAO vex where vex.tipo_prod=eng.TIPO_PROD) TIPO_PRODUCAO,
       ltrim(obf.unidade_fabril,'0') UND_FAB,
       (select TRIM(UFB.NOME_UNIDADE_FABRIL) from unidade_fabril ufb where ufb.codigo_unidade_fabri=OBF.unidade_fabril) NOME_UNIDADE_FABRIL,
       Case
         When nvl(ped.nro_pedidos,0) = 1 then (select MAX(PCO.PEDIDOCLIENTE) from pedidocomercial pco
                  where pco.pedido = ped.pedido)
         Else ''
       end PEDIDO_CLIENTE_EXCLUSIVO,
       Case
         When nvl(ped.nro_pedidos,0) <> 0 then Ped.PEDIDO
         Else 0
       end PEDIDO_EXCLUSIVO,
       NVL(Case
         When nvl(ped.nro_pedidos,0) = 1 then (select MAX(PFJ.NOME) from pedidocomercial pco, pessoasfj pfj
                  where pco.pedido = ped.pedido
                  and pfj.IDPESSOAFJ = pco.idfilialresponsavel)
         Else (SELECT TRIM(PFJ.NOME) FROM PESSOASFJ PFJ WHERE PFJ.IDPESSOAFJ = PAR.IDPESSOAFJ)
       end,ENG.DESCR_CLIENTE_ITEM) NOME_CLIENTE_EXCLUSIVO,
       NVL(Case
         When nvl(ped.nro_pedidos,0) = 1 then (select PCO.IDFILIALRESPONSAVEL from pedidocomercial pco
                  where pco.pedido = ped.pedido)
         Else PAR.IDPESSOAFJ
       end,0) IDPFJ_EXCLUSIVO,
       OBe.CODIGO_FLUXO FLUXO,
       OBe.NUMERO_GRUPO_PROGRAM,
       eng.tpunidademedida,
       eng.TIPO_PROD,
      CAST(NVL((SELECT ffx.PROCESSOTERCEIROS FROM FASES_FLUXO FFX WHERE ffx.codigo_fase = obf.codigo_fase),0) AS NUMBER(10)) PROD_EXTERNA,
       eng.CODIGO,
       eng.IDGI,
       obe.OB_ALTERNATIVA,
      eng.DESCR_GRUPO_ITEM,
      ENG.descr_tipo_variante,
      (select trim(vto.DESCRICAO) from VW_ENU_OB_TIPO_ORDEM vto where vto.TIPO_ORDEM = obe.TIPO_ORDEM) DESCR_TIPO_ORDEM,
       OBe.TIPO_ORDEM,
       to_char(vup.data_fim,'rrrrmm') ANO_MES,
       TB.TIPO_BUSCA,
       decode(
       nvl((select max(gfl.cbefetuadivlongitudi) from grupo_fluxo gfl where obe.idgrupofluxo = gfl.idgrupofluxo),0),
            1,1,0) CORTE_LONGITUDINAL,
       nvl((select max(gfl.nrpecasdivisao) from grupo_fluxo gfl where gfl.idgrupofluxo = obe.idgrupofluxo),0)
         PECAS_CORTE_LONGITUDINAL,
        decode(obf.CBCORTELONGITUDINAL,1,1,0) FASE_CORTE_LONGITUDINAL,
        (SELECT trim(vtb.DESCR_TIPO_BUSCA) FROM VW_F7_PRD_TIPO_BUSCA VTB WHERE VTB.TIPO_BUSCA = TB.TIPO_BUSCA) DESCR_TIPO_BUSCA,
       1 PERIODO,
       'Por Turno (Saída Máquina)' DESCR_PERIODO,
       eng.familia_estoque,
       eng.DESCR_FAMILIA_ESTOQUE,
       obf.ID_LIGA_CADREC_ITEMR,
       cASE
          wHEN ENG.idleprojeto <> 0 then (select TRIM(LEP.PROJETO) from le_projeto lep where lep.idleprojeto = ENG.idleprojeto)
          Else ''
       END PROJETO,
       CASE                                                          /* Fabiano Barbosa 29/03/2017 - inicio tarefa 106805*/
         /* wHEN (select COUNT(IDP.NUMOBGERADA) from itens_desenv_prod idp where idp.numobgerada = OBF.numero_ob) <> 0 THEN 1*/
         when (select count(lid.numero_ob)
                 from LE_OB_ITENS_DESENV lid
                where lid.numero_ob = OBF.numero_ob) <> 0 then 1     /* Fabiano Barbosa 29/03/2017 - fim tarefa 106805*/
         else 0
       end DESENV_PROD,
       vup.numeroup,
         obf.idpessoasfjtec IDPFJ_PRIOR_TEC,
       (select TRIM(PFJ.NOME) from pessoasfj pfj where pfj.idpessoafj = obf.idpessoasfjtec) NOME_CLIENTE_PRIOR_TEC,
       (select TRIM(PFJ.NOMEFANTASIA) from pessoasfj pfj where pfj.idpessoafj = obf.idpessoasfjtec) NOME_FANTASIA_PRIOR_TEC,
       (SELECT TRIM(EPT.DESCRICAO) FROM pessoasfj pfj, eng_prioridade_tec EPT WHERE pfj.idpessoafj = obf.idpessoasfjtec and EPT.ID = pfj.IDPRIORIDADETEC) DESCR_PRIOR_TEC,
       obe.exportacao,
       OBe.PRIM_LOTE_POR_COR PRIM_LOTE_COR,
       OBe.PRIM_LOTE_PROCESSO PRIM_LOTE_PROC,
       NVL((select GFA.SETOR_SEQUENCIA from  GRUPO_FASES GFA, FASES_FLUXO FFL where FFL.CODIGO_FASE=obf.CODIGO_FASE AND GFA.CODIGO = FFL.CODIGO_GRUPO),0) SETOR_IND,
       obf.numeroordemmovimento||'-'||obf.sequenciaordemmovime DOCUMENTO,
       obf.NUMEROORDEMMOVIMENTO ORDEM_MOV,
       obf.SEQUENCIAORDEMMOVIME SEQ_ORDEM_MOV,
       obf.SECAO,
       (select SUBSTR(optstraggr(TRIM(obs.texto)),1,100) from observacao obs where obs.codigo = obf.codigo_observacao) OBSERVACAO_FASE,
      (SELECT TRIM(SEC.DESSEC) FROM SECAO sec where sec.secao = obf.secao) DESCR_SECAO,
      OBF.PERC_PARCIAL
 FROM
           vw_bnf_ob_fases_up vup, ob obe,
       (select obfX.Numero_Ob,
            nvl(obfX.Sequencia,0) sequencia,
            oby.codpro_reduzido,
            obfX.Numero_Maquina, obfX.Codigo_Fase, obfX.Status status_fase,
             obfX.Tipo_Processo, obfX.Especificacao_Produt, obfX.Processo_Especifico, obfX.Codigo_Cor_Desenho, obfX.Codigo_Variante,
             obfX.Codigo_Grupo, obfX.Numeroordemmovimento, obfX.Sequenciaordemmovime,
             pri.tipo_processo_indust, pri.descricao_pi,
            TO_NUMBER(obfx.codigo_fase||obfx.tipo_processo) PI_REC,
            oby.idpessoasfjtec,
            OBFx.CODIGO_COR_DESENHO COR_REC,
            OBFx.ESPECIFICACAO_PRODUT EP_REC,
            OBFx.PROCESSO_ESPECIFICO PE_REC,
            decode(obfx.kilos_produzidos,0,oby.kilos,obfx.kilos_produzidos) kilos,
            decode(obfx.metros_produzidos,0,oby.metros,obfx.metros_produzidos) metros,
       Case
          When OBFx.CODIGO_GRUPO =0 then 100
          When obfx.codigo_grupo <>0 and maq.tipo_maquina in (17,18,19,20,21,22,60)
               and (select ite.idunidademedida from itens_estoque ite where ite.codigo_reduzido = oby.codpro_reduzido) = 1
               and (select SUM(DECODE(obk.KILOS_PRODUZIDOS,0,OBY.KILOS,obk.KILOS_PRODUZIDOS))
                       from ob_fases obk where obk.codigo_grupo = obfx.codigo_grupo) <>0 then
                obfx.kilos_produzidos / (select SUM(DECODE(obk.KILOS_PRODUZIDOS,0,OBY.KILOS,obk.KILOS_PRODUZIDOS))
                       from ob_fases obk where obk.codigo_grupo = obfx.codigo_grupo) *100
          When (select SUM(DECODE(obk.METROS_PRODUZIDOS,0,OBY.METROS,obk.METROS_PRODUZIDOS))
                       from ob_fases obk where obk.codigo_grupo = obfx.codigo_grupo) <> 0 then
                obfx.METROS_produzidos / (select SUM(DECODE(obk.METROS_PRODUZIDOS,0,OBY.METROS,obk.METROS_PRODUZIDOS))
                       from ob_fases obk where obk.codigo_grupo = obfx.codigo_grupo) *100
          Else 1 / (select count(obk.numero_ob)
                       from ob_fases obk where obk.codigo_grupo = obfx.codigo_grupo)
       End PERC_GRUPO,
            obfx.fase_programada_manu, obfx.operador_inicio, obfx.operador_final, obfx.carga_maxima, to_number(obfx.CBCORTELONGITUDINAL) CBCORTELONGITUDINAL,
            obfx.grupo_defeito, obfx.tipo_defeito, obfx.destino_receita, obfx.red_ob_qualidade, obfx.id_liga_cadrec_itemr, maq.grupo,
             obfX.Velocidade,
--              obe.status, obe.codigo_reduzido, obe.codigo_fluxo, obe.data_entrega_pedido, obe.codigo_reduzido_cru, OBE.TIPO_ORDEM,
--             OBE.PRIM_LOTE_POR_COR, OBE.PRIM_LOTE_PROCESSO, OBE.EXPORTACAO, OBE.OB_ALTERNATIVA, OBE.NUMERO_GRUPO_PROGRAM, obe.idgrupofluxo,
        maq.tipo_maquina,
        TRIM(MAQ.NOME_MAQUINA) DESCR_MAQ,
        gpr.unidade_fabril,
        Case
           When obfX.Codigo_Variante <> '     ' then
                ((TRUNC(MAQ.HORAMAQUINA_CARGA_DE)*60) + (MAQ.HORAMAQUINA_CARGA_DE-TRUNC(MAQ.HORAMAQUINA_CARGA_DE))*100) +
               (select nvl(vde.tempo_preparacao_maq,0) from variante_desenho vde where vde.processo_industrial = pri.processo_industrial
                and vde.codigo_desenho = obfX.Codigo_Cor_Desenho
                and vde.codigo_variante = obfX.Codigo_Variante
                and vde.especificacao_produt = obfX.Especificacao_Produt)
           Else ((TRUNC(MAQ.HORAMAQUINA_CARGA_DE)*60) + (MAQ.HORAMAQUINA_CARGA_DE-TRUNC(MAQ.HORAMAQUINA_CARGA_DE))*100)
        END MIN_SETUP,
         NVL(gdx.tipo_destino,0)  tipo_destino, trim(dex.descricao) descr_destino,
        OBFx.Codigo_Observacao, maq.velocidade_maquina,
        maq.secao,
        100 PERC_PARCIAL
       from ob_fases obfX, ob_produto oby, maquina maq, processo_industrial pri, grupo_maquinas gpr, destino dex, grupo_destino gdx
       where maq.setor = 5
       and maq.numero_maquina = obfX.Numero_Maquina
       and oby.numero_ob = obfx.numero_ob
       and pri.codigo_fase = obfX.Codigo_Fase and pri.tipo_processo = obfX.Tipo_Processo
       and gpr.setor = maq.setor
       and gpr.grupo = maq.grupo
       and dex.destino (+) = obfX.Destino_Receita
       and gdx.codigo_grupo (+) = dex.codigo_grupo
          ) obf,
       (select p.numeroob numero_ob, count(*) nro_pedidos,
            max(pco.pedido) pedido
       from pedproducaoob p, ofordens ofo, ofpedido ofp,  itenspedidoqtdes ipx, itenspedidograde ipg, pedidocomercial pco
   where ofo.numeropedproducao = p.numero and ofp.numeroof = ofo.numeroof and ipx.iditenspedidoqtdes = ofp.iditenspedidoqtdes
   and ipg.iditenspedidograde = ipx.iditempedgrade and pco.pedido = ipg.pedido
    group by p.numeroob) ped,
   (SELECT fl.filial, fl.IDPESSOAFJ FROM  filiais fl) PAR, -- Artur D. - 16/08/2018 - Campos da tela de parâmetros gerais trocados
   vw_pi_cenga03_prodaca eng,
    (SELECT 1 TIPO_BUSCA FROM DUAL
UNION ALL
SELECT 2 TIPO_BUSCA FROM DUAL
   ) TB
 where obe.numero_ob = vup.numero_ob
 and OBF.NUMERO_OB = VUP.numero_ob
 AND OBF.SEQUENCIA = VUP.seq
 and obf.codpro_reduzido = obe.codigo_reduzido
-- and vup.STATUS_UP = 0 Hugo CR - 19/12/2018
 and eng.REDUZ = obe.CODIGO_REDUZIDO
 and ped.numero_ob (+) = vup.numero_ob
 AND PAR.FILIAL = vup.CDFILIAL -- Artur D. - 16/08/2018 - Campos da tela de parâmetros gerais trocados
-- and VUP.numeroup = 451048


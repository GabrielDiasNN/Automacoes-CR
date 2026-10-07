/* =============================================================================
OBJETIVO: VW_PI_CBPAP01_PROCBENEF
DOMÍNIO: 11_views_referencia_sgt
ARQUIVO ORIGINAL: Comandos SQL - CR\VW_PI_CBPAP01_PROCBENEF.sql
TIPO: DDL / Definição de View
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: Não identificadas explicitamente
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

--CREATE OR REPLACE VIEW VW_PI_CBPAP01_PROCBENEF AS
select
      obe.cdfilial filial,
      obe.numero_ob,
      (select trim(vto.descricao) from vw_enu_ob_tipo_ordem vto where vto.tipo_ordem = obx.tipo_ordem) descr_tipo_ordem,
      obx.codigo_reduzido reduz,
      eng.descr_item,
      case
        when obe.status = 1 and obe.tpunidademedida = 3 then decode(sign(ordem_qtd-aca_qtd),-1,0,ordem_qtd-aca_qtd)
        when obe.status = 1 and obe.tpunidademedida = 1 then decode(sign(ordem_qtd-aca_qtd),-1,0,ordem_qtd-aca_qtd) * obx.rendimento_origem
        else 0
      end metros_proc,
      case
        when obe.status = 1 and obe.tpunidademedida = 1 then decode(sign(ordem_qtd-aca_qtd),-1,0,ordem_qtd-aca_qtd)
        when obe.status = 1 and obe.tpunidademedida = 3 and obx.pecas_corte_longitudinal not in (0,1)
                            and obe.montada = 1 and obx.kilos_produzidos = 0
                             then decode(sign(obp.kilos-acab_kg),-1,0,kilos-acab_kg)
        when obe.status = 1 and obe.tpunidademedida = 3 and obx.pecas_corte_longitudinal not in (0,1) then decode(sign(obx.kilos_produzidos-acab_kg),-1,0,kilos_produzidos-acab_kg)
        when obe.status = 1 and obe.tpunidademedida = 3 and obx.rendimento_origem <> 0 then decode(sign(ordem_qtd-aca_qtd),-1,0,ordem_qtd-aca_qtd) / obx.rendimento_origem
        else 0
      end quilos_proc,
      vfa.descr_fase,
      (select max(obz.codigo_placa) from ob_fases obz where obz.numero_ob = obx.numero_ob ) placa_kanban,
      obe.prog_qtd quant_prog,
      obe.orig_qtd quant_orig,
      obe.ordem_qtd quant,
       (select optstraggrasc(v.modo_estampar)
          from (select distinct x.codigo_desenho
                              , x.codigo_variante
                              , x.modo_estampar
                              , x.especificacao_produt
                  from variante_desenho x) v
         where trim(v.codigo_desenho)  = eng.DESENHO
           and trim(v.codigo_variante) = eng.VARIANTE
           and v.especificacao_produt  = eng.EP
       ) modo_estampar,
      case
        when obe.status = 1 then decode(sign(ordem_qtd-aca_qtd),-1,0,ordem_qtd-aca_qtd)
        else 0
      end quant_proc,
      case
        when obe.status = 1 and obe.tpunidademedida = 1 and obp.kilos_programados <> 0
           and (ordem_qtd-aca_qtd)*(obp.kilos_acabados / obp.kilos_programados) > 0 then (ordem_qtd-aca_qtd)*(obp.kilos_acabados / obp.kilos_programados)
        when obe.status = 3 and obe.tpunidademedida = 1 and obp.metros_programados <> 0
           and (ordem_qtd-aca_qtd)*(obp.metros_acabados / obp.metros_programados) > 0 then (ordem_qtd-aca_qtd)*(obp.metros_acabados / obp.metros_programados)
        else 0
      end quant_proc_aca,
      eng.um,
      obe.pc_cru pecas_orig,
      obe.pc_aca pecas_aca,
      obe.aca_qtd quant_aca,
            vfa.sequencia seq,
      vfa.codigo_fase fase,
      vfa.codigo_grupo,
      (select max(ltrim(vfx.localizacao,'0')) from vw_bnf_faseanteriorob vfx where vfx.numero_ob = obe.numero_ob)
         localizacao,
      cast (( select optstraggr(trim(ltrim(lote_produto,'0'))) from
 ( select distinct gpo.numero_ob, gpp.lote_produto from gerapecaorigemob gpo, gerapecasproduto gpp
   where gpp.idpecasproduto = gpo.idpecasproduto) where numero_ob = obe.numero_ob) as varchar2(50)) lote_produto_origem,
      eng.tipo,
      (select trim(bpa.descr_um) from vw_f7_prd_bpa_und_med bpa where bpa.tpunidademedida=eng.tpunidademedida) descr_um,
      (select trim(vex.descricao) from vw_enu_status_ob_nc vex where vex.status_nc=obe.status_nc) descr_status_nc,
      (select trim(vex.descricao) from vw_enu_status_ob_cq vex where vex.status_cq=obe.status_cq) descr_status_cq,
       (select max(lso.idlab_solic) from lab_solic lso, lab_tiposolicteste lst
       where lso.tipostqualidade=0 and lso.numero_documento=obe.numero_ob and lso.sequencia_fase=vfa.sequencia and lst.idlab_tiposolicteste=lso.idlab_tiposolicteste
       and lst.tipostqualidade=0) st_cq,
       (select max(vss.descricao) from lab_solic lso, lab_tiposolicteste lst, vw_enu_status_st vss
       where lso.tipostqualidade=0 and lso.numero_documento=obe.numero_ob and lso.sequencia_fase=vfa.sequencia and lst.idlab_tiposolicteste=lso.idlab_tiposolicteste
       and lst.tipostqualidade=0 and vss.id_status=lso.status) descr_status_st_cq,
       (select max(lso.status) from lab_solic lso, lab_tiposolicteste lst
       where lso.tipostqualidade=0 and lso.numero_documento=obe.numero_ob and lso.sequencia_fase=vfa.sequencia and lst.idlab_tiposolicteste=lso.idlab_tiposolicteste
       and lst.tipostqualidade=0) status_st_cq,
      obe.montada,
      vfa.fases_conf,
      eng.artigo,
      eng.descr_artigo,
      eng.cor,
      eng.descr_cor,
      eng.RGB_COR,
      eng.acabamento,
      eng.artigo_var,
      eng.DIMENSAO_COD dimensao,
      eng.descr_estrutura,
      eng.descr_desenho,
      eng.descr_variante,
      eng.descr_processo,
      eng.descr_atrib1,
      eng.descr_atrib2,
      eng.descr_atrib3,
      eng.descr_var_artigo,
      eng.descr_dimensao,
      eng.cliente_item,
      eng.descr_cliente_item,
      eng.codind,
      eng.codcom,
      eng.codigo_alternativo,
      eng.desenho,
      eng.variante,
      eng.idleprojeto,
      eng.linha_produto,
      eng.tesituacaoproduto,
      eng.descr_situacao_produto,
      eng.intermediario,
      eng.descr_linha_produto,
      eng.DESCR_TIPO_PRODUTO,
       case
          when obx.menor_status_consumo in (0,1,2,3) then 'falta executar'
          when obx.menor_status_consumo in (4) then 'falta confirmar'
          when obx.menor_status_consumo in (6) then 'confirmado'
          else 'não usa'
        end situacao_confirmacao_consumo,
      case
        when (select count(lid.numero_ob)
                from itens_desenv_prod idp, LE_OB_ITENS_DESENV lid
               where idp.codigo_reduzido = obe.codigo_reduzido
                 and idp.id =  lid.id_iten_desenv_prod
                 and lid.numero_ob = obe.numero_ob) <> 0 then 1
        else 0
      end desenv_prod,
      obe.data_emissao,
      obe.data_progr,
      obp.metros_programados metros_prog,
      obp.metros,
      obp.kilos_programados quilos_prog,
      obp.kilos quilos,
      vfa.setor_sequencia setor_ind,
        (select trim(stx.descricao) from setor_industrial stx where stx.setor_sequencia = vfa.setor_sequencia)
         descr_setor_ind,
      maq.tipo_maquina,
       (SELECT TRIM(VTM.DESCRICAO) FROM TIPOSMAQUINAS VTM WHERE VTM.IDTIPOSMAQUINA = MAQ.TIPO_MAQUINA) descr_tipo_maquina,
      (select trim(des.descricao) from destino des where des.destino = vfa.destino_receita ) descr_destino,
      eng.tpunidademedida,
     cast  ((select substr(optstraggr('pi '||pord.pedido||'/'||pord.itempedido||' pc '||trim(pord.pedidocliente)||' '||trim(pord.nome)),1,150)
     from (select vpo.numeroob numero_ob, vpo.pedido, vpo.itempedido, vpo.quantidade, pfj.nome, vpo.pedidocliente
       from vw_plm_of_pedido_ordem vpo, pessoasfj pfj
   where vpo.setor = 5 and vpo.SIT_PED = 1
   and pfj.idpessoafj = vpo.idfilialresponsavel order by vpo.quantidade desc) pord where pord.numero_ob = obe.numero_ob and rownum <=3 )
   as varchar2(150)) pedido,
      (select min(pkgutil0001.fnc_cnvdata(ipc.expedirem,null))
                                 from vw_plm_of_pedido_ordem vpo, itenspedidocomercial ipc
                                 where obx.numero_ob = vpo.numeroob
                                 and vpo.setor = 5
                                 and vpo.SIT_PED = 1
                                 and ipc.pedido = vpo.pedido
                                 and ipc.itempedido = vpo.itempedido
                                  ) data_entrega,
      (select min(pkgutil0001.fnc_cnvdata(ipd.programadopara,null))
                                 from vw_plm_of_pedido_ordem vpo, itenspedidodatas ipd
                                 where obx.numero_ob = vpo.numeroob
                                 and vpo.setor = 5
                                 and vpo.SIT_PED = 1
                                 and ipd.pedido = vpo.pedido
                                 and ipd.itempedido = vpo.itempedido
                                  ) data_plano_pedido,
       case
         when nvl(ped.nro_pedidos,0) = 1 then ped.idfilialresponsavel
         else 0
       end idpfj_exclusivo,
       case
         when nvl(ped.nro_pedidos,0) = 1 then (select max(pfj.nome) from pessoasfj pfj
                  where pfj.idpessoafj = ped.idfilialresponsavel)
         else ''
       end nome_cliente_exclusivo,
       case
         when nvl(ped.nro_pedidos,0) <> 0 then ped.pedido
         else 0
       end pedido_exclusivo,
       case
         when nvl(ped.nro_pedidos,0) = 1 then ped.pedidocliente
         else ''
       end pedido_cliente_exclusivo,
        obe.lead_time_real,
        obe.lead_time_prev,
       case
         when obe.lead_time_prev <>0 and obe.lead_time_prev < obe.lead_time_real then 'atraso'
         when obe.lead_time_prev <>0 and sign((abs(obe.lead_time_prev-obe.lead_time_real/obe.lead_time_prev))*100-50) = -1 then 'atenção'
         else 'normal'
       end descr_analise_lead_time,
       case
         when obe.lead_time_prev <>0 and obe.lead_time_prev < obe.lead_time_real then 2
         when obe.lead_time_prev <>0 and sign((abs(obe.lead_time_prev-obe.lead_time_real/obe.lead_time_prev))*100-50) = -1 then 1
         else 0
       end analise_lead_time,
       case
         when obe.lead_time_prev <>0 and obe.lead_time_prev < obe.lead_time_real then 1
         else 0
       end atraso_lead_time,
       case
         when trunc(sysdate) >   (select nvl(min(pkgutil0001.fnc_cnvdata(ipc.expedirem,null)),trunc(sysdate))
                                 from vw_plm_of_pedido_ordem vpo, itenspedidocomercial ipc
                                 where obx.numero_ob = vpo.numeroob
                                 and vpo.setor = 5
                                 and vpo.SIT_PED = 1
                                 and ipc.pedido = vpo.pedido
                                 and ipc.itempedido = vpo.itempedido
                                  ) then 1
         else 0
       end atraso_data_entrega,
       case
         when trunc(sysdate) >   (select nvl(min(pkgutil0001.fnc_cnvdata(ipd.programadopara,null)),trunc(sysdate))
                                 from vw_plm_of_pedido_ordem vpo, itenspedidodatas ipd
                                 where obx.numero_ob = vpo.numeroob
                                 and vpo.setor = 5
                                 and vpo.SIT_PED = 1
                                 and ipd.pedido = vpo.pedido
                                 and ipd.itempedido = vpo.itempedido
                                  ) then 1
         else 0
       end atraso_data_plano,
       (select trim(fgr.descricao) from fluxogrupo fgr where fgr.id=obe.idfluxogrupo) descr_grupo_fluxo,
       obe.data_ult_conf data_hora_ult_conf,
       obe.data_pri_conf data_hora_pri_conf,
       case
         when decode(obe.data_ult_conf,null,sysdate-obe.data_emissao,sysdate-obe.data_ult_conf) < 0 then 0
         else decode(obe.data_ult_conf,null,sysdate-obe.data_emissao,sysdate-obe.data_ult_conf)
       end dias_parado,
       obx.codigo_fluxo fluxo,
       obx.numero_grupo_program num_gp,
       eng.codigo,
       obx.corte_longitudinal,
       obx.pecas_corte_longitudinal,
       eng.estampado,
       cast ((select substr(optstraggr(obs.texto),1,150) from observacao obs where obs.codigo=obx.codigo_observacao) as varchar2(150)) observacao,
       obx.tipo_ordem,
      ltrim(vfa.numero_maquina,'0') numero_maquina,
      trim(maq.nome_maquina) descr_maquina,
       (select (vex.descr_tipo_producao) from vw_f7_prd_tipo_producao vex where vex.tipo_prod= eng.tipo_prod) tipo_producao,
       (select (vex.descr_producao_externa) from vw_f7_prd_prod_externa vex where vex.prod_externa=obe.prod_externa) local_producao,
     eng.tipo_prod,
       vfa.status status_fase,
       (select trim(vfx.descricao) from vw_enu_status_ob_fases vfx where vfx.status=vfa.status) descr_status_fase,
       to_number(obe.prod_externa) prod_externa,
       TRIM(obx.ob_alternativa) ob_alternativa,
       eng.idgi,
       eng.descr_grupo_item,
      vfa.pi,
      (select trim(pri.descricao_pi) from processo_industrial pri where pri.processo_industrial=vfa.pi) descr_pi,
       obx.status_nc,
       eng.larg largura,
       obx.rendimento_origem,
       obx.largura_origem,
      eng.composicao,
      eng.idgrupodimensao,
      eng.descr_grupo_dimensao,
       (select bpf.deposito_produto_em_ from beneparametrofilial bpf where bpf.cdfilial = obx.cdfilial) deposito,
       (select trim(dep.descricao) from beneparametrofilial bpf, deposito dep where bpf.cdfilial = obx.cdfilial and dep.codigo_deposito = bpf.deposito_produto_em_) descr_deposito,
       pkgutil0001.fnc_cnvdata (obp.data_entrega_pedido,null) data_plano,
       to_char(pkgutil0001.fnc_cnvdata (obp.data_entrega_pedido,null)+1,'rrww') semana_plano,
       obx.numero_semana_plano periodo_plano,
       eng.linha_prod_comercial,
       eng.descr_linha_prod_comercial,
       obe.status,
       (select trim(vst.descricao) from vw_enu_status_ob vst where vst.status = obe.status) descr_status_ob,
       (select trim(gca.descricao) from povitemestogrupoarti poa, grupo_artigo gca where poa.codigo_reduzido=obx.codigo_reduzido and gca.idgrupoartigo=poa.idgrupoartigo) descr_grupo_artigo_pov,
       nvl((select trim(poa.idgrupoartigo) from povitemestogrupoarti poa where poa.codigo_reduzido=obx.codigo_reduzido),'') idgrupoartigo,
       eng.familia_estoque,
       eng.descr_familia_estoque,
       eng.descr_tipo_variante,
       eng.idmascara,
       obp.idpessoasfjtec idpfj_prior_tec,
       (select trim(pfj.nome) from pessoasfj pfj where pfj.idpessoafj = obp.idpessoasfjtec) nome_cliente_prior_tec,
       (select trim(pfj.nomefantasia) from pessoasfj pfj where pfj.idpessoafj = obp.idpessoasfjtec) nome_fantasia_prior_tec,
       (select trim(ept.descricao) from pessoasfj pfj, eng_prioridade_tec ept where pfj.idpessoafj = obp.idpessoasfjtec and ept.id = pfj.idprioridadetec) descr_prior_tec,
       obx.exportacao,
       obx.prim_lote_por_cor,
       obx.prim_lote_processo,
       eng.item_exclusivo,
       obe.status_cq,
       ltrim(MAQ.CODIGO_UNIDADE_FABRI,0) UNI_FAB,
       TRIM(maq.nome_unidade_fabril) DESCR_UNIDADE_FABRIL,
       Case
          When ped.cd_subtipoped in (6,7,8,9,31,21,29) then 'Sim'
          Else 'Não'
       END BANDEIRA
from
    vw_bnf_obmontada obe,
    (select obxx.numero_ob, obxx.cdfilial, obxx.codigo_reduzido, obxx.status_nc, obxx.status_cq,
            obxx.ob_alternativa, obxx.tipo_ordem, obxx.numero_grupo_program, obxx.codigo_fluxo, obxx.status,
            obxx.codigo_observacao,
            obxx.idgrupofluxo,
           nvl((select vfz.kilos_produzidos from vw_bnf_faseanteriorob vfz where vfz.numero_ob=obxx.numero_ob),0) kilos_produzidos,
           nvl((select vfz.metros_produzidos from vw_bnf_faseanteriorob vfz where vfz.numero_ob=obxx.numero_ob),0) metros_produzidos,
       obxx.exportacao,
       obxx.numero_semana_plano,
       obxx.prim_lote_por_cor,
       obxx.prim_lote_processo,
       decode(
       nvl((select gfl.cbefetuadivlongitudi from grupo_fluxo gfl where gfl.idgrupofluxo = obxx.idgrupofluxo),0),
            1,1,0) corte_longitudinal,
      nvl((select gfl.nrpecasdivisao from grupo_fluxo gfl where gfl.idgrupofluxo = obxx.idgrupofluxo),0)
         pecas_corte_longitudinal,

            (select min(obz.status) from ob_fases obz, fases_fluxo ffx where ffx.codigo_fase=obz.codigo_fase and ffx.contr_confir_cosumo = 1
               and obz.numero_ob = obxx.numero_ob ) menor_status_consumo,
       case
         when ico.tipo_da_gramatura = 1 and (ico.gramatura * ico.largura) <>0 then 1000/(ico.gramatura*ico.largura)
         when ico.tipo_da_gramatura <> 1 and ico.gramatura <>0 then 1000/ico.gramatura
         else 0
       end rendimento_origem,
       ico.largura largura_origem
       from ob obxx, itens_complemento ico
       where obxx.status <> 0
       and obxx.tipo_ordem in (0,6)
       and ico.codigo_reduzido = obxx.codigo_reduzido_cru
        ) obx,
          (select p.numeroob numero_ob,
            min(pco.pedido) pedido,
            max(pco.pedidocliente) pedidocliente,
            max(pco.idfilialresponsavel) idfilialresponsavel,
            count(pco.pedido) nro_pedidos,
-- William Mello - Início - 16/11/2017 - Salete - Subtipo para diferenciar BANDEIRA de PRODUÇÃO - TR 123753
            max(pco.cd_subtipoped) cd_subtipoped
-- William Mello - Fim - 16/11/2017 - Salete - Subtipo para diferenciar BANDEIRA de PRODUÇÃO - TR 123753
       from pedproducaoob p, ofordens ofo, ofpedido ofp,  itenspedidoqtdes ipx, itenspedidograde ipg, pedidocomercial pco
   where ofo.numeropedproducao = p.numero and ofp.numeroof = ofo.numeroof and ipx.iditenspedidoqtdes = ofp.iditenspedidoqtdes
   and ipg.iditenspedidograde = ipx.iditempedgrade and pco.pedido = ipg.pedido and p.setor = 5
    group by p.numeroob) ped,
     vw_pi_cenga03_prodaca eng,
     ob_produto obp,
     vw_bnf_faseatualob vfa,

     (SELECT MAQx.Numero_Maquina, MAQx.Nome_Maquina, MAQx.Setor, UFA.EH_FACCAO, ufa.nome_unidade_fabril, maqx.codigo_unidade_fabri,
        maqx.Idtiposmaquina tipo_maquina
       FROM MAQUINA MAQx, UNIDADE_FABRIL UFA
        where maqx.setor = 5
       and UFA.CODIGO_UNIDADE_FABRI = MAQx.Codigo_Unidade_Fabri) MAQ
where obe.status <>0
and  eng.reduz = obx.codigo_reduzido
and obx.numero_ob = obe.numero_ob
and obp.numero_ob  = obe.numero_ob
and vfa.numero_ob = obe.numero_ob
and maq.numero_maquina (+) = vfa.numero_maquina
and ped.numero_ob (+) = obx.numero_ob


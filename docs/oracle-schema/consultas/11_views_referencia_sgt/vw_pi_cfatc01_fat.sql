/* =============================================================================
OBJETIVO: VW_PI_CFATC01_FAT
DOMÍNIO: 11_views_referencia_sgt
ARQUIVO ORIGINAL: SGTPRD.VW_PI_CFATC01_FAT (Dicionário ALL_VIEWS)
TIPO: DDL / Definição de View
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.NOTAFISCALCAPA, SGTPRD.NOTAFISCALITENS, SGTPRD.BD_FAT_FATURAMENTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.PESSOASFJ, SGTPRD.PEDIDOCOMERCIAL
CUIDADOS OPERACIONAIS: View corporativa pesada de faturamento (~25 tabelas e 51 subqueries por linha). Apenas referência DDL — não executar em produção.
============================================================================= */

CREATE OR REPLACE VIEW SGTPRD.VW_PI_CFATC01_FAT AS
select VFA.FILIALNOTA FILIAL,
       nsa.cdchavenfe,
       (select trim(fil.descricao)
          from filiais fil
         where fil.filial = VFA.FILIALNOTA) NOME_FILIAL,
       vfa.numeronota NUMERO_NF,
       VFA.SERIENOTA SERIE_NF,
       VFA.DATA_DA_EMISSAO DATA_EMISSAO,
       (select trim(vex.dstipoopernatureza)
          from SUPRTIPOOPERNATUREZA vex
         where vex.id = vfa.TIPO_OPERACAO) DESCR_TIPO_OPERACAO,
       (select trim(vex.DESCRICAO)
          from vw_enu_tipo_oper_nat vex
         where vex.tiopernatureza = vfa.tiopernatureza) DESCR_OPERACAO,
       VFA.CODIGO_REDUZIDO REDUZ,
       trim(ite.descricao) DESCR_ITEM,
       trim(ite.nome_detalhado1) DESCR_ITEM_1,
       trim(ite.nome_detalhado2) DESCR_ITEM_2,
       (select trim(vti.DESCRICAO)
          from vw_enu_tipo_item vti
         where vti.TIPO_ITEM = ite.tipo_item) DESCR_TIPO_ITEM,
       trim(pfj.nome) NOME_cliente,
       trim(pfj.nomefantasia) NOME_FANTASIA_cliente,
       vfa.Fator_romaneio,
       NVL(cps.idfilialresponsavel, nsa.idpessoafj) IDCLIENTE_COMPRADOR,
       cASE
          WHEN NVL(cps.idfilialresponsavel,0) <> NSA.IDPESSOAFJ THEN '1'
          ELSE '0'
       END cliente_fatura_dif_comprador,
       trim(pfj1.nome) NOME_cliente_COMPRADOR,
       trim(pfj1.nomefantasia) NOME_FANT_cliente_COMPRADOR,
       cASE
         WHEN pro.tiitemprodrom = 4 THEN 0 -- INSUMO APLICADO SERVIÇO
         WHEN MTI.SERIE = 510 AND ROUND(VFA.QUANT,4) <> ROUND(PNS.QTITEM * VFA.FATOR_ROMANEIO,4) THEN ROUND(PNS.QTITEM * VFA.FATOR_ROMANEIO,4) -- COSTARICA
         ELSE VFA.QUANT
       END QUANT,
       cASE
         WHEN pro.tiitemprodrom = 4 THEN 0
         WHEN MTI.SERIE = 510 AND ROUND(VFA.QUANT,4) <> ROUND(PNS.QTITEM * VFA.FATOR_ROMANEIO,4) THEN 1 -- COSTARICA
         ELSE 0
       END QUANT_AJUSTADA,
       --
       (select TRIM(und.dssigla)
          from unidade_medida und
         where und.idunidademedida = vfa.idunidademedida) UM,
       (SELECT TRIM(vtp.DESCRICAO)
          FROM VW_ENU_TIPO_UNID_MEDIDA vtp
         where vtp.TPUNIDADEMEDIDA = vfa.tpunidademedida) DESCR_TIPO_UM,
       vfa.QUALIDADE QS,
        cASE
         WHEN pro.tiitemprodrom = 4 THEN 0
         ELSE vfa.kilos
       END QUILOS,
       cASE
         WHEN pro.tiitemprodrom = 4 THEN 0
         ELSE vfa.metros
       END METROS,
       vfa.preco_unit,
       CPS.PRECOLISTA PRECO_LISTA,
       (SELECT TRIM(CTA.NOME)
          FROM COML_TABELAPRECOS CTA
         WHERE CTA.TABELAPRECO = CPS.TABELAPRECO) NOME_TABELA_PRECO,
       vfa.VALOR - vfa.valor_desconto VALOR,
       VFA.VALOR_TOTAL_NOTA VALOR_TOTAL_NF,
       vfa.VALOR VALOR_BRUTO,
       (select trim(vex.nome)
          from REPRESENTANTES VEX
         where vex.idREPRESENTANTE = vfa.REPRESENTANTE) NOME_REPRESENTANTE,
       vfa.comissao,
       CASE
         WHEN (pns.vlcomissao * vfa.Fator_romaneio) IS not NULL THEN
           (pns.vlcomissao * vfa.Fator_romaneio)
         ELSE
           (vfa.VALOR - vfa.valor_desconto) * vfa.comissao / 100
       END as VALOR_COMISSAO, --Tarefa: 178534
       CASE
         WHEN (pns.vlcomissao * vfa.Fator_romaneio) IS not NULL THEN
           (pns.vlcomissao * vfa.Fator_romaneio)
         ELSE
           (vfa.VALOR - vfa.valor_desconto) * vfa.comissao / 100
       END as VALOR_COMISSAO_ITEM_PED, --Tarefa: 178534
       (SELECT P1.IDREPRESENT_INTERNO
          FROM PEDIDOCOMERCIAL P1
         WHERE P1.PEDIDO = CPS.pedido) REPRESENTANTE_INT,
       (SELECT trim(R1.NOME)
          FROM PEDIDOCOMERCIAL P1, REPRESENTANTES R1
         WHERE P1.PEDIDO = CPS.pedido
           AND R1.IDREPRESENTANTE = P1.IDREPRESENT_INTERNO) NOME_REPRESENTANTE_INT,
       (SELECT P1.PERC_COMISSA_REP_INT
          FROM PEDIDOCOMERCIAL P1
         WHERE P1.PEDIDO = CPS.pedido) COMISSAO_INT,
       (VFA.VALOR - VFA.VALOR_DESCONTO) *
       (SELECT P1.PERC_COMISSA_REP_INT
          FROM PEDIDOCOMERCIAL P1
         WHERE P1.PEDIDO = CPS.pedido) / 100 VALOR_COMISSAO_INT,
       VFA.VALOR_DESCONTO,
       VFA.VALOR_FRETE,
       VFA.VALOR_SEGURO,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              pns.vlbaseicms,
              vfa.valor / NVL(pns.vltotalbruto, 0)
              * pns.vlbaseicms) BASE_CALCULO_ICMS,
       pns.pcicms ICMS,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              pns.vlicms,
              vfa.valor / NVL(pns.vltotalbruto, 0)
              * pns.vlicms) VALOR_ICMS,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              pns.Vlpis,
              vfa.valor / NVL(pns.vltotalbruto, 0)
              * pns.Vlpis) VALOR_PIS,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              pns.Vlcofins,
              vfa.valor / NVL(pns.vltotalbruto, 0)
              * pns.Vlcofins) VALOR_COFINS,
       pns.pcipi IPI,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              pns.vlbaseipi,
              vfa.valor / NVL(pns.vltotalbruto, 0)
              * pns.vlbaseipi) BASE_CALCULO_IPI,
       VFA.VALOR_IPI,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              (vfa.valor_ipi + pns.vlicms + pns.Vlpis + pns.Vlcofins),
              ((vfa.valor / NVL(pns.vltotalbruto, 0)
              * (pns.vlicms + pns.Vlpis + pns.Vlcofins)) + vfa.valor_ipi)) VALOR_IMPOSTOS,
       decode(NVL(pns.vltotalbruto, 0),
              0,
              pns.vldespaces,
              vfa.valor / NVL(pns.vltotalbruto, 0)
              * pns.vldespaces) VALOR_DESP_ACESSORIAS,
       (select trim(CID.nome)
          from cidades cid
         where pfj.IDCIDADE = cid.IDCIDADE) CIDADE_cliente,
       (select trim(est.SIGLA_ESTADO)
          from cidades cid, estados est
         where pfj.IDCIDADE = cid.IDCIDADE
           and est.IDESTADO = cid.IDESTADO) UF_cliente,
       vfa.PEDIDO,
       vfa.item_pedido,
       trim(cps.PEDIDOCLIENTE) PEDIDO_CLIENTE,
       cps.DATA_ENTREGA data_entrega_pedido,
       cps.DATA_EMISSAO data_emissao_pedido,
       vfa.data_da_emissao - cps.DATA_EMISSAO DIAS_EMISSAO_PED_FAT,
       vfa.data_da_emissao - cps.DATA_ENTREGA DIAS_ENTREGA_PED_FAT,
       cASE
         When (vfa.data_da_emissao - cps.DATA_ENTREGA) > 0 then
          'Atraso'
         When (vfa.data_da_emissao - cps.DATA_ENTREGA) = 0 then
          'Na Data'
         Else
          'Antecipado'
       END DESCR_ANALISE_ENTREGA,
       (SELECT TRIM(CEX.DESCRICAO)
          FROM COML_CONDICOESPAGAME CEX
         WHERE CEX.CONDICAO = nsa.idcondicaopagamento) DESCR_CONDICAO_PAGAMENTO,
       NVL((SELECT MAX(CEX.PRAZOMEDIO)
             FROM COML_CONDICOESPAGAME CEX
            WHERE CEX.CONDICAO = nsa.idcondicaopagamento),
           0) PRAZO_MEDIO_PAGTO,
       (NVL((SELECT MAX(CEX.Acrescimovinculado)
              FROM COML_CONDICOESPAGAME CEX
             WHERE CEX.CONDICAO = nsa.idcondicaopagamento),
            0)) CUSTO_FINANCEIRO,
       vfa.preco_unit +
       (vfa.preco_unit *
       DECODE(vfa.preco_unit,
               0,
               0,
               (NVL((SELECT MAX(CEX.Acrescimovinculado)
                      FROM COML_CONDICOESPAGAME CEX
                     WHERE CEX.CONDICAO = nsa.idcondicaopagamento),
                    0) / 100))) PRECO_UNIT_COM_CUSTO,
       (vfa.VALOR - vfa.valor_desconto +
       (vfa.VALOR - vfa.valor_desconto) *
       DECODE((vfa.VALOR - vfa.valor_desconto),
               0,
               0,
               (NVL((SELECT MAX(CEX.Acrescimovinculado)
                      FROM COML_CONDICOESPAGAME CEX
                     WHERE CEX.CONDICAO = nsa.idcondicaopagamento),
                    0) / 100))) VALOR_COM_CUSTO,
       (DECODE(CPS.PRECOLISTA,
               0,
               0,
               (((vfa.preco_unit * 100) / CPS.PRECOLISTA)) - 100) * -1) PERC_DESCONTO,
       CPS.CD_SUBTIPOPED,
       (select TRIM(max(CST.DS_SUBTIPOPED))
          from COML_SUBTIPOPED CST
         where CST.CD_SUBTIPOPED = CPS.CD_SUBTIPOPED) DESCR_SUB_TIPO_PEDIDO,
       CPS.TIPOPEDIDO,
       (select Trim(ctp.descricao)
          from coml_tipospedidos ctp
         where ctp.tipopedido = cps.tipopedido) descr_tipopedido,
       cps.quantidade QUANT_PEDIDO,
       DECODE(cps.estoque, 1, 'SIM', 'NÃO') PRONTA_ENTREGA,
       cv.CANAL_VENDA as CANAL_VENDAS,
       trim(cv.DESCRICAO) as DESCR_CANAL_VENDAS,
       CAST(PKGBASI0001.FNC_MONTA_MASCARA(ITE.CODIGO,
                                          (SELECT B.EDMASCARA
                                             FROM MASCARA_TIPO_INSUMO a,
                                                  MASCARAS            B
                                            where a.idmascaratipoinsumo =
                                                  ITE.IDMASCARATIPOINSUMO
                                              and b.idmascara = a.idmascara)) AS
            VARCHAR2(200)) CODIND,
       Case
         When ite.tipo_item = 10 then
          CAST(trim(PKGBASI0001.FNC_MONTA_MASCARA(ITE.CODIGO_COMERCIAL,
                                                  (SELECT M.EDMASCARA
                                                     FROM MASCARAS M
                                                    WHERE M.TIPO_MASCARA = 16))) AS
               VARCHAR2(200))
         Else
          trim(ITE.Codigo_Comercial)
       End CODCOM,
       trim(ITE.CODIGO_COMERCIAL) CODIGO_COMERCIAL,
       trim(ITE.CODIGO_ALTERNATIVO) CODIGO_ALTERNATIVO,
       Case
         When ite.tipo_item = 9 then
          (SELECT VMA.ARTIGO
             FROM VW_BAS_MASCARAPRODUTOCRU VMA
            WHERE VMA.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO)
         When ite.tipo_item = 10 then
          (SELECT VMA.ARTIGO
             FROM /*VW_BAS_MASCARAPRODUTOACABADO -- Alex - Melhorias de performance*/ BD_BAS_MASCPRODACAB VMA
            WHERE VMA.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO)
         Else
          ite.codigo
       End ARTIGO,
       Case
         When ite.tipo_item in (9, 10) and
              (select max(cri.serie)
                 from cristal cri
                where cri.senha_mestra = 1) <> 73 then
          (SELECT trim(EAR.DSITEMARTIGOCRU)
             FROM ENGEITEMESTOARTCRU EAC, ENGEITEMARTIGOCRU EAR
            WHERE EAR.CDITEMARTIGOCRU = EAC.CDARTIGOCRU
              AND EAC.CDREDUZIDO = ITE.CODIGO_REDUZIDO)
         Else
          trim(ite.descricao)
       End DESCR_ARTIGO,
       (SELECT TRIM(COR.CDCOR)
          FROM ENGEITEMESTOCOR COR
         WHERE COR.CDREDUZIDO = ITE.CODIGO_REDUZIDO) COR,
       (SELECT TRIM(COR.DESCRICAO)
          FROM ENGEITEMESTOCOR COX, COR
         WHERE COR.CODIGO_COR = COX.CDCOR
           AND ITE.CODIGO_REDUZIDO = COX.CDREDUZIDO) DESCR_COR,
       (SELECT TRIM(DES.CDDESENHO)
          FROM ENGEITEMESTODESENHO DES
         WHERE DES.CDREDUZIDO = ITE.CODIGO_REDUZIDO) DESENHO,
       (SELECT TRIM(VDE.CDVARIANTE)
          FROM ENGEITEMESTOVARDESEN VDE
         WHERE VDE.CDREDUZIDO = ITE.CODIGO_REDUZIDO) VARIANTE,
       (select trim(lpr.descricaolinha)
          from linha_produto lpr
         where lpr.codigolinha = ite.linha_produto) DESCR_LINHA_PRODUTO,
       (select trim(lpc.decricao)
          from linhaprodutocomercia lpc
         where lpc.linhaprodutocomercia = ite.linhaprodutocomercia) DESCR_LINHA_PROD_COMERCIAL,
       pns.idnatuoper ID_natop,
       vfa.natop,
       vfa.natop_seq,
       trim(nat.DESCOPERACAO) DESCR_NATUREZA_OPERACAO,
       DECODE(trim(nat.entrada), 1, 1, 0) NATOP_OPERACAO,
       DECODE(trim(nat.entrada), 1, 'ENTRADA', 'SAIDA') DESCR_NATOP_OPERACAO,
       (select gic.cdsefaz
          from geraitemcomprado gic
         where gic.id = nat.itemcomprado) ||
       (select lpad(tcs.cdsitutrib, 2, '0')
          from tsitutribimpo tcs
         where tcs.id = nat.idsitutribicms) CST_ICMS,
       vfa.numero_romaneio,
     (SELECT COUNT(GPEC.IDPECASPRODUTO)
          FROM GERAPECAROMSAIDA GPEC, GERAPECASPRODUTO GPP
         WHERE GPP.IDPECASPRODUTO=GPEC.IDPECASPRODUTO
         AND   GPEC.NUMERO_ROMANEIO_SAID = vfa.NUMERO_ROMANEIO
         AND   GPP.CODIGO_REDUZIDO_PROD=pns.cdreduzido) NRO_PECAS,
       pro.pesobruto PESO_BRUTO,
       trim(vfa.descricao_1) DESCRICAO_1,
       trim(ITE.CODIGO) codigo,
       vfa.qualidade_comercial QC,
       vfa.COMPL AUX1,
       cASE
         When vfa.COMPL > 0 then
          (vfa.COMPL - vfa.COMPL1) * vfa.comissao / 100
         else
          0
       END AUX2,
       vfa.COMPL1 AUX3,
       decode(to_number(vfa.GERACONTASRECEBER),
              0,
              'NÃO',
              'SIM') CONTAS_A_RECEBER,
       (select trim(MAX(ffx.dspontofaturamento))
          from fatupontfatu ffx
         where ffx.cdpontofaturamento = vfa.cdpontofaturamento
           and ffx.cdfilial = vfa.filialnota) DESCR_PONTO_FATURAMENTO,
       (SELECT trim(vgi.DESCR_GRUPO_ITEM)
          FROM VW_F7_GRUPO_ITEM vgi
         where vgi.IDGI = mti.idgrupoitem) DESCR_GRUPO_ITEM,
       ITE.LINHAPRODUTOCOMERCIA LINHA_PROD_COMERCIAL,
       case
         when (ite.tipo_item) in (9, 10) then
          'Malha/Tecido'
         else
          (select trim(vti.DESCRICAO)
             from vw_enu_tipo_item vti
            where vti.TIPO_ITEM = ite.tipo_item)
       end DESCR_TIPO_PRODUTO,
       (SELECT TRIM(CFI.CODCLASFISCAL)
          FROM CODIGO_FISCAL CFI
         WHERE cfi.idclasfiscal = pns.idclasfiscal) CLASSIF_FISCAL,
       (SELECT TRIM(CFI.DESCRICAO)
          FROM CODIGO_FISCAL CFI
         WHERE cfi.idclasfiscal = pns.idclasfiscal) DESCR_CLASSIF_FISCAL,
       'ONLINE' DESCR_TIPO_BUSCA,
       to_number(to_char(nsa.dtemissao, 'rrrr')) ANO,
       to_number(to_char(nsa.dtemissao, 'mm')) MES,
       to_char(nsa.dtemissao, 'rrrrmm') ANO_MES,
       TRIM(ite.idmascaratipoinsumo) TIPO,
       TRIM(ite.idmascaratipoinsumo) IDMASCARA,
       MTI.IDGRUPOITEM IDGI,
       to_number(vfa.GERACONTASRECEBER) GERACONTASRECEBER ,
       vfa.idunidademedida,
       vfa.tpunidademedida,
       ITE.LINHA_PRODUTO,
       vfa.cdpontofaturamento,
       nsa.idpessoafj IDCLIENTE,
        CGT.IDGRUPO idGRP_CLIENTE_tec,
         cASE
            WHEN CGT.IDGRUPO IS NOT NULL THEN
           (SELECT TRIM(Cg.DESCRICAO) FROM COML_GRUPO_TEC CG WHERE CG.ID = CGT.IDGRUPO)
       ELSE null
       END DESCR_GRUPO_CLIENTE_TEC,
       TCL.IDGRUPOEMPADM,
       (SELECT TRIM(IG.NOMEGRUPO) FROM int_grupoempresa IG WHERE IG.ID = TCL.IDGRUPOEMPADM) DESCR_GRUPO_EMPRESA_ADM,
       (select trim(seg.descricao) from coml_segmentomercado seg, tcliente tcl
         where tcl.idpessoafj = nsa.idpessoafj
         and seg.segmento = tcl.segmento) descr_segmento,
       vfa.REPRESENTANTE IDREPRESENTANTE,
       ite.tipo_item,
       vfa.tipo_operacao,
       vfa.tiopernatureza,
       nvl(nsa.idcondicaopagamento, 0) COND_PAGTO,
       decode(ITE.TIPO_ITEM,
              10,
              (select max(trim(tvr.descricao))
                 from engeitemestovardesen eid,
                      variante_desenho     vde,
                      tiposvariante        tvr
                where eid.cdreduzido = VFA.codigo_reduzido
                  and trim(vde.codigo_desenho) = trim(eid.cddesenho)
                  and trim(vde.codigo_variante) = trim(eid.cdvariante)
                  and tvr.idtipovariante = vde.idtipovariante),
              '') descr_tipo_variante,
       NSA.STPRODUTOFATURAMENTO,
       decode(nsa.stprodutofaturamento,
              0,
              'Nenhum',
              1,
              'Expedida',
              2,
              'Expedida Porto Aduaneiro',
              3,
              'Embarcada Exportação') DESCR_STPRODFATUR,
       nsa.stnotafaturamento STATUS_NF,
       (SELECT VS.DESCRICAO
          FROM vw_enu_STATUS_NFS vs
         where vs.STATUS = nsa.stnotafaturamento) DESCR_STATUS_NF,
       (select trim(max(fex.descricao))
          from familia_estoque fex
         where fex.familia_estoque = Ite.familia_estoque) DESCR_FAMILIA_ESTOQUE,
       TRIM(ite.familia_estoque) FAMILIA_ESTOQUE,
       nsa.tpdocumento,
       (SELECT TRIM(TD.DESCRICAO)
          FROM vw_enu_TIPO_DOC_NF TD
         WHERE TD.TPDOCUMENTO = NSA.TPDOCUMENTO) DESCR_TIPO_DOC_NF,
       trim(gba.dsbasealiq) DESCR_BASE_ALIQ_ICMS,
       1 tipo_busca,
       nsa.dtmanidest,
       nsa.idtransportadora,
       (select trim(trans.nome)
          from transportadoras trans
         where trans.idtransportadora = nsa.idtransportadora) transportadora,

       --Eduardo Vicente - Início - 08/08/2023 - TR 209133 - MAS-View: W_PI_CFATC01_FAT
       --Foi solicitado pela Alpina para adicionar nesta View as informações abaixo
       NSA.IDREDESPACHO,
       (select trim(trans.nome)
          from transportadoras trans
          where trans.idtransportadora = nsa.idredespacho) transportadora_redespacho,
       --Eduardo Vicente - Fim - 08/08/2023 - TR 209133 - MAS-View: W_PI_CFATC01_FAT

       CAST((SELECT OPTSTRAGGR(DISTINCT TRIM(GPP.LOTE_PRODUTO))
               FROM GERAREQUESTOITEMNOTA GQI,
                    PRODUTO_ROMANEIO     PRO,
                    PECAS_ROMANEIO_SAIDA PRS,
                    GERAPECASPRODUTO     GPP
              WHERE PRO.IDPRODUTO_ROMANEIO = GQI.IDPRODUTO_ROMANEIO
                AND PRS.IDPRODUTO_ROMANEIO = PRO.IDPRODUTO_ROMANEIO
                AND GPP.IDPECASPRODUTO = PRS.IDPECASPRODUTO
                AND GQI.IDNOTAFISCALITENS = PNS.ID) AS VARCHAR2(150)) LOTES_PRODUTO,
       nsa.id idnotafiscalcapa,
       nfc.nrcoletatrans numero_transporte_coleta,
       nfc.cdreduusuario codigo_usuario_coleta,
       (select trim(c.usuario)
          from cristal c
         where c.codredusuario = nfc.cdreduusuario) nome_usuario_coleta,
       nfc.dtcontatocoleta data_contato_coleta,
       nfc.nomecontatotrans nome_contato_transporte_coleta,
       nfc.dtcoletaprevista data_prevista_coleta,
       nfc.dsformacontato descr_forma_contato_coleta,
       r.idreferencia referencia,
       (SELECT TDI.NRDOCUIMPO
          FROM NOTAFISCALITENSDCIMP IDI, TDECIMPORTACAO TDI
         WHERE IDI.IDNOTAFISCALITENS = PNS.ID
           AND TDI.ID = IDI.IDDECIMPORTACAO) DOC_IMPORT,
       nat.tilocaloperacao,
       (select trim(vlo.DESCRICAO)
          from vw_enu_local_operacao vlo
         where vlo.tilocaloperacao = nat.tilocaloperacao) DESCR_LOCAL_OPERACAO,
       trim(r.descricao) descr_referencia,
       ffe.tifinaemisnfs FINALIDADE_EMISSAO_NF,
       (select TRIM(eni.description)
         from xx2_enumerates enu, xx2_enumitem eni
        where enu.name like 'TFINALIDADEEMISSAONFS%'
          and eni.idenumerate = enu.id
          AND eni.sequence = ffe.tifinaemisnfs) DESCR_FINALIDADE_EMISSAO_NF,
       case
         when CPS.grupoinsupedido = 0 then
           CPS.itempedido
       Else
         CPS.grupoinsupedido
       end grupoinsupedido,
       VFA.UNID_NEGOCIO,
       (SELECT TRIM(CUN.NMUNIDADENEGOCIO)
           FROM CUSTUNIDADENEGOCIO CUN
          WHERE CUN.IDUNIDADENEGOCIO = VFA.UNID_NEGOCIO) DESCR_UNID_NEGOCIO,
       vfa.idproduto_romaneio,
        (select TRIM(CTE.DESCRICAO) from COML_EMPRESAS CE, COML_TIPOSEMPRESA CTE
       WHERE CE.EMPRESA = PFJ.EMPRESA AND CTE.TIPOEMPRESA = CE.TIPOEMPRESA) DESCR_TIPO_EMPRESA,
       pro.tiitemprodrom,
                    ( select MAX(eni.description)
              from xx2_enumerates enu, xx2_enumitem eni
              where enu.name like  'TTIPOITEMPRODROM%'
              and eni.idenumerate = enu.id
              and eni.sequence = pro.tiitemprodrom) DESCR_TIPO_ITEM_PROD_ROM,
       pns.tiitensfatu,
        (select trim(ctf.descricao)
        from coml_tiposfrete ctf
        where ctf.tipofrete = nsa.idtipofrete) DESCR_TIPO_FRETE -- Amanda Victória - 10/09/2025 - Princesa - Tr. 241790 - Adicionar coluna para descrição do tipo frete
  from notafiscalcapa   nsa,
       notafiscalitens  pns,
       notafiscalcoleta nfc,
       ITENS_ESTOQUE ITE,
       (select MTIx.Idmascaratipoinsumo, MTIx.Dsprimeironivemascar, MTIx.Idgrupoitem,
       (select cri.serie from cristal cri where cri.codredusuario = 0) SERIE
         from MASCARA_TIPO_INSUMO MTIx
           ) MTI,
       (select ipcx.pedido,
               ipcx.itempedido,
               ipcx.grupoinsupedido,
               ipcx.quantidade,
               decode(ipcx.estoque, 'N', 0, 1) ESTOQUE,
               PCO.PEDIDOCLIENTE,
               PCO.CD_SUBTIPOPED,
               PCO.TIPOPEDIDO,
               pco.idfilialresponsavel,
               IPCx.PRECOLISTA,
               PCO.TABELAPRECO,
               PKGUTIL0001.FNC_CNVDATA(IPCx.DTEMISSAO,null) DATA_EMISSAO,
               PKGUTIL0001.FNC_CNVDATA(IPCx.EXPEDIREM,null) DATA_ENTREGA
          from pedidocomercial      pco,
               itenspedidocomercial ipcX,
               itenspedidodatas     ipdX
         where ipdX.pedido = ipcX.pedido
           and ipdX.itempedido = ipcX.itempedido
           and ipcx.pedido = pco.pedido) cps,
       PESSOASFJ PFJ,
       COML_GRUPO_TEC_CLI CGT,
       PESSOASFJ PFJ1,
       natureza_operacao nat,
       produto_romaneio pro,
       gerabasealiq gba,
       referencias r,
       suprtipoopernatureza ston,
       fatufinaemis ffe,
       BD_FAT_FATURAMENTO vfa,
       TCLIENTE TCL,
       CANAIS_VENDA cv
 WHERE ite.codigo_reduzido = VFA.CODIGO_REDUZIDO
   and pfj.idbasealiqapli = gba.id(+)
   AND MTI.IDMASCARATIPOINSUMO = ITE.IDMASCARATIPOINSUMO
   and pns.idnotafiscalcapa = nsa.id
   and vfa.idpns = pns.id
   and cps.pedido(+) = vfa.pedido
   and cps.itempedido(+) = vfa.item_pedido
   and pro.idproduto_romaneio = vfa.idproduto_romaneio
   and pfj.idpessoafj = nsa.idpessoafj
   AND PFJ1.IDPESSOAFJ = NVL(cps.idfilialresponsavel, nsa.idpessoafj)
   and nat.idnaturezaoperacao = pns.idnatuoper
   and nsa.id = nfc.idnotafiscalcapa(+)
   and iTe.identificacao = r.referencia(+)
   and nat.tipooperacao = ston.id
   and ston.idfinaemis = ffe.id
   AND CGT.IDPESSOASFJ (+) = NSA.IDPESSOAFJ
   AND TCL.IDPESSOAFJ (+) = NSA.IDPESSOAFJ
   and nvl(vfa.CANAL_VENDAS, 0) = cv.CANAL_VENDA(+)
   /* 0 - Faturavel - William Mello - 13/06/2023 - Leão & Jetex - Mostrar apenas itens da capa que são faturaveis - TR 210109 */
   AND pns.tiitensfatu = 0

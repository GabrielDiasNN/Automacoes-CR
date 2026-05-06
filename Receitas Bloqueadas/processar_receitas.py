# -*- coding: utf-8 -*-
# {
#   "version": "2.1.1",
#   "skill": "python-oracle-migration",
#   "description": "Processa Receitas Bloqueadas com Controle de Estado, Realce Visual e Excel Profissional"
# }
import os
import sys
import base64
import oracledb
import pandas as pd
import json
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from dotenv import load_dotenv

# Carregar ambiente (.env) do projeto raiz
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    raw_msg = f"[{ts}] [PY-PROCESS] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def get_sql() -> str:
    return """
        WITH 
        CTE_TEMPOS AS (
            SELECT 
                UPO.NUMEROORDEMREAL AS NR_OB,
                MAX(UNP.DTTEMPOINICIAL) AS INICIO_TING,
                MAX(UNP.DTTEMPOFINAL) AS FINAL_TING,
                MAX(SUBSTR(UNP.NUMERO_MAQUINA, 7, 4)) AS MQ_TING
            FROM SGTPRD.UP_ORDEM_MVTO UPO
            INNER JOIN SGTPRD.UNIDADE_PROGRAMACAO UNP ON UPO.NUMEROUP = UNP.NUMEROUP
            WHERE UNP.TIPO_MAQUINA = 19 
              AND UNP.EXCLUIDA = 0 
              AND UNP.TIPOUP = 0
              AND UNP.DTTEMPOFINAL >= TRUNC(SYSDATE)
            GROUP BY UPO.NUMEROORDEMREAL
        ),
        CTE_GRAFICO AS (
            SELECT IDLCRIR_PRD, MAX(GRAFICO) AS GRAFICO
            FROM SGTPRD.VW_LAC_RECPRD_RECLAB
            GROUP BY IDLCRIR_PRD
        ),
        CTE_DADOS AS (
            SELECT 
                OBFX.CODIGO_GRUPO AS GRUPO,
                OBFX.NUMERO_OB AS NR_OB,
                TRIM(OBFX.CODIGO_COR_DESENHO) AS COR_OB,
                TRIM(SUBSTR(CREX.CODCOR, 1, 11)) AS COR_REC,
                OBFX.ESPECIFICACAO_PRODUT AS EP_OB,
                CREX.ESPECIFICACAO_PRODUT AS EP_REC,
                OBFX.PROCESSO_ESPECIFICO AS PE_OB,
                CREX.PROCESSO_ESPECIFICO AS PE_REC,
                T.MQ_TING,
                T.INICIO_TING,
                T.FINAL_TING,
                GR.GRAFICO,
                DECODE(LCR.DATA_ULTIMA_PRODUC, 0, TO_DATE('1899-12-31','YYYY-MM-DD'), 
                       TO_DATE(LCR.DATA_ULTIMA_PRODUC,'YYYYMMDD')) AS DATA_ULT_PROD,
                CREX.CODIGO_CLASSIFICACAO AS CD_CLASSIF,
                UPPER(TRIM(CLF.DESCRICAO)) AS CLASSIF_COR,
                LCR.CODIGO_REDUZIDO_RECE AS CODIGO_REDUZIDO_RECE,
                UPPER(LRB.USUARIO_BLOQUEIO) AS USUARIO_BLOQUEIO,
                TO_DATE(LRB.DATA_BLOQUEIO, 'YYYY/MM/DD') AS DATA_BLOQUEIO,
                TO_DATE(LCR.DATA_ALTERACAO, 'YYYY/MM/DD') AS DATA_ALTERACAO,
                LCR.USUARIO_ALTEROU,
                UPPER(TRIM(VSU.NOME)) AS NOME_USUARIO_ALTEROU,
                CASE 
                    WHEN OBFX.PROCESSO_ESPECIFICO IS NULL OR CREX.PROCESSO_ESPECIFICO IS NULL THEN 'Indefinido'
                    WHEN OBFX.PROCESSO_ESPECIFICO = CREX.PROCESSO_ESPECIFICO THEN 'OK'
                    ELSE 'Divergente'
                END AS STATUS_PE
            FROM CTE_TEMPOS T
            INNER JOIN SGTPRD.UP_ORDEM_MVTO UPO ON UPO.NUMEROORDEMREAL = T.NR_OB
            INNER JOIN SGTPRD.OB_FASES OBFX ON OBFX.NUMERO_OB = T.NR_OB
            INNER JOIN SGTPRD.OB OB ON OBFX.NUMERO_OB = OB.NUMERO_OB
            LEFT JOIN SGTPRD.CADASTRO_RECEITAS CREX 
                ON CREX.PROCESSOINDUSTRIAL = (OBFX.CODIGO_FASE || OBFX.TIPO_PROCESSO)
                AND SUBSTR(CREX.CODCOR, 1, 11) = OBFX.CODIGO_COR_DESENHO
                AND CREX.ESPECIFICACAO_PRODUT = OBFX.ESPECIFICACAO_PRODUT
                AND CREX.PROCESSO_ATIVO_PRODU = 1
            LEFT JOIN SGTPRD.LIGA_CADREC_ITEMREC LCR ON LCR.CODIGO_REDUZIDO_RECE = CREX.CODIGO_REDUZIDO_RECE
            LEFT JOIN CTE_GRAFICO GR ON GR.IDLCRIR_PRD = LCR.ID_LIGA_CADREC_ITEMR
            LEFT JOIN SGTPRD.CLASSIFICACAO_COR CLF ON CLF.CODIGO_CLASSIFICACAO = CREX.CODIGO_CLASSIFICACAO
            INNER JOIN SGTPRD.LABRECEITA_BLOQUEADA LRB ON LRB.ID_LABRECEITA_BLOQ = LCR.ID_LABRECEITA_BLOQ
            LEFT JOIN SGTPRD.VW_SIS_SENHA_USUARIO VSU ON VSU.CODREDUSUARIO = LCR.USUARIO_ALTEROU
            WHERE OB.STATUS <> 0
              AND OBFX.CODIGO_FASE = 40
              AND OBFX.STATUS = 0
              AND LRB.BLOQUEIO_RECEITA = 0
        )
        SELECT * FROM CTE_DADOS
        ORDER BY INICIO_TING ASC, NR_OB ASC, GRUPO ASC
    """

def gerar_html_artistico(df_atual: pd.DataFrame, df_diff: pd.DataFrame, stats: dict) -> str:
    # Cores Classicas
    cor_header = "#0f4c81"
    cor_header_text = "#ffffff"
    cor_sub_header = "#e8f1ff"
    cor_table_header = "#e5eef8"
    cor_table_border = "#cbd5e1"
    
    # Cores de Status
    cor_mod_bg = "#fef9c3"   # Amarelo suave para alteradas
    cor_del_bg = "#f1f5f9"   # Cinza muito claro para liberadas
    
    # Textos ASCII-Safe
    rel_title = "Relat\u00f3rio de Receitas Bloqueadas"
    ciclo_resumo = "Resumo do Ciclo:"
    col_cor = "Cor Rec."
    col_ult_prod = "Data \u00daltima Prod."
    col_bloqueio = "Data Bloqueio"
    col_status = "Status / Mudan\u00e7a"
    txt_intro = "Abaixo, as altera\u00e7\u00f5es detectadas desde o \u00faltimo processamento:"
    txt_footer_ob = "Favor consultar a planilha em anexo para o detalhamento t\u00e9cnico completo por Ordem de Beneficiamento (OB)."
    txt_footer_auto = "Mensagem autom\u00e1tica."
    txt_warning = "Por favor, atualizar os status com as previs\u00f5es de liberar cada receita."

    html = f"""
    <div style="font-family:'Segoe UI', Calibri, Arial, sans-serif; font-size:11pt; color:#1f2937; line-height:1.5;">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width:1100px; border-collapse:collapse; border:1px solid #d1d5db;">
            <thead>
                <tr>
                    <th colspan="6" style="background-color:{cor_header}; color:{cor_header_text}; padding:18px; text-align:center;">
                        <div style="font-size:17pt; font-weight:bold; margin-bottom:5px;">{rel_title}</div>
                        <div style="font-size:10.5pt; font-weight:normal; color:{cor_sub_header};">
                            Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}
                        </div>
                    </th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="padding:16px;">
                        <div style="margin-bottom:20px; padding:12px; background-color:#f8fafc; border-left:4px solid {cor_header}; border-radius:4px;">
                            <b style="color:{cor_header}; font-size:12pt;">{ciclo_resumo}</b><br>
                            <table cellspacing="5" cellpadding="0" style="margin-top:5px; font-size:10.5pt;">
                                <tr>
                                    <td><span style="display:inline-block; width:12px; height:12px; background-color:#ffffff; border:1px solid {cor_table_border};"></span> Novas: <b>{stats['new']}</b></td>
                                    <td style="padding-left:20px;"><span style="display:inline-block; width:12px; height:12px; background-color:{cor_mod_bg}; border:1px solid #fef08a;"></span> Alteradas: <b>{stats['mod']}</b></td>
                                    <td style="padding-left:20px;"><span style="display:inline-block; width:12px; height:12px; background-color:{cor_del_bg}; border:1px solid {cor_table_border};"></span> Liberadas: <b>{stats['del']}</b></td>
                                </tr>
                            </table>
                        </div>
                        <p style="margin-bottom:10px;">{txt_intro}</p>
                        <table cellspacing="0" cellpadding="6" border="1" width="100%" style="border-collapse:collapse; border:1px solid {cor_table_border}; font-size:10pt;">
                            <thead>
                                <tr style="background-color:{cor_table_header};">
                                    <th style="border:1px solid {cor_table_border};">{col_cor}</th>
                                    <th style="border:1px solid {cor_table_border};">EP Rec.</th>
                                    <th style="border:1px solid {cor_table_border};">PE Rec</th>
                                    <th style="border:1px solid {cor_table_border};">{col_ult_prod}</th>
                                    <th style="border:1px solid {cor_table_border};">{col_bloqueio}</th>
                                    <th style="border:1px solid {cor_table_border};">{col_status}</th>
                                </tr>
                            </thead>
                            <tbody>
    """
    for _, row in df_diff.iterrows():
        change_type = row['_change_type']
        bg = "#ffffff"
        status_text = ""
        font_style = "normal"
        if change_type == 'NEW':
            status_text = "\u2728 NOVO BLOQUEIO"
        elif change_type == 'MODIFIED':
            bg = cor_mod_bg
            status_text = "\u26a0 DATA ALTERADA"
        elif change_type == 'DELETED':
            bg = cor_del_bg
            status_text = "<b style='color:#059669;'>\u2705 LIBERADA</b>"
            font_style = "italic"
            
        html += f"""
                                <tr style="background-color:{bg}; font-style:{font_style};">
                                    <td style="border:1px solid {cor_table_border}; text-align:center; font-weight:bold;">{row['Cor Rec.']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['EP Rec.']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['PE Rec']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['Data \u00daltima Prod.']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['Data Bloqueio']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center; font-size:9pt; font-weight:bold;">{status_text}</td>
                                </tr>
        """
    html += f"""
                            </tbody>
                        </table>
                        <p style="margin-top:15px; color:#b91c1c; font-weight:bold;">{txt_warning}</p>
                    </td>
                </tr>
            </tbody>
        </table>
        <p style="margin-top:20px; font-size:10pt; color:#64748b;">
            {txt_footer_ob}<br>
            <span style="font-size:8.5pt; color:#cbd5e1;">{txt_footer_auto}</span>
        </p>
    </div>
    """
    return html

def formatar_excel(file_path: str) -> None:
    wb = load_workbook(file_path)
    header_fill = PatternFill(start_color="0F4C81", end_color="0F4C81", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    status_err_fill = PatternFill(start_color="FECACA", end_color="FECACA", fill_type="solid")
    center_align = Alignment(horizontal='center', vertical='center')
    border = Border(left=Side(style='thin', color='CBD5E1'), right=Side(style='thin', color='CBD5E1'), 
                    top=Side(style='thin', color='CBD5E1'), bottom=Side(style='thin', color='CBD5E1'))

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = header_fill; cell.font = header_font; cell.alignment = center_align; cell.border = border

        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.border = border
                if isinstance(cell.value, datetime):
                    cell.number_format = 'DD/MM/YYYY HH:MM:SS'
                elif sheet_name == 'OBsReceitasBloqueadas':
                    if cell.column in [11, 12, 15, 18, 19, 20]: cell.number_format = 'DD/MM/YYYY'
                if sheet_name == 'OBsReceitasBloqueadas':
                    if ws.cell(row=cell.row, column=22).value == "Divergente":
                        ws.cell(row=cell.row, column=22).fill = status_err_fill
                    ws.cell(row=cell.row, column=2).font = Font(bold=True)
        for col in ws.columns:
            max_length = 0; column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
                except: pass
            ws.column_dimensions[column].width = (max_length + 2)
    wb.save(file_path)

def process() -> None:
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"
    log("Iniciando processo V2 de Receitas Bloqueadas (Controle de Estado)", "INFO", exec_id)
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    dsn = "dbprd" 
    client_lib = os.environ.get("ORACLE_CLIENT_PATH")
    tns_admin = os.environ.get("TNS_ADMIN")

    if not client_lib or not tns_admin:
        log("Caminhos Oracle ausentes no ambiente.", "ERROR", exec_id); sys.exit(1)

    try:
        oracledb.init_oracle_client(lib_dir=client_lib, config_dir=tns_admin)
        log("Oracle Thick Mode ativado.", "INFO", exec_id)
    except Exception as e: log(f"Aviso Thick client: {e}", "WARN", exec_id)

    connection = None
    try:
        connection = oracledb.connect(user=user, password=password, dsn=dsn)
        sql_query = f"SELECT GRUPO, NR_OB, COR_OB, COR_REC, EP_OB, EP_REC, PE_OB, PE_REC, MQ_TING, INICIO_TING, FINAL_TING, GRAFICO, DATA_ULT_PROD, CD_CLASSIF, CLASSIF_COR, CODIGO_REDUZIDO_RECE, USUARIO_BLOQUEIO, DATA_BLOQUEIO, DATA_ALTERACAO, USUARIO_ALTEROU, NOME_USUARIO_ALTEROU, STATUS_PE FROM ({get_sql()})"
        df_raw = pd.read_sql(sql_query, con=connection)
        df_raw = df_raw.rename(columns={"COR_REC": "Cor Rec.", "EP_REC": "EP Rec.", "PE_REC": "PE Rec", "DATA_ULT_PROD": "Data \u00daltima Prod.", "DATA_BLOQUEIO": "Data Bloqueio"})
        for col in ["Data \u00daltima Prod.", "Data Bloqueio"]:
            df_raw[col] = pd.to_datetime(df_raw[col], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')

        cols_agreg = ["Cor Rec.", "EP Rec.", "PE Rec", "Data \u00daltima Prod.", "Data Bloqueio"]
        df_agreg = df_raw[cols_agreg].drop_duplicates().sort_values(by=["Cor Rec.", "EP Rec."])
        df_agreg["Key"] = df_agreg["Cor Rec."].astype(str) + "_" + df_agreg["EP Rec."].astype(str) + "_" + df_agreg["PE Rec"].astype(str)

        state_path = os.path.join(os.path.dirname(__file__), "receitas_state.json")
        last_state_data = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f: last_state_data = json.load(f)
            except: last_state_data = {}
        
        last_records = last_state_data.get("records", []) if isinstance(last_state_data, dict) else last_state_data
        df_last = pd.DataFrame(last_records)
        diff_rows = []; stats = {'new': 0, 'mod': 0, 'del': 0}
        
        for _, row in df_agreg.iterrows():
            if df_last.empty:
                row_diff = row.copy(); row_diff['_change_type'] = 'NEW'; diff_rows.append(row_diff); stats['new'] += 1
                continue
            match = df_last[df_last['Key'] == row['Key']] if 'Key' in df_last.columns else pd.DataFrame()
            if match.empty:
                row_diff = row.copy(); row_diff['_change_type'] = 'NEW'; diff_rows.append(row_diff); stats['new'] += 1
            elif (match.iloc[0]['Data \u00daltima Prod.'] != row['Data \u00daltima Prod.'] or match.iloc[0]['Data Bloqueio'] != row['Data Bloqueio']):
                row_diff = row.copy(); row_diff['_change_type'] = 'MODIFIED'; diff_rows.append(row_diff); stats['mod'] += 1
        
        if not df_last.empty:
            for _, row in df_last.iterrows():
                if df_agreg.empty or df_agreg[df_agreg['Key'] == row['Key']].empty:
                    row_diff = row.copy(); row_diff['_change_type'] = 'DELETED'; diff_rows.append(row_diff); stats['del'] += 1

        if not diff_rows:
            log("Sem alteracoes. Notificacao suprimida.", "INFO", exec_id)
            state_data = {"last_hash": pd.util.hash_pandas_object(df_agreg).sum().astype(str), "updated_at": datetime.now().isoformat(), "records": df_agreg.to_dict(orient='records')}
            with open(state_path, "w", encoding="utf-8") as f: json.dump(state_data, f, ensure_ascii=False, indent=4)
            sys.exit(0)

        state_data = {"last_hash": pd.util.hash_pandas_object(df_agreg).sum().astype(str), "updated_at": datetime.now().isoformat(), "records": df_agreg.to_dict(orient='records')}
        with open(state_path, "w", encoding="utf-8") as f: json.dump(state_data, f, ensure_ascii=False, indent=4)
        
        excel_path = os.path.join(os.path.dirname(__file__), "Receitas Bloqueadas.xlsx")
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df_agreg.drop(columns=['Key'], errors='ignore').to_excel(writer, sheet_name='ReceitasBloqueadas', index=False)
            df_raw.to_excel(writer, sheet_name='OBsReceitasBloqueadas', index=False)
        
        try: formatar_excel(excel_path); log("Excel formatado.", "INFO", exec_id)
        except Exception as e: log(f"Aviso Excel: {e}", "WARN", exec_id)
            
        html_content = gerar_html_artistico(df_agreg, pd.DataFrame(diff_rows), stats)
        with open(os.path.join(os.path.dirname(__file__), "email_body.html"), "w", encoding="utf-8") as f: f.write(html_content)
        log("Processo concluido.", "INFO", exec_id)

    except oracledb.DatabaseError as de:
        error_obj, = de.args; log(f"Erro DB: {error_obj.message}", "ERROR", exec_id); sys.exit(1)
    except Exception as e: log(f"Erro fatal: {str(e)}", "ERROR", exec_id); sys.exit(1)
    finally:
        if connection: connection.close()

if __name__ == "__main__": process()

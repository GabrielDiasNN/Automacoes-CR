# -*- coding: utf-8 -*-
# {
#   "version": "2.1.2",
#   "skill": "python-oracle-migration",
#   "description": "Processa Receitas Bloqueadas com Controle de Estado, Realce Visual, Excel Profissional e Resiliencia (Stamina)"
# }
import os
import sys
import base64
import oracledb
import pandas as pd
import json
import stamina
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

@stamina.retry(on=oracledb.DatabaseError, attempts=3)
def fetch_data_with_retry(user: str, password: str, dsn: str, sql_query: str, exec_id: str) -> pd.DataFrame:
    log("Estabelecendo conexao e extraindo dados...", "INFO", exec_id)
    with oracledb.connect(user=user, password=password, dsn=dsn) as connection:
        return pd.read_sql(sql_query, con=connection)

def gerar_html_artistico(df_display: pd.DataFrame, stats: dict) -> str:
    # Cores Classicas
    cor_header = "#0f4c81"
    cor_header_text = "#ffffff"
    cor_sub_header = "#e8f1ff"
    cor_table_header = "#e5eef8"
    cor_table_border = "#cbd5e1"
    
    # Cores de Status
    cor_new_bg = "#f0fdf4"   # Verde muito claro para novos
    cor_mod_bg = "#fef9c3"   # Amarelo suave para alteradas
    cor_del_bg = "#f1f5f9"   # Cinza muito claro para liberadas (riscado)
    
    # Textos ASCII-Safe
    rel_title = "Painel Geral de Receitas Bloqueadas"
    ciclo_resumo = "Resumo do Ciclo:"
    col_cor = "Cor Rec."
    col_ult_prod = "Data \u00daltima Prod."
    col_bloqueio = "Data Bloqueio"
    col_status = "Status / Mudan\u00e7a"
    txt_intro = "Abaixo, a listagem completa de receitas sob bloqueio com os destaques do ciclo:"
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
                                    <td><span style="display:inline-block; width:12px; height:12px; background-color:{cor_new_bg}; border:1px solid #bbf7d0;"></span> Novas: <b>{stats['new']}</b></td>
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
    
    # Ordenar: Liberadas no fim, o resto por Cor/EP
    df_display['_sort_order'] = df_display['_change_type'].apply(lambda x: 1 if x == 'DELETED' else 0)
    df_display = df_display.sort_values(by=['_sort_order', 'Cor Rec.', 'EP Rec.'])

    for _, row in df_display.iterrows():
        change_type = row['_change_type']
        bg = "#ffffff"
        status_text = ""
        font_style = "normal"
        text_decor = "none"
        
        if change_type == 'NEW':
            bg = cor_new_bg
            status_text = "\u2728 NOVO BLOQUEIO"
        elif change_type == 'MODIFIED':
            bg = cor_mod_bg
            status_text = "\u26a0 DATA ALTERADA"
        elif change_type == 'DELETED':
            bg = cor_del_bg
            status_text = "<b style='color:#059669;'>\u2705 LIBERADA</b>"
            font_style = "italic"
            text_decor = "line-through"
        else:
            status_text = "<span style='color:#94a3b8;'>BLOQUEIO MANTIDO</span>"
            
        html += f"""
                                <tr style="background-color:{bg}; font-style:{font_style}; text-decoration:{text_decor};">
                                    <td style="border:1px solid {cor_table_border}; text-align:center; font-weight:bold;">{row['Cor Rec.']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['EP Rec.']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['PE Rec']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['Data \u00daltima Prod.']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center;">{row['Data Bloqueio']}</td>
                                    <td style="border:1px solid {cor_table_border}; text-align:center; font-size:8.5pt; font-weight:bold;">{status_text}</td>
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
    
    # Limpar artefatos de execucoes anteriores para evitar disparos indevidos
    html_path = os.path.join(os.path.dirname(__file__), "email_body.html")
    if os.path.exists(html_path):
        os.remove(html_path)
        log("Artefato email_body.html antigo removido.", "DEBUG", exec_id)

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

    try:
        sql_path = os.path.join(os.path.dirname(__file__), "SQL-ReceitasBloqueadas.sql")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_query = f.read()

        df_raw = fetch_data_with_retry(user, password, dsn, sql_query, exec_id)
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
            log("Sem alteracoes relevantes detectadas no ciclo.", "INFO", exec_id)
            # Atualiza apenas o timestamp e o hash no arquivo de estado para manter sincronia
            state_data = {"last_hash": pd.util.hash_pandas_object(df_agreg).sum().astype(str), "updated_at": datetime.now().isoformat(), "records": df_agreg.to_dict(orient='records')}
            with open(state_path, "w", encoding="utf-8") as f: json.dump(state_data, f, ensure_ascii=False, indent=4)
            sys.exit(2) # Exit code 2 indica sucesso, mas sem necessidade de notificacao

        state_data = {"last_hash": pd.util.hash_pandas_object(df_agreg).sum().astype(str), "updated_at": datetime.now().isoformat(), "records": df_agreg.to_dict(orient='records')}
        with open(state_path, "w", encoding="utf-8") as f: json.dump(state_data, f, ensure_ascii=False, indent=4)
        
        excel_path = os.path.join(os.path.dirname(__file__), "Receitas Bloqueadas.xlsx")
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df_agreg.drop(columns=['Key'], errors='ignore').to_excel(writer, sheet_name='ReceitasBloqueadas', index=False)
            df_raw.to_excel(writer, sheet_name='OBsReceitasBloqueadas', index=False)
        
        try: formatar_excel(excel_path); log("Excel formatado.", "INFO", exec_id)
        except Exception as e: log(f"Aviso Excel: {e}", "WARN", exec_id)
            
        # Preparar DataFrame para exibicao unificada no HTML
        df_diff = pd.DataFrame(diff_rows)
        df_display = df_agreg.copy()
        df_display['_change_type'] = 'STABLE'
        
        # Mapear mudancas para o dataframe principal
        for _, row in df_diff.iterrows():
            if row['_change_type'] in ['NEW', 'MODIFIED']:
                df_display.loc[df_display['Key'] == row['Key'], '_change_type'] = row['_change_type']
        
        # Adicionar as liberadas (que nao estao mais no df_agreg)
        df_deleted = df_diff[df_diff['_change_type'] == 'DELETED']
        if not df_deleted.empty:
            df_display = pd.concat([df_display, df_deleted], ignore_index=True)

        html_content = gerar_html_artistico(df_display, stats)
        with open(html_path, "w", encoding="utf-8") as f: f.write(html_content)
        log("Processo concluido com alteracoes. Notificacao gerada.", "INFO", exec_id)
        sys.exit(0)

    except oracledb.DatabaseError as de:
        error_obj, = de.args; log(f"Erro DB: {error_obj.message}", "ERROR", exec_id); sys.exit(1)
    except Exception as e: log(f"Erro fatal: {str(e)}", "ERROR", exec_id); sys.exit(1)

if __name__ == "__main__": process()
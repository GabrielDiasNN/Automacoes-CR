# {
#   "version": "1.0.2",
#   "skill": "ai-native-development-standard",
#   "contract": "hybrid-fetch-logic",
#   "description": "Extrai dados do Excel (Logs isolados no stderr)",
#   "reliability": "Base64-Bridge-Logs"
# }
import os
import sys
import json
from openpyxl import load_workbook
from datetime import datetime
import base64

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

def log(message, level="INFO", exec_id="manual"):
    """Envia logs em Base64 para o stderr (Isolamento total)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    raw_msg = f"[{ts}] [PY-EXTRACT-XL] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def extract():
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(script_dir, "Legacy", "Validador_Notas_Montagem.xlsm")
    table_name = "VW_EXC_OB_PED_ROM_Faccao"

    if not os.path.exists(excel_path):
        log("Arquivo Excel nao encontrado: " + excel_path, "ERROR", exec_id)
        sys.exit(1)

    try:
        log("Abrindo workbook para leitura: " + excel_path, "INFO", exec_id)
        wb = load_workbook(excel_path, data_only=True)
        
        target_sheet = None
        target_table = None

        for sheet in wb.worksheets:
            if table_name in sheet.tables:
                target_sheet = sheet
                target_table = sheet.tables[table_name]
                break

        if not target_table:
            log("Tabela '" + table_name + "' nao encontrada.", "ERROR", exec_id)
            sys.exit(1)

        ref = target_table.ref
        rows = list(target_sheet[ref])
        
        header_cells = rows[0]
        headers = [str(cell.value).strip().upper() for cell in header_cells]
        
        data = []
        for row in rows[1:]:
            record = {}
            for i, cell in enumerate(row):
                val = cell.value
                col_name = headers[i]
                if isinstance(val, datetime): val = val.isoformat()
                elif isinstance(val, str): val = val.strip()
                record[col_name] = val
            data.append(record)

        # Saida estruturada via STDOUT - EXCLUSIVA PARA DADOS
        sys.stdout.write(json.dumps(data, ensure_ascii=False))
        sys.stdout.flush()
        log("Extracao hibrida concluida: " + str(len(data)) + " registros.", "INFO", exec_id)

    except Exception as e:
        log("Erro fatal: " + str(e), "ERROR", exec_id)
        sys.exit(1)

if __name__ == "__main__":
    extract()

import json
import os
import sys
import math
from datetime import datetime

def html_escape(text):
    if not text: return "&nbsp;"
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;') \
                   .replace('á', '&aacute;').replace('Á', '&Aacute;').replace('é', '&eacute;').replace('É', '&Eacute;') \
                   .replace('í', '&iacute;').replace('Í', '&Iacute;').replace('ó', '&oacute;').replace('Ó', '&Oacute;') \
                   .replace('ú', '&uacute;').replace('Ú', '&Uacute;').replace('ç', '&ccedil;').replace('Ç', '&Ccedil;') \
                   .replace('ã', '&atilde;').replace('Ã', '&Atilde;').replace('õ', '&otilde;').replace('Õ', '&Otilde;') \
                   .replace('ê', '&ecirc;').replace('Ê', '&Ecirc;').replace('â', '&acirc;').replace('Â', '&Acirc;')

def generate_html(exec_id):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, f"ReceitasEmitidas_shadow_{exec_id}.json")
    config_path = os.path.join(script_dir, "receitas_config.json")
    output_html = os.path.join(script_dir, f"email_body_shadow_{exec_id}.html")

    if not os.path.exists(json_path):
        print(f"[{datetime.now()}] [PY-HTML] [ERRO] JSON de dados não encontrado: {json_path}")
        return False

    # 1. Carregar Dados e Config
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if not data:
        print(f"[{datetime.now()}] [PY-HTML] [WARN] Nenhum dado para gerar relatório.")
        return False

    # 2. Agrupar Dados (Máquina -> Grupo -> OBs)
    # Ordenar dados brutos antes do agrupamento para garantir consistência
    # Ordem: INICIO_TING (asc), GRUPO (asc), NUMERO_OB (asc)
    data_sorted = sorted(data, key=lambda x: (
        x.get('INICIO_TING') or '9999-12-31', 
        str(x.get('GRUPO') or '0'), 
        str(x.get('NUMERO_OB') or '')
    ))

    machines = {}
    total_weight = 0
    max_machine_weight = 0
    recipe_count = 0

    for row in data_sorted:
        mq = str(row.get('MQ_TING') or 'SEM MAQ').strip()
        grupo = str(row.get('GRUPO') or '0').strip()
        ob = str(row.get('NUMERO_OB') or '')
        inicio = row.get('INICIO_TING') or ''
        
        if inicio and 'T' in inicio:
            try:
                dt = datetime.fromisoformat(inicio)
                inicio = dt.strftime('%d/%m/%Y %H:%M')
            except: pass

        if mq not in machines:
            machines[mq] = {"groups": {}, "weight": 1, "recipes": 0}
        
        if grupo not in machines[mq]["groups"]:
            machines[mq]["groups"][grupo] = []
            if grupo != '0':
                machines[mq]["weight"] += 1 # Peso visual do cabeçalho do grupo
                machines[mq]["recipes"] += 1 # O grupo (lote) conta como 1 receita

        machines[mq]["groups"][grupo].append({"ob": ob, "inicio": inicio})
        machines[mq]["weight"] += 1 # Cada linha de OB adiciona peso visual
        
        # Se for avulsa (Grupo 0), cada OB é uma receita (lote) individual
        if grupo == '0':
            machines[mq]["recipes"] += 1

    # Estatísticas para o Layout (Replicação BuildLayoutProfile do VBA)
    machine_count = len(machines)
    for mq in machines:
        total_weight += machines[mq]["weight"]
        recipe_count += machines[mq]["recipes"]
        if machines[mq]["weight"] > max_machine_weight:
            max_machine_weight = machines[mq]["weight"]

    # 3. Lógica de Layout Adaptativo (Portabilidade do VBA)
    volume_score = total_weight + (machine_count * 2.2) + max_machine_weight + (recipe_count / 3)
    
    compress_factor = 0
    if volume_score > 54:
        compress_factor = min(1.0, (volume_score - 54) / 72)

    column_count = 3 if (volume_score >= 72 or max_machine_weight >= 16 or machine_count >= 11) else 2
    
    container_width = 696 if column_count == 3 else 680
    column_gap = max(6, int(14 - (compress_factor * 8)))
    outer_pad = max(4, int(12 - (compress_factor * 6)))

    # Fontes (pt)
    title_font = max(10.5, 13.5 - (compress_factor * 2.7))
    meta_font = max(6.3, 8.4 - (compress_factor * 1.8))
    section_font = max(6.1, 8.4 - (compress_factor * 2.0))
    header_font = max(5.9, 7.9 - (compress_factor * 1.8))
    body_font = max(5.6, 7.8 - (compress_factor * 2.2))

    # Alturas de linha (px)
    title_line = max(13, int(title_font * 1.35))
    meta_line = max(9, int(meta_font * 1.35))
    section_line = max(9, int(section_font * 1.35))
    header_line = max(8, int(header_font * 1.35))
    body_line = max(8, int(body_font * 1.35))

    row_pad_y = max(1, int(4 - (compress_factor * 3)))
    row_pad_x = max(3, int(6 - (compress_factor * 3)))
    block_pad_y = max(3, int(6 - (compress_factor * 3)))
    spacer_height = max(2, int(6 - (compress_factor * 4)))

    usable_width = container_width - ((column_count - 1) * column_gap)
    column_width = usable_width // column_count
    ob_width = int(column_width * 0.47)
    inicio_width = column_width - ob_width

    # 4. Distribuição das Máquinas em Colunas (Equilíbrio de Carga)
    columns_html = ["" for _ in range(column_count)]
    columns_current_weight = [0 for _ in range(column_count)]

    # Ordenar máquinas para manter consistência (alfabética como no VBA Collection?)
    sorted_machines = sorted(machines.keys())

    for mq_name in sorted_machines:
        mq_data = machines[mq_name]
        
        # Encontrar a coluna mais vazia
        best_col = columns_current_weight.index(min(columns_current_weight))
        
        # Construir Bloco da Máquina
        html = f"""
        <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='{column_width}' style='width:{column_width}px;margin:0;page-break-inside:avoid;'>
            <tr>
                <td colspan='2' align='center' style='padding:{block_pad_y}px {row_pad_x}px;border:1px solid #000000;background-color:#E9EEF7;font-size:{section_font:.1f}pt;font-weight:bold;line-height:{section_line}px;text-align:center;'>
                    {html_escape(mq_name)} | {mq_data['recipes']} receita{'s' if mq_data['recipes'] != 1 else ''}
                </td>
            </tr>
        """
        
        sorted_groups = sorted(mq_data["groups"].keys())
        for g_name in sorted_groups:
            if g_name != '0':
                html += f"""
                <tr>
                    <td colspan='2' align='center' style='padding:{row_pad_y}px {row_pad_x}px;border-left:1px solid #000000;border-right:1px solid #000000;border-bottom:1px solid #D9D9D9;background-color:#F2F2F2;font-size:{header_font:.1f}pt;font-weight:bold;line-height:{header_line}px;text-align:center;'>
                        Grupo {html_escape(g_name)}
                    </td>
                </tr>
                """
            
            for item in mq_data["groups"][g_name]:
                html += f"""
                <tr>
                    <td width='{ob_width}' style='width:{ob_width}px;padding:{row_pad_y}px {row_pad_x}px;border-left:1px solid #000000;border-bottom:1px solid #D9D9D9;font-size:{body_font:.1f}pt;line-height:{body_line}px;color:#000000;white-space:nowrap;'>{html_escape(item['ob'])}</td>
                    <td width='{inicio_width}' align='center' style='width:{inicio_width}px;padding:{row_pad_y}px {row_pad_x}px;border-right:1px solid #000000;border-bottom:1px solid #D9D9D9;font-size:{body_font:.1f}pt;line-height:{body_line}px;color:#000000;white-space:nowrap;text-align:center;'>{html_escape(item['inicio'])}</td>
                </tr>
                """

        html += f"<tr><td colspan='2' style='height:{spacer_height}px;font-size:0;line-height:0;border-left:1px solid #000000;border-right:1px solid #000000;border-bottom:1px solid #000000;'>&nbsp;</td></tr></table>"
        html += f"<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='{column_width}' style='width:{column_width}px;'><tr><td height='{spacer_height}' style='height:{spacer_height}px;font-size:0;line-height:0;'>&nbsp;</td></tr></table>"

        columns_html[best_col] += html
        columns_current_weight[best_col] += mq_data["weight"]

    # 5. Montar Documento Final
    header_row = ""
    content_row = ""
    for i in range(column_count):
        header_row += f"""<td width='{column_width}' align='center' valign='middle' style='width:{column_width}px;padding:{block_pad_y}px {row_pad_x}px;border:1px solid #000000;background-color:#D9E2F3;font-size:{header_font:.1f}pt;font-weight:bold;line-height:{header_line}px;text-align:center;'>M&aacute;quina / Grupo / OB / In&iacute;cio</td>"""
        content_row += f"""<td width='{column_width}' valign='top' style='width:{column_width}px;padding-top:{block_pad_y}px;vertical-align:top;'>{columns_html[i] or "&nbsp;"}</td>"""
        if i < column_count - 1:
            header_row += f"<td width='{column_gap}' style='width:{column_gap}px;font-size:0;line-height:0;'>&nbsp;</td>"
            content_row += f"<td width='{column_gap}' style='width:{column_gap}px;font-size:0;line-height:0;'>&nbsp;</td>"

    full_html = f"""<html><head><meta http-equiv='Content-Type' content='text/html; charset=utf-8'></head>
    <body style='margin:0;padding:0;background-color:#FFFFFF;'><div class='WordSection1'>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;background-color:#FFFFFF;border-collapse:collapse;'>
    <tr><td align='center' style='padding:{outer_pad}px;'>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='{container_width}' style='width:{container_width}px;background-color:#FFFFFF;border-collapse:collapse;'>
    <tr><td style='padding:{block_pad_y}px {row_pad_x}px;border:1px solid #D9E2F3;background-color:#FFFFFF;'>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;border-collapse:collapse;'>
    <tr><td align='center' style='padding:0 0 2px 0;font-size:{title_font:.1f}pt;font-weight:bold;line-height:{title_line}px;color:#000000;text-align:center;'>{html_escape(config['layout']['title'])}</td></tr>
    <tr><td align='center' style='padding:0 0 2px 0;font-size:{meta_font:.1f}pt;line-height:{meta_line}px;color:#333333;text-align:center;'>{html_escape(config['layout']['subtitle'])}</td></tr>
    <tr><td align='center' style='padding:0 0 {block_pad_y}px 0;font-size:{meta_font:.1f}pt;line-height:{meta_line}px;color:#333333;text-align:center;'>Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')} | M&aacute;quinas: {machine_count} | Receitas: {recipe_count}</td></tr>
    </table>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;border-collapse:collapse;'>
    <tr>{header_row}</tr><tr>{content_row}</tr>
    </table></td></tr></table></td></tr></table></div></body></html>"""

    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(full_html)

    print(f"[{datetime.now()}] [PY-HTML] [INFO] HTML gerado com sucesso: {output_html}")
    return True

if __name__ == "__main__":
    eid = sys.argv[1] if len(sys.argv) > 1 else "manual"
    generate_html(eid)

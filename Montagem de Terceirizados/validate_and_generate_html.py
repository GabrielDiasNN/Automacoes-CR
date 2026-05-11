# -*- coding: utf-8 -*-
# {
#   "version": "1.0.6",
#   "skill": "ai-native-development-standard",
#   "contract": "ipc-file-payload",
#   "description": "Nucleo de validacao NF/OB (E/S via arquivos para estabilidade)",
#   "reliability": "Base64-Bridge-Logs, HTML-Entity-Shield"
# }
import os
import sys
import json
import re
import time
import base64
from datetime import datetime

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# ==========================================
# CONSTANTES DE DESIGN / UI
# ==========================================
HTML_ICON_WARNING   = "&#9888;&#65039;"
HTML_ICON_CHECK     = "&#9989;"
HTML_ICON_CALENDAR  = "&#128197;"
HTML_ICON_MAGNIFY   = "&#128269;"
HTML_ICON_CHART     = "&#128202;"
HTML_ICON_CHART_UP  = "&#128200;"
HTML_ICON_CROSS     = "&#10060;"
HTML_ICON_STOPWATCH = "&#9201;"
HTML_ICON_TROPHY    = "&#127942;"
HTML_ICON_TARGET    = "&#127919;"

ROBO_VERSAO = "v1.0"

def log(message, level="INFO", exec_id="manual"):
    """Envia logs em Base64 para o stderr (Isolamento total)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    raw_msg = f"[{ts}] [PY-VALIDATE] [{level}] [ExecId:{exec_id}] {message}"
    b64_msg = base64.b64encode(raw_msg.encode('utf-8')).decode('ascii')
    sys.stderr.write(f"B64:{b64_msg}\n")
    sys.stderr.flush()

def html_escape(text):
    if not text: return "&nbsp;"
    s = str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')
    char_map = {
        '\u00e7': '&ccedil;', '\u00c7': '&Ccedil;', '\u00e3': '&atilde;', '\u00c3': '&Atilde;',
        '\u00f5': '&otilde;', '\u00d5': '&Otilde;', '\u00e1': '&aacute;', '\u00c1': '&Aacute;',
        '\u00e9': '&eacute;', '\u00c9': '&Eacute;', '\u00ed': '&iacute;', '\u00cd': '&Iacute;',
        '\u00f3': '&oacute;', '\u00d3': '&Oacute;', '\u00fa': '&uacute;', '\u00da': '&Uacute;',
        '\u00e2': '&acirc;', '\u00c2': '&Acirc;', '\u00ea': '&ecirc;', '\u00ca': '&Ecirc;',
        '\u00f4': '&ocirc;', '\u00d4': '&Ocirc;', '\u00e0': '&agrave;', '\u00c0': '&Agrave;',
    }
    for char, entity in char_map.items():
        s = s.replace(char, entity)
    return s

def clean_str(val):
    if val is None: return ""
    if isinstance(val, float) and val.is_integer(): return str(int(val))
    return str(val).strip()

def processar_validacao(data):
    erros = []
    for row in data:
        cd_ref_clt = clean_str(row.get('CD_REF_CLT'))
        qt_pc_nf = clean_str(row.get('QT_PC_NF'))
        obs_ob = clean_str(row.get('OBS_OB'))
        montagem_ok = True; nfs_montagem = []
        if qt_pc_nf:
            partes = qt_pc_nf.split(',')
            for parte in partes:
                sub_partes = parte.split('-')
                if len(sub_partes) >= 2:
                    nf_atual = sub_partes[1].strip()
                    nfs_montagem.append(nf_atual)
                    if nf_atual != cd_ref_clt: montagem_ok = False
        nf_montagem_str = ", ".join(nfs_montagem)
        nf_prog = ""
        match = re.search(r"NF:\s*(\d+)", obs_ob, re.IGNORECASE)
        if match: nf_prog = match.group(1).strip()
        prog_ok = (cd_ref_clt == nf_prog)
        detalhe_erro = ""
        if not montagem_ok and not prog_ok: detalhe_erro = "Erro de Montagem e Programacao"
        elif not montagem_ok and prog_ok: detalhe_erro = "Erro de Montagem"
        elif montagem_ok and not prog_ok: detalhe_erro = "Erro de Programacao"
        if detalhe_erro:
            row['DETALHE_ERRO'] = detalhe_erro; row['NF_ESPERADA'] = cd_ref_clt
            row['NF_MONTAGEM'] = nf_montagem_str; row['NF_PROGRAMACAO'] = nf_prog
            erros.append(row)
    return erros

def gerar_tabela_categoria_html(titulo, erros, cor_titulo):
    html = f"<div style='margin-bottom: 24px;'><p style='font-size:12pt;margin:10px 0 8px 0;color:{cor_titulo}; border-bottom: 2px solid {cor_titulo}; padding-bottom: 4px; display: inline-block;'><b>{html_escape(titulo)} ({len(erros)})</b></p>"
    if not erros: return html + "<p style='font-size:10pt;color:#6b7280;margin:0 0 8px 0; background:#f9fafb; padding:10px; border-radius:6px;'><i>Nenhum item nesta categoria.</i></p></div>"
    html += "<table border='0' cellspacing='0' cellpadding='8' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9.5pt;width:100%; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden;'><tr style='background:#f3f4f6; color:#374151; text-align:center; font-weight:bold; border-bottom:2px solid #e5e7eb;'><th>N&ordm; OB</th><th>Prog.</th><th>Ref. Cliente (Esperada)</th><th>NF Usada (Mont.)</th><th>NF Usada (Prog.)</th><th>Detalhe do Erro</th></tr>"
    for idx, e in enumerate(erros):
        bg = "#ffffff" if idx % 2 == 0 else "#f9fafb"
        html += f"<tr style='background:{bg}; text-align:center; border-bottom:1px solid #e5e7eb;'><td>{html_escape(e.get('NR_OB'))}</td><td>{html_escape(e.get('NR_PROG'))}</td><td><span style='background:#eff6ff; color:#1d4ed8; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #bfdbfe;'>{html_escape(e.get('NF_ESPERADA'))}</span></td><td>{destaque_nf_montagem(e.get('NF_MONTAGEM'), e.get('NF_ESPERADA'))}</td><td>{destaque_nf_prog(e.get('NF_PROGRAMACAO'), e.get('NF_ESPERADA'))}</td><td style='color:#b91c1c;'>{html_escape(e.get('DETALHE_ERRO'))}</td></tr>"
    html += "</table></div>"
    return html

def destaque_nf_montagem(nf_montagem_str, nf_esperada):
    if not nf_montagem_str: return "<span style='color:#9ca3af;'><i>N/A</i></span>"
    nfs = [n.strip() for n in nf_montagem_str.split(',')]; res = []
    for nf in nfs:
        if nf == nf_esperada: res.append(f"<span style='color:#166534; font-weight:bold;'>{html_escape(nf)}</span>")
        else: res.append(f"<span style='background:#fee2e2; color:#991b1b; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #fca5a5;'>{html_escape(nf)}</span>")
    return ", ".join(res)

def destaque_nf_prog(nf_prog, nf_esperada):
    if not nf_prog: return "<span style='color:#9ca3af;'><i>N/A</i></span>"
    if nf_prog == nf_esperada: return f"<span style='color:#166534; font-weight:bold;'>{html_escape(nf_prog)}</span>"
    else: return f"<span style='background:#fee2e2; color:#991b1b; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #fca5a5;'>{html_escape(nf_prog)}</span>"

def gerar_tabela_completa_erros(erros):
    if not erros: return ""
    html = "<div style='margin-top: 30px;'><h3 style='font-size:14pt; margin:0 0 12px 0; color:#1f2937; text-align:center;'>Detalhamento Completo das Divergencias</h3>"
    html += "<div style='overflow-x:auto; border: 1px solid #e5e7eb; border-radius: 8px;'><table border='0' cellspacing='0' cellpadding='8' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9pt;width:100%; white-space:nowrap;'>"
    html += "<tr style='background-color:#f87171; color:#ffffff; text-align:center; font-weight:bold;'><th>Sit. OB</th><th>Prog.</th><th>Fac&ccedil;&atilde;o</th><th>N&ordm; OB</th><th>Ref. Cliente</th><th>NF (Montagem)</th><th>NF (Prog.)</th><th>Detalhe Do Erro</th><th>Alternativo</th><th>Data/Hora</th></tr>"
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    for idx, e in enumerate(erros):
        bg = "#ffffff" if idx % 2 == 0 else "#fef2f2"
        html += f"<tr style='background:{bg}; text-align:center; border-bottom:1px solid #e5e7eb;'><td>{html_escape(e.get('ST_OB_ABERTO'))}</td><td>{html_escape(e.get('NR_PROG'))}</td><td>{html_escape(e.get('DS_ITEMPED_CLT'))}</td><td>{html_escape(e.get('NR_OB'))}</td><td><span style='background:#eff6ff; color:#1d4ed8; padding:2px 6px; border-radius:4px; font-weight:bold;'>{html_escape(e.get('NF_ESPERADA'))}</span></td><td>{destaque_nf_montagem(e.get('NF_MONTAGEM'), e.get('NF_ESPERADA'))}</td><td>{destaque_nf_prog(e.get('NF_PROGRAMACAO'), e.get('NF_ESPERADA'))}</td><td style='color:#b91c1c;'>{html_escape(e.get('DETALHE_ERRO'))}</td><td>{html_escape(e.get('CD_ALTERNATIVO'))}</td><td style='color:#6b7280;'>{agora}</td></tr>"
    html += "</table></div></div>"
    return html

def montar_template_email(tipo_notificacao, total_linhas, total_erros, elapsed_time, detalhes_html):
    tipo = tipo_notificacao.upper().strip()
    if tipo == "ERRO": cor, icon, msg, res = "#dc2626", HTML_ICON_WARNING, "Divergencias Detectadas", f"{total_erros} erros"
    elif tipo == "ALTERACAO": cor, icon, msg, res = "#ea580c", HTML_ICON_TARGET, "Divergencias Alteradas", f"{total_erros} erros"
    else: cor, icon, msg, res = "#16a34a", HTML_ICON_CHECK, "Validacao Aprovada", "100% OK"
    html = f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body style='margin:0;padding:24px;background:#f3f4f6;'><div style='font-family:Segoe UI,Calibri,Arial,sans-serif;font-size:11pt;max-width:960px;margin:0 auto;color:#1f2937;'><div style='background:{cor};padding:24px;border-radius:12px 12px 0 0;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);'><h1 style='color:#ffffff;margin:0;font-size:24pt;text-align:center;font-weight:600;'><span style='font-size:32pt;vertical-align:middle;margin-right:12px;'>{icon}</span>{msg}</h1></div><div style='background:#ffffff;padding:32px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);'>"
    if tipo == "ERRO": html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_MAGNIFY}</span> <b>Foram detectadas divergencias entre a Montagem e a Programacao.</b></p>"
    elif tipo == "ALTERACAO": html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_CHART_UP}</span> <b>Houve uma atualizacao no status das divergencias acompanhadas.</b></p>"
    else: html += f"<p style='font-size:13pt;margin:0 0 12px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_TROPHY}</span> <b>Nenhuma divergencia foi encontrada na rotina atual. O processo esta liberado.</b></p>"
    card_tpl = "<td style='width:33%;padding:16px;'><div style='background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;text-align:center;'><div style='font-size:20pt;margin-bottom:8px;'>{icon}</div><div style='color:#6b7280;font-size:10pt;font-weight:bold;text-transform:uppercase;letter-spacing:0.05em;'>{label}</div><div style='color:{val_color};font-size:18pt;font-weight:bold;margin-top:4px;'>{value}</div></div></td>"
    cards = card_tpl.format(icon=HTML_ICON_CHART, label="Total de Linhas", value=total_linhas, val_color="#111827") + card_tpl.format(icon=(HTML_ICON_CHECK if tipo == "ACERTO" else HTML_ICON_CROSS), label="Resultado", value=res, val_color=("#16a34a" if tipo == "ACERTO" else "#dc2626")) + card_tpl.format(icon=HTML_ICON_STOPWATCH, label="Tempo Total", value=f"{elapsed_time:.2f}s", val_color="#111827")
    html += f"<div style='margin: 24px -16px;'><table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='border-collapse:collapse;'><tr>{cards}</tr></table></div>"
    if detalhes_html: html += f"<div>{detalhes_html}</div>"
    html += f"<hr style='border:0;border-top:1px solid #e5e7eb;margin:32px 0 24px 0;'><p style='font-size:10pt;color:#9ca3af;text-align:center;margin:0;'><span style='font-size:13pt;vertical-align:middle;'>{HTML_ICON_CALENDAR}</span> <b>Data da Validacao:</b> {datetime.now().strftime('%d/%m/%Y &agrave;s %H:%M:%S')}</p></div></div></body></html>"
    return html

import hashlib

def gerar_assinatura(erro):
    """Gera um hash MD5 unico para a combinacao de erro/OB."""
    base = f"{str(erro.get('NR_OB', '')).strip().upper()}|{str(erro.get('NR_PROG', '')).strip().upper()}|{str(erro.get('CD_REF_CLT', '')).strip().upper()}|{str(erro.get('DETALHE_ERRO', '')).strip().upper()}"
    if not base.strip('|_'): base = "VAZIO"
    return hashlib.md5(base.encode('utf-8')).hexdigest()

def main():
    start_time = time.time()
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(script_dir, ".cache_erros.json")
    data_file = os.path.join(script_dir, f".data_{exec_id}.json")
    
    # 1. Carregar Dados via Arquivo Temporario (Estabilidade Maxima)
    try:
        if not os.path.exists(data_file):
            log("Arquivo de dados nao encontrado: " + data_file, "ERROR", exec_id)
            sys.exit(1)
        with open(data_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        os.remove(data_file)
    except Exception as e:
        log("Falha ao ler dados do arquivo: " + str(e), "ERROR", exec_id)
        sys.exit(1)

    total_linhas = len(data)
    erros_atuais = processar_validacao(data)
    total_erros = len(erros_atuais); dic_atuais = {gerar_assinatura(e): e for e in erros_atuais}
    cache_anterior = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f: cache_anterior = json.load(f)
        except: pass
    dic_anteriores = cache_anterior.get("itens", {}); ja_existia_cache = bool(cache_anterior)
    novos, permanentes, corrigidos = [], [], []
    for ass, erro in dic_atuais.items():
        if ass in dic_anteriores: permanentes.append(erro)
        else: novos.append(erro)
    for ass, erro in dic_anteriores.items():
        if ass not in dic_atuais: corrigidos.append(erro)
    tipo_notif = "NENHUMA"
    if not ja_existia_cache:
        if total_erros > 0: tipo_notif = "ERRO"
    else:
        if total_erros == 0 and len(dic_anteriores) > 0: tipo_notif = "ACERTO" 
        elif total_erros > 0 and len(dic_anteriores) == 0: tipo_notif = "ERRO" 
        elif total_erros > 0 and (novos or corrigidos): tipo_notif = "ALTERACAO" 
    try:
        with open(cache_file, 'w', encoding='utf-8') as f: json.dump({"timestamp": datetime.now().isoformat(), "itens": dic_atuais}, f, ensure_ascii=False, indent=2)
    except: pass

    if tipo_notif != "NENHUMA":
        elapsed_time = time.time() - start_time
        detalhes_html = ""; subject = "Alerta: Divergencias Montagem - " + datetime.now().strftime('%d/%m/%Y')
        if tipo_notif == "ERRO": detalhes_html = gerar_tabela_completa_erros(erros_atuais)
        elif tipo_notif == "ALTERACAO":
            subject = "Alteracao: Divergencias Montagem - " + datetime.now().strftime('%d/%m/%Y')
            txt_novos = "Novo Erro" if len(novos) == 1 else "Novos Erros"
            txt_cor = "Erro Corrigido" if len(corrigidos) == 1 else "Erros Corrigidos"
            txt_perm = "Erro Permanente" if len(permanentes) == 1 else "Erros Permanentes"
            resumo_painel = f"""<div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; padding:24px; margin: 30px 0; text-align:center;"><h3 style="margin:0 0 20px 0; color:#1f2937; font-size:14pt; font-weight:600;">Resumo da Atualizacao</h3><table border="0" cellspacing="0" cellpadding="0" style="margin: 0 auto; width: 100%; max-width: 600px; table-layout:fixed;"><tr><td align="center" style="padding: 0 10px;"><div style="background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#991b1b; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Novos</span><span style="display:block; font-size:28pt; color:#b91c1c; font-weight:bold; line-height:1;">{len(novos)}</span></div></td><td align="center" style="padding: 0 10px;"><div style="background:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#166534; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Corrigidos</span><span style="display:block; font-size:28pt; color:#15803d; font-weight:bold; line-height:1;">{len(corrigidos)}</span></div></td><td align="center" style="padding: 0 10px;"><div style="background:#fff7ed; border:1px solid #fdba74; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#9a3412; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Permanentes</span><span style="display:block; font-size:28pt; color:#c2410c; font-weight:bold; line-height:1;">{len(permanentes)}</span></div></td></tr></table></div>"""
            detalhes_html = resumo_painel + gerar_tabela_categoria_html(txt_novos, novos, "#b91c1c") + gerar_tabela_categoria_html(txt_cor, corrigidos, "#15803d") + gerar_tabela_categoria_html(txt_perm, permanentes, "#c2410c")
        elif tipo_notif == "ACERTO": subject = "Sucesso: Validacao Aprovada - " + datetime.now().strftime('%d/%m/%Y'); detalhes_html = ""
        html_final = montar_template_email(tipo_notif, total_linhas, total_erros, elapsed_time, detalhes_html)
        result_payload = { "subject_b64": base64.b64encode(subject.encode('utf-8')).decode('ascii'), "html": html_final }
        payload_file = os.path.join(script_dir, f".payload_{exec_id}.json")
        try:
            with open(payload_file, 'w', encoding='utf-8') as f: json.dump(result_payload, f, ensure_ascii=False)
            log("Payload gerado em arquivo: " + payload_file, "INFO", exec_id)
        except Exception as e:
            log("Falha ao gravar payload: " + str(e), "ERROR", exec_id); sys.exit(1)
        log("Processamento concluido (" + tipo_notif + ").", "INFO", exec_id)
    else:
        log("Nenhuma mudanca.", "INFO", exec_id)

if __name__ == "__main__":
    main()

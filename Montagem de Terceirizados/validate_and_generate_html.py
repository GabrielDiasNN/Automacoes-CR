# pylint: disable=all
# mypy: ignore-errors
# -*- coding: utf-8 -*-
# {
#   "version": "1.2.0",
#   "skill": "ai-native-development-standard",
#   "contract": "ipc-file-payload",
#   "description": "Nucleo de validacao NF/OB com tipagem estrita e gramatica corrigida",
#   "reliability": "Base64-Bridge-Logs, HTML-Entity-Shield"
# }
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

# Forca UTF-8 para garantir interoperabilidade
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# ==========================================
# CONSTANTES DE DESIGN / UI
# ==========================================
HTML_ICON_WARNING: str = "&#9888;&#65039;"
HTML_ICON_CHECK: str = "&#9989;"
HTML_ICON_CALENDAR: str = "&#128197;"
HTML_ICON_MAGNIFY: str = "&#128269;"
HTML_ICON_CHART: str = "&#128202;"
HTML_ICON_CHART_UP: str = "&#128200;"
HTML_ICON_CROSS: str = "&#10060;"
HTML_ICON_STOPWATCH: str = "&#9201;"
HTML_ICON_TROPHY: str = "&#127942;"
HTML_ICON_TARGET: str = "&#127919;"

ROBO_VERSAO: str = "v1.1"


def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
    """Envia logs para o stderr."""
    ts: str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    raw_msg: str = f"[{ts}] [PY-VALIDATE] [{level}] [ExecId:{exec_id}] {message}"
    sys.stderr.write(f"{raw_msg}\n")
    sys.stderr.flush()


def html_escape(text: Optional[Any]) -> str:
    """Escapa caracteres HTML para garantir renderizacao correta e seguranca."""
    if not text:
        return "&nbsp;"
    s: str = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
    char_map: Dict[str, str] = {
        "ç": "&ccedil;",
        "Ç": "&Ccedil;",
        "ã": "&atilde;",
        "Ã": "&Atilde;",
        "õ": "&otilde;",
        "Õ": "&Otilde;",
        "á": "&aacute;",
        "Á": "&Aacute;",
        "é": "&eacute;",
        "É": "&Eacute;",
        "í": "&iacute;",
        "Í": "&Iacute;",
        "ó": "&oacute;",
        "Ó": "&Oacute;",
        "ú": "&uacute;",
        "Ú": "&Uacute;",
        "â": "&acirc;",
        "Â": "&Acirc;",
        "ê": "&ecirc;",
        "Ê": "&Ecirc;",
        "ô": "&ocirc;",
        "Ô": "&Ocirc;",
        "à": "&agrave;",
        "À": "&Agrave;",
    }
    for char, entity in char_map.items():
        s = s.replace(char, entity)
    return s


def clean_str(val: Any) -> str:
    """Limpa e normaliza strings ou numeros do Excel/Oracle."""
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def processar_validacao(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Executa a logica de negocio: compara Montagem com Programacao."""
    erros: List[Dict[str, Any]] = []
    for row in data:
        cd_ref_clt: str = clean_str(row.get("CD_REF_CLT"))
        qt_pc_nf: str = clean_str(row.get("QT_PC_NF"))
        obs_ob: str = clean_str(row.get("OBS_OB"))

        montagem_ok: bool = True
        nfs_montagem: List[str] = []

        if qt_pc_nf:
            partes: List[str] = qt_pc_nf.split(",")
            for parte in partes:
                sub_partes: List[str] = parte.split("-")
                if len(sub_partes) >= 2:
                    nf_atual: str = sub_partes[1].strip()
                    nfs_montagem.append(nf_atual)
                    if nf_atual != cd_ref_clt:
                        montagem_ok = False

        nf_montagem_str: str = ", ".join(nfs_montagem)
        nf_prog: str = ""
        match = re.search(r"NF:\s*(\d+)", obs_ob, re.IGNORECASE)
        if match:
            nf_prog = match.group(1).strip()

        prog_ok: bool = cd_ref_clt == nf_prog
        detalhe_erro: str = ""

        if not montagem_ok and not prog_ok:
            detalhe_erro = "Erro de Montagem e Programação"
        elif not montagem_ok:
            detalhe_erro = "Erro de Montagem"
        elif not prog_ok:
            detalhe_erro = "Erro de Programação"

        if detalhe_erro:
            row["DETALHE_ERRO"] = detalhe_erro
            row["NF_ESPERADA"] = cd_ref_clt
            row["NF_MONTAGEM"] = nf_montagem_str
            row["NF_PROGRAMACAO"] = nf_prog
            erros.append(row)
    return erros


def destaque_nf_montagem(nf_montagem_str: Optional[str], nf_esperada: str) -> str:
    """Gera visual HTML para destaque de NFs divergentes na Montagem."""
    if not nf_montagem_str:
        return "<span style='color:#9ca3af;'><i>N/A</i></span>"
    nfs: List[str] = [n.strip() for n in nf_montagem_str.split(",")]
    res: List[str] = []
    for nf in nfs:
        if nf == nf_esperada:
            res.append(
                f"<span style='color:#166534; font-weight:bold;'>{html_escape(nf)}</span>"
            )
        else:
            res.append(
                f"<span style='background:#fee2e2; color:#991b1b; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #fca5a5;'>{html_escape(nf)}</span>"
            )
    return ", ".join(res)


def destaque_nf_prog(nf_prog: Optional[str], nf_esperada: str) -> str:
    """Gera visual HTML para destaque de NF divergente na Programacao."""
    if not nf_prog:
        return "<span style='color:#9ca3af;'><i>N/A</i></span>"
    if nf_prog == nf_esperada:
        return f"<span style='color:#166534; font-weight:bold;'>{html_escape(nf_prog)}</span>"
    return f"<span style='background:#fee2e2; color:#991b1b; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #fca5a5;'>{html_escape(nf_prog)}</span>"


def gerar_tabela_categoria_html(
    titulo: str, erros: List[Dict[str, Any]], cor_titulo: str
) -> str:
    """Gera uma tabela HTML para uma categoria especifica de erros."""
    html: str = (
        f"<div style='margin-bottom: 24px;'><p style='font-size:12pt;margin:10px 0 8px 0;color:{cor_titulo}; border-bottom: 2px solid {cor_titulo}; padding-bottom: 4px; display: inline-block;'><b>{html_escape(titulo)} ({len(erros)})</b></p>"
    )
    if not erros:
        return (
            html
            + "<p style='font-size:10pt;color:#6b7280;margin:0 0 8px 0; background:#f9fafb; padding:10px; border-radius:6px;'><i>Nenhum item nesta categoria.</i></p></div>"
        )

    html += "<table border='0' cellspacing='0' cellpadding='8' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9.5pt;width:100%; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden;'><tr style='background:#f3f4f6; color:#374151; text-align:center; font-weight:bold; border-bottom:2px solid #e5e7eb;'><th>Nº OB</th><th>Prog.</th><th>Ref. Cliente (Esperada)</th><th>NF Usada (Mont.)</th><th>NF Usada (Prog.)</th><th>Detalhe do Erro</th></tr>"
    for idx, e in enumerate(erros):
        bg: str = "#ffffff" if idx % 2 == 0 else "#f9fafb"
        html += f"<tr style='background:{bg}; text-align:center; border-bottom:1px solid #e5e7eb;'><td>{html_escape(e.get('NR_OB'))}</td><td>{html_escape(e.get('NR_PROG'))}</td><td><span style='background:#eff6ff; color:#1d4ed8; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #bfdbfe;'>{html_escape(e.get('NF_ESPERADA'))}</span></td><td>{destaque_nf_montagem(cast(str, e.get('NF_MONTAGEM')), cast(str, e.get('NF_ESPERADA')))}</td><td>{destaque_nf_prog(cast(str, e.get('NF_PROGRAMACAO')), cast(str, e.get('NF_ESPERADA')))}</td><td style='color:#b91c1c;'>{html_escape(e.get('DETALHE_ERRO'))}</td></tr>"
    html += "</table></div>"
    return html


def gerar_tabela_completa_erros(erros: List[Dict[str, Any]]) -> str:
    """Gera o detalhamento completo das divergencias para o e-mail."""
    if not erros:
        return ""
    html: str = (
        "<div style='margin-top: 30px;'><h3 style='font-size:14pt; margin:0 0 12px 0; color:#1f2937; text-align:center;'>Detalhamento Completo das Divergências</h3>"
    )
    html += "<div style='overflow-x:auto; border: 1px solid #e5e7eb; border-radius: 8px;'><table border='0' cellspacing='0' cellpadding='8' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9pt;width:100%; white-space:nowrap;'>"
    html += "<tr style='background-color:#f87171; color:#ffffff; text-align:center; font-weight:bold;'><th>Sit. OB</th><th>Prog.</th><th>Facção</th><th>Nº OB</th><th>Ref. Cliente</th><th>NF (Montagem)</th><th>NF (Prog.)</th><th>Detalhe Do Erro</th><th>Alternativo</th><th>Data/Hora</th></tr>"
    agora: str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    for idx, e in enumerate(erros):
        bg: str = "#ffffff" if idx % 2 == 0 else "#fef2f2"
        html += f"<tr style='background:{bg}; text-align:center; border-bottom:1px solid #e5e7eb;'><td>{html_escape(e.get('ST_OB_ABERTO'))}</td><td>{html_escape(e.get('NR_PROG'))}</td><td>{html_escape(e.get('DS_ITEMPED_CLT'))}</td><td>{html_escape(e.get('NR_OB'))}</td><td><span style='background:#eff6ff; color:#1d4ed8; padding:2px 6px; border-radius:4px; font-weight:bold;'>{html_escape(e.get('NF_ESPERADA'))}</span></td><td>{destaque_nf_montagem(cast(str, e.get('NF_MONTAGEM')), cast(str, e.get('NF_ESPERADA')))}</td><td>{destaque_nf_prog(cast(str, e.get('NF_PROGRAMACAO')), cast(str, e.get('NF_ESPERADA')))}</td><td style='color:#b91c1c;'>{html_escape(e.get('DETALHE_ERRO'))}</td><td>{html_escape(e.get('CD_ALTERNATIVO'))}</td><td style='color:#6b7280;'>{agora}</td></tr>"
    html += "</table></div></div>"
    return html


def montar_template_email(
    tipo_notificacao: str,
    total_linhas: int,
    total_erros: int,
    elapsed_time: float,
    detalhes_html: str,
) -> str:
    """Envolve os detalhes no template de e-mail padronizado."""
    tipo: str = tipo_notificacao.upper().strip()
    cor: str = "#dc2626"
    icon: str = HTML_ICON_WARNING
    msg: str = "Divergências Detectadas"
    res: str = f"{total_erros} erros"

    if tipo == "ALTERACAO":
        cor, icon, msg, res = (
            "#ea580c",
            HTML_ICON_TARGET,
            "Divergências Alteradas",
            f"{total_erros} erros",
        )
    elif tipo == "ACERTO":
        cor, icon, msg, res = (
            "#16a34a",
            HTML_ICON_CHECK,
            "Validação Aprovada",
            "100% OK",
        )

    html: str = (
        f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body style='margin:0;padding:24px;background:#f3f4f6;'><div style='font-family:Segoe UI,Calibri,Arial,sans-serif;font-size:11pt;max-width:960px;margin:0 auto;color:#1f2937;'><div style='background:{cor};padding:24px;border-radius:12px 12px 0 0;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);'><h1 style='color:#ffffff;margin:0;font-size:24pt;text-align:center;font-weight:600;'><span style='font-size:32pt;vertical-align:middle;margin-right:12px;'>{icon}</span>{msg}</h1></div><div style='background:#ffffff;padding:32px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);'>"
    )

    if tipo == "ERRO":
        html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_MAGNIFY}</span> <b>Foram detectadas divergências entre a Montagem e a Programação.</b></p>"
    elif tipo == "ALTERACAO":
        html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_CHART_UP}</span> <b>Houve uma atualização no status das divergências acompanhadas.</b></p>"
    else:
        html += f"<p style='font-size:13pt;margin:0 0 12px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_TROPHY}</span> <b>Nenhuma divergência foi encontrada na rotina atual. O processo está liberado.</b></p>"

    card_tpl: str = (
        "<td style='width:33%;padding:16px;'><div style='background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;text-align:center;'><div style='font-size:20pt;margin-bottom:8px;'>{icon}</div><div style='color:#6b7280;font-size:10pt;font-weight:bold;text-transform:uppercase;letter-spacing:0.05em;'>{label}</div><div style='color:{val_color};font-size:18pt;font-weight:bold;margin-top:4px;'>{value}</div></div></td>"
    )
    res_color: str = "#16a34a" if tipo == "ACERTO" else "#dc2626"
    cards: str = (
        card_tpl.format(
            icon=HTML_ICON_CHART,
            label="Total de Linhas",
            value=total_linhas,
            val_color="#111827",
        )
        + card_tpl.format(
            icon=(HTML_ICON_CHECK if tipo == "ACERTO" else HTML_ICON_CROSS),
            label="Resultado",
            value=res,
            val_color=res_color,
        )
        + card_tpl.format(
            icon=HTML_ICON_STOPWATCH,
            label="Tempo Total",
            value=f"{elapsed_time:.2f}s",
            val_color="#111827",
        )
    )

    html += f"<div style='margin: 24px -16px;'><table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='border-collapse:collapse;'><tr>{cards}</tr></table></div>"
    if detalhes_html:
        html += f"<div>{detalhes_html}</div>"
    html += f"<hr style='border:0;border-top:1px solid #e5e7eb;margin:32px 0 24px 0;'><p style='font-size:10pt;color:#9ca3af;text-align:center;margin:0;'><span style='font-size:13pt;vertical-align:middle;'>{HTML_ICON_CALENDAR}</span> <b>Data da Validação:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</p></div></div></body></html>"
    return html


def gerar_assinatura(erro: Dict[str, Any]) -> str:
    """Gera um hash MD5 unico para a combinacao de erro/OB."""
    base: str = (
        f"{str(erro.get('NR_OB', '')).strip().upper()}|{str(erro.get('NR_PROG', '')).strip().upper()}|{str(erro.get('CD_REF_CLT', '')).strip().upper()}|{str(erro.get('DETALHE_ERRO', '')).strip().upper()}"
    )
    if not base.strip("|_"):
        base = "VAZIO"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def main() -> None:
    """Orquestrador principal da validacao."""
    start_time: float = time.time()
    exec_id: str = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir: str = os.path.dirname(os.path.abspath(__file__))
    cache_file: str = os.path.join(script_dir, ".cache_erros.json")
    data_file: str = os.path.join(script_dir, f".data_{exec_id}.json")

    # 1. Carregar Dados via Arquivo Temporario
    try:
        if not os.path.exists(data_file):
            log(f"Arquivo de dados nao encontrado: {data_file}", "ERROR", exec_id)
            sys.exit(1)
        with open(data_file, "r", encoding="utf-8-sig") as f:
            data: List[Dict[str, Any]] = json.load(f)
        os.remove(data_file)
    except Exception as e:  # pylint: disable=broad-exception-caught
        log(f"Falha ao ler dados do arquivo: {e}", "ERROR", exec_id)
        sys.exit(1)

    total_linhas: int = len(data)
    erros_atuais: List[Dict[str, Any]] = processar_validacao(data)
    total_erros: int = len(erros_atuais)
    dic_atuais: Dict[str, Dict[str, Any]] = {
        gerar_assinatura(e): e for e in erros_atuais
    }

    cache_anterior: Dict[str, Any] = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f_cache:
                cache_anterior = json.load(f_cache)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    dic_anteriores: Dict[str, Any] = cache_anterior.get("itens", {})
    ja_existia_cache: bool = bool(cache_anterior)

    novos: List[Dict[str, Any]] = []
    permanentes: List[Dict[str, Any]] = []
    corrigidos: List[Dict[str, Any]] = []

    for ass, erro in dic_atuais.items():
        if ass in dic_anteriores:
            permanentes.append(erro)
        else:
            novos.append(erro)
    for ass, erro_ant in dic_anteriores.items():
        if ass not in dic_atuais:
            corrigidos.append(erro_ant)

    tipo_notif: str = "NENHUMA"
    if not ja_existia_cache:
        if total_erros > 0:
            tipo_notif = "ERRO"
    else:
        if total_erros == 0 and len(dic_anteriores) > 0:
            tipo_notif = "ACERTO"
        elif total_erros > 0 and len(dic_anteriores) == 0:
            tipo_notif = "ERRO"
        elif total_erros > 0 and (novos or corrigidos):
            tipo_notif = "ALTERACAO"

    if tipo_notif != "NENHUMA":
        cache_tmp_file = cache_file + ".tmp"
        try:
            # Salva apenas no temporario. O commit ocorre no run.ps1 apos sucesso no e-mail.
            with open(cache_tmp_file, "w", encoding="utf-8") as f_out:
                json.dump(
                    {"timestamp": datetime.now().isoformat(), "itens": dic_atuais},
                    f_out,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            log(f"Falha ao gravar cache temporario: {e}", "WARN", exec_id)

        elapsed_time: float = time.time() - start_time
        detalhes_html: str = ""
        subject: str = (
            f"Alerta: Divergências Montagem - {datetime.now().strftime('%d/%m/%Y')}"
        )

        if tipo_notif == "ERRO":
            detalhes_html = gerar_tabela_completa_erros(erros_atuais)
        elif tipo_notif == "ALTERACAO":
            subject = f"Alteração: Divergências Montagem - {datetime.now().strftime('%d/%m/%Y')}"
            txt_novos: str = "Novo Erro" if len(novos) == 1 else "Novos Erros"
            txt_cor: str = (
                "Erro Corrigido" if len(corrigidos) == 1 else "Erros Corrigidos"
            )
            txt_perm: str = (
                "Erro Permanente" if len(permanentes) == 1 else "Erros Permanentes"
            )

            resumo_painel: str = (
                f"""<div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; padding:24px; margin: 30px 0; text-align:center;"><h3 style="margin:0 0 20px 0; color:#1f2937; font-size:14pt; font-weight:600;">Resumo da Atualização</h3><table border="0" cellspacing="0" cellpadding="0" style="margin: 0 auto; width: 100%; max-width: 600px; table-layout:fixed;"><tr><td align="center" style="padding: 0 10px;"><div style="background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#991b1b; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Novos</span><span style="display:block; font-size:28pt; color:#b91c1c; font-weight:bold; line-height:1;">{len(novos)}</span></div></td><td align="center" style="padding: 0 10px;"><div style="background:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#166534; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Corrigidos</span><span style="display:block; font-size:28pt; color:#15803d; font-weight:bold; line-height:1;">{len(corrigidos)}</span></div></td><td align="center" style="padding: 0 10px;"><div style="background:#fff7ed; border:1px solid #fdba74; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#9a3412; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Permanentes</span><span style="display:block; font-size:28pt; color:#c2410c; font-weight:bold; line-height:1;">{len(permanentes)}</span></div></td></tr></table></div>"""
            )
            detalhes_html = (
                resumo_painel
                + gerar_tabela_categoria_html(txt_novos, novos, "#b91c1c")
                + gerar_tabela_categoria_html(txt_cor, corrigidos, "#15803d")
                + gerar_tabela_categoria_html(txt_perm, permanentes, "#c2410c")
            )
        elif tipo_notif == "ACERTO":
            subject = (
                f"Sucesso: Validação Aprovada - {datetime.now().strftime('%d/%m/%Y')}"
            )
            detalhes_html = ""

        html_final: str = montar_template_email(
            tipo_notif, total_linhas, total_erros, elapsed_time, detalhes_html
        )
        result_payload: Dict[str, str] = {
            "subject_b64": base64.b64encode(subject.encode("utf-8")).decode("ascii"),
            "html": html_final,
        }
        payload_file: str = os.path.join(script_dir, f".payload_{exec_id}.json")
        try:
            with open(payload_file, "w", encoding="utf-8") as f_out:
                json.dump(result_payload, f_out, ensure_ascii=False)
            log(f"Payload gerado em arquivo: {payload_file}", "INFO", exec_id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            log(f"Falha ao gravar payload: {e}", "ERROR", exec_id)
            sys.exit(1)
        log(f"Processamento concluído ({tipo_notif}).", "INFO", exec_id)
    else:
        log("Nenhuma mudança.", "INFO", exec_id)


if __name__ == "__main__":
    main()


# ## Gestao de Contexto (AI-Native) - Atualizado em 12/05/2026
# - Estado: Estabilizado v1.2.1 (Sintaxe corrigida).
# - Objetivo: Garantir que a IA entenda a correcao da sintaxe e a remocao de texto vivo.



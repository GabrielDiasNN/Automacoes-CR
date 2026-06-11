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
LEMBRETE_INTERVALO_MINUTOS: int = 20


def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
    """Envia logs para o stderr."""
    ts: str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    raw_msg: str = f"[{ts}] [PY-VALIDATE] [{level}] [ExecId:{exec_id}] {message}"
    sys.stderr.write(f"{raw_msg}\n")
    sys.stderr.flush()


def html_escape(text: Optional[Any]) -> str:
    """Escapa caracteres HTML fundamentais para seguranca.
    Caracteres acentuados sao mantidos nativos em UTF-8 para melhor legibilidade e suporte moderno.
    """
    if not text:
        return "&nbsp;"
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def clean_str(val: Any) -> str:
    """Limpa e normaliza strings ou numeros do Excel/Oracle."""
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def parse_qt_pc_nf(qt_pc_nf: str) -> List[Dict[str, Any]]:
    """Quebra o campo QT_PC_NF em itens de quantidade/NF, tolerando sufixos e separadores variaveis."""
    itens: List[Dict[str, Any]] = []
    if not qt_pc_nf:
        return itens

    partes: List[str] = [
        trecho.strip()
        for trecho in re.split(r"\s*;\s*|\s*,\s*(?=\d+\s*-)", qt_pc_nf)
        if trecho.strip()
    ]
    for parte in partes:
        match = re.match(r"^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(.*))?$", parte)
        if not match:
            continue
        itens.append(
            {
                "qtd": int(match.group(1)),
                "nf": match.group(2).strip(),
                "origem": clean_str(match.group(3)),
            }
        )
    return itens


def processar_validacao(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Executa a logica de negocio: compara Montagem com Programacao."""
    erros: List[Dict[str, Any]] = []
    for row in data:
        cd_ref_clt: str = clean_str(row.get("CD_REF_CLT"))
        qt_pc_nf: str = clean_str(row.get("QT_PC_NF"))
        obs_ob: str = clean_str(row.get("OBS_OB"))

        itens_montagem: List[Dict[str, Any]] = parse_qt_pc_nf(qt_pc_nf)
        nfs_montagem: List[str] = [clean_str(item.get("nf")) for item in itens_montagem]
        itens_incorretos: List[Dict[str, Any]] = [
            item for item in itens_montagem if clean_str(item.get("nf")) != cd_ref_clt
        ]
        montagem_ok: bool = len(itens_incorretos) == 0
        nf_montagem_str: str = ", ".join(nfs_montagem)
        nf_montagem_incorretas: str = ", ".join(
            clean_str(item.get("nf")) for item in itens_incorretos
        )
        qt_peca_nf_incorreta: int = sum(
            int(cast(int, item.get("qtd", 0))) for item in itens_incorretos
        )
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
            row["NF_MONTAGEM_INCORRETAS"] = nf_montagem_incorretas
            row["NF_PROGRAMACAO"] = nf_prog
            row["QT_PECA_NF_INCORRETA"] = qt_peca_nf_incorreta
            row["TEM_ERRO_MONTAGEM"] = not montagem_ok
            erros.append(row)
    return erros


def formatar_qtd_pecas_incorretas(erro: Dict[str, Any]) -> str:
    """Renderiza a quantidade de pecas com NF incorreta apenas para divergencia de montagem."""
    if not bool(erro.get("TEM_ERRO_MONTAGEM")):
        return "<span style='color:#9ca3af;'><i>N/A</i></span>"
    qtd: int = int(erro.get("QT_PECA_NF_INCORRETA", 0) or 0)
    return (
        f"<span style='background:#fff7ed; color:#9a3412; padding:2px 6px; "
        f"border-radius:4px; font-weight:bold; border:1px solid #fdba74;'>{qtd}</span>"
    )


def formatar_nr_kanban(erro: Dict[str, Any]) -> str:
    """Renderiza a placa kanban com fallback visual quando nao existir valor."""
    nr_kanban: str = clean_str(erro.get("NR_KANBAN"))
    if not nr_kanban:
        return "<span style='color:#9ca3af;'><i>N/A</i></span>"
    return (
        f"<span style='background:#f5f3ff; color:#5b21b6; padding:2px 6px; "
        f"border-radius:4px; font-weight:bold; border:1px solid #ddd6fe;'>{html_escape(nr_kanban)}</span>"
    )


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

    html += "<table border='0' cellspacing='0' cellpadding='8' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9.5pt;width:100%; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden;'><tr style='background:#f3f4f6; color:#374151; text-align:center; font-weight:bold; border-bottom:2px solid #e5e7eb;'><th>Categoria</th><th>Nº OB</th><th>Prog.</th><th>Placa Kanban</th><th>Facção</th><th>Alternativo</th><th>NF esperada da Facção</th><th>NF informada na montagem</th><th>Qtd. peças NF incorreta</th><th>NF informada na programação</th><th>Detalhe do Erro</th></tr>"
    for idx, e in enumerate(erros):
        bg: str = "#ffffff" if idx % 2 == 0 else "#f9fafb"
        html += f"<tr style='background:{bg}; text-align:center; border-bottom:1px solid #e5e7eb;'><td>{html_escape(titulo)}</td><td>{html_escape(e.get('NR_OB'))}</td><td>{html_escape(e.get('NR_PROG'))}</td><td>{formatar_nr_kanban(e)}</td><td>{html_escape(e.get('DS_ITEMPED_CLT'))}</td><td>{html_escape(e.get('CD_ALTERNATIVO'))}</td><td><span style='background:#eff6ff; color:#1d4ed8; padding:2px 6px; border-radius:4px; font-weight:bold; border:1px solid #bfdbfe;'>{html_escape(e.get('NF_ESPERADA'))}</span></td><td>{destaque_nf_montagem(cast(str, e.get('NF_MONTAGEM')), cast(str, e.get('NF_ESPERADA')))}</td><td>{formatar_qtd_pecas_incorretas(e)}</td><td>{destaque_nf_prog(cast(str, e.get('NF_PROGRAMACAO')), cast(str, e.get('NF_ESPERADA')))}</td><td style='color:#b91c1c;'>{html_escape(e.get('DETALHE_ERRO'))}</td></tr>"
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
    html += "<tr style='background-color:#f87171; color:#ffffff; text-align:center; font-weight:bold;'><th>Sit. OB</th><th>Prog.</th><th>Placa Kanban</th><th>Facção</th><th>Nº OB</th><th>NF esperada da Facção</th><th>NF informada na montagem</th><th>Qtd. peças NF incorreta</th><th>NF informada na programação</th><th>Detalhe Do Erro</th><th>Alternativo</th><th>Data/Hora</th></tr>"
    agora: str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    for idx, e in enumerate(erros):
        bg: str = "#ffffff" if idx % 2 == 0 else "#fef2f2"
        html += f"<tr style='background:{bg}; text-align:center; border-bottom:1px solid #e5e7eb;'><td>{html_escape(e.get('ST_OB_ABERTO'))}</td><td>{html_escape(e.get('NR_PROG'))}</td><td>{formatar_nr_kanban(e)}</td><td>{html_escape(e.get('DS_ITEMPED_CLT'))}</td><td>{html_escape(e.get('NR_OB'))}</td><td><span style='background:#eff6ff; color:#1d4ed8; padding:2px 6px; border-radius:4px; font-weight:bold;'>{html_escape(e.get('NF_ESPERADA'))}</span></td><td>{destaque_nf_montagem(cast(str, e.get('NF_MONTAGEM')), cast(str, e.get('NF_ESPERADA')))}</td><td>{formatar_qtd_pecas_incorretas(e)}</td><td>{destaque_nf_prog(cast(str, e.get('NF_PROGRAMACAO')), cast(str, e.get('NF_ESPERADA')))}</td><td style='color:#b91c1c;'>{html_escape(e.get('DETALHE_ERRO'))}</td><td>{html_escape(e.get('CD_ALTERNATIVO'))}</td><td style='color:#6b7280;'>{agora}</td></tr>"
    html += "</table></div></div>"
    return html


def montar_template_email(
    tipo_notificacao: str,
    total_linhas: int,
    total_erros: int,
    total_pecas_nf_incorreta: int,
    novos_count: int,
    corrigidos_count: int,
    permanentes_count: int,
    detalhes_html: str,
) -> str:
    """Envolve os detalhes no template de e-mail padronizado."""
    tipo: str = tipo_notificacao.upper().strip()
    cor: str = "#dc2626"
    icon: str = HTML_ICON_WARNING
    msg: str = "Divergências NF x OB"
    res: str = f"{total_erros} erros"

    if tipo == "ALTERACAO":
        cor, icon, msg, res = (
            "#ea580c",
            HTML_ICON_TARGET,
            "Atualização de Divergências",
            f"{total_erros} erros",
        )
    elif tipo == "LEMBRETE":
        cor, icon, msg, res = (
            "#b45309",
            HTML_ICON_WARNING,
            "Lembrete de Pendências",
            f"{total_erros} pendências",
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
        html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_MAGNIFY}</span> <b>Divergências encontradas entre NF esperada, montagem e programação.</b></p><p style='font-size:11pt;margin:0 0 12px 0;text-align:center;color:#4b5563;'>Conferir as OBs listadas antes de seguir com a montagem do lote.</p>"
    elif tipo == "ALTERACAO":
        html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_CHART_UP}</span> <b>Conjunto de divergências atualizado. Priorizar novos itens e revisar pendências.</b></p>"
    elif tipo == "LEMBRETE":
        html += f"<p style='font-size:13pt;margin:0 0 8px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_WARNING}</span> <b>Pendências NF x OB ainda abertas. Conferir as OBs listadas.</b></p>"
    else:
        html += f"<p style='font-size:13pt;margin:0 0 12px 0;text-align:center;color:#374151;'><span style='font-size:16pt;'>{HTML_ICON_TROPHY}</span> <b>Nenhuma divergência NF x OB encontrada nesta execução. Sem ação pendente.</b></p>"

    card_tpl: str = (
        "<td style='width:{width};padding:16px;'><div style='background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;text-align:center;'><div style='font-size:20pt;margin-bottom:8px;'>{icon}</div><div style='color:#6b7280;font-size:10pt;font-weight:bold;text-transform:uppercase;letter-spacing:0.05em;'>{label}</div><div style='color:{val_color};font-size:18pt;font-weight:bold;margin-top:4px;'>{value}</div></div></td>"
    )
    res_color: str = "#16a34a" if tipo == "ACERTO" else "#dc2626"
    acao_label = (
        "Ação necessária" if tipo in ("ERRO", "ALTERACAO", "LEMBRETE") else "Status"
    )
    acao_value = (
        "Conferir OBs com divergência"
        if tipo in ("ERRO", "ALTERACAO", "LEMBRETE")
        else "Sem ação pendente"
    )
    acao_color = "#b91c1c" if tipo in ("ERRO", "ALTERACAO", "LEMBRETE") else "#166534"
    saldo_value = (
        f"N:{novos_count} | C:{corrigidos_count} | P:{permanentes_count}"
        if tipo in ("ALTERACAO", "LEMBRETE")
        else f"{total_erros}"
    )
    width_padrao: str = "25%" if tipo != "ACERTO" else "33.33%"
    cards: List[str] = [
        card_tpl.format(
            width=width_padrao,
            icon=HTML_ICON_CROSS if tipo != "ACERTO" else HTML_ICON_CHECK,
            label="OBs com divergência",
            value=saldo_value,
            val_color="#111827",
        )
    ]
    if tipo != "ACERTO":
        cards.append(
            card_tpl.format(
                width=width_padrao,
                icon=HTML_ICON_CHART,
                label="Peças NF incorreta",
                value=str(total_pecas_nf_incorreta),
                val_color="#9a3412",
            )
        )
    cards.extend(
        [
            card_tpl.format(
                width=width_padrao,
                icon=(HTML_ICON_CHECK if tipo == "ACERTO" else HTML_ICON_CROSS),
                label="Resultado",
                value=res,
                val_color=res_color,
            ),
            card_tpl.format(
                width=width_padrao,
                icon=HTML_ICON_TARGET,
                label=acao_label,
                value=acao_value,
                val_color=acao_color,
            ),
        ]
    )

    html += f"<div style='margin: 24px -16px;'><table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='border-collapse:collapse;'><tr>{''.join(cards)}</tr></table></div>"
    if detalhes_html:
        html += f"<div>{detalhes_html}</div>"
    html += f"<hr style='border:0;border-top:1px solid #e5e7eb;margin:32px 0 24px 0;'><p style='font-size:10pt;color:#9ca3af;text-align:center;margin:0;'><span style='font-size:13pt;vertical-align:middle;'>{HTML_ICON_CALENDAR}</span> <b>Data da Validação:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</p></div></div></body></html>"
    return html


def gerar_assinatura(erro: Dict[str, Any]) -> str:
    """Gera um hash MD5 unico para a combinacao de erro/OB."""
    base: str = (
        f"{str(erro.get('NR_OB', '')).strip().upper()}|{str(erro.get('NR_PROG', '')).strip().upper()}|{str(erro.get('CD_REF_CLT', '')).strip().upper()}|{str(erro.get('DETALHE_ERRO', '')).strip().upper()}|{str(erro.get('NF_MONTAGEM', '')).strip().upper()}|{str(erro.get('NF_PROGRAMACAO', '')).strip().upper()}|{str(erro.get('QT_PECA_NF_INCORRETA', '')).strip().upper()}"
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
    total_pecas_nf_incorreta: int = sum(
        int(erro.get("QT_PECA_NF_INCORRETA", 0) or 0) for erro in erros_atuais
    )
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

    novos_pecas_nf_incorreta: int = sum(
        int(erro.get("QT_PECA_NF_INCORRETA", 0) or 0) for erro in novos
    )
    corrigidos_pecas_nf_incorreta: int = sum(
        int(erro.get("QT_PECA_NF_INCORRETA", 0) or 0) for erro in corrigidos
    )
    permanentes_pecas_nf_incorreta: int = sum(
        int(erro.get("QT_PECA_NF_INCORRETA", 0) or 0) for erro in permanentes
    )

    tipo_notif: str = "NENHUMA"
    lembrete_enviado_em: str = str(cache_anterior.get("last_reminder_at", "")).strip()
    pode_enviar_lembrete: bool = False
    if lembrete_enviado_em:
        try:
            ts_lembrete = datetime.fromisoformat(lembrete_enviado_em)
            minutos = (datetime.now() - ts_lembrete).total_seconds() / 60.0
            pode_enviar_lembrete = minutos >= LEMBRETE_INTERVALO_MINUTOS
        except Exception:
            pode_enviar_lembrete = True
    else:
        pode_enviar_lembrete = True
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
        elif (
            total_erros > 0
            and permanentes
            and not novos
            and not corrigidos
            and pode_enviar_lembrete
        ):
            tipo_notif = "LEMBRETE"

    if tipo_notif != "NENHUMA":
        cache_tmp_file = cache_file + ".tmp"
        try:
            # Salva apenas no temporario. O commit ocorre no run.ps1 apos sucesso no e-mail.
            with open(cache_tmp_file, "w", encoding="utf-8") as f_out:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "itens": dic_atuais,
                        "last_reminder_at": (
                            datetime.now().isoformat()
                            if tipo_notif == "LEMBRETE"
                            else lembrete_enviado_em
                        ),
                    },
                    f_out,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            log(f"Falha ao gravar cache temporario: {e}", "WARN", exec_id)

        detalhes_html: str = ""
        subject: str = (
            f"Ação necessária: divergências NF x OB - Montagem Terceirizados - {datetime.now().strftime('%d/%m/%Y')}"
        )

        if tipo_notif == "ERRO":
            detalhes_html = gerar_tabela_completa_erros(erros_atuais)
        elif tipo_notif == "ALTERACAO":
            subject = f"Atualização de divergências NF x OB - Novos: {len(novos)} | Corrigidos: {len(corrigidos)} | Pendentes: {len(permanentes)} - {datetime.now().strftime('%d/%m/%Y')}"
            txt_novos: str = "Novo Erro" if len(novos) == 1 else "Novos Erros"
            txt_cor: str = (
                "Erro Corrigido" if len(corrigidos) == 1 else "Erros Corrigidos"
            )
            txt_perm: str = (
                "Erro Permanente" if len(permanentes) == 1 else "Erros Permanentes"
            )

            resumo_painel: str = (
                f"""<div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; padding:24px; margin: 30px 0; text-align:center;"><h3 style="margin:0 0 20px 0; color:#1f2937; font-size:14pt; font-weight:600;">Resumo da Atualização</h3><table border="0" cellspacing="0" cellpadding="0" style="margin: 0 auto; width: 100%; max-width: 720px; table-layout:fixed;"><tr><td align="center" style="padding: 0 10px;"><div style="background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#991b1b; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Novos</span><span style="display:block; font-size:28pt; color:#b91c1c; font-weight:bold; line-height:1;">{len(novos)}</span><span style="display:block; font-size:10pt; color:#7f1d1d; margin-top:6px;">{novos_pecas_nf_incorreta} peças</span></div></td><td align="center" style="padding: 0 10px;"><div style="background:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#166534; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Corrigidos</span><span style="display:block; font-size:28pt; color:#15803d; font-weight:bold; line-height:1;">{len(corrigidos)}</span><span style="display:block; font-size:10pt; color:#166534; margin-top:6px;">{corrigidos_pecas_nf_incorreta} peças</span></div></td><td align="center" style="padding: 0 10px;"><div style="background:#fff7ed; border:1px solid #fdba74; border-radius:8px; padding:16px;"><span style="display:block; font-size:11pt; color:#9a3412; margin-bottom:8px; text-transform:uppercase; font-weight:bold; letter-spacing:0.05em;">Permanentes</span><span style="display:block; font-size:28pt; color:#c2410c; font-weight:bold; line-height:1;">{len(permanentes)}</span><span style="display:block; font-size:10pt; color:#9a3412; margin-top:6px;">{permanentes_pecas_nf_incorreta} peças</span></div></td></tr></table></div>"""
            )
            detalhes_html = (
                resumo_painel
                + gerar_tabela_categoria_html(txt_novos, novos, "#b91c1c")
                + gerar_tabela_categoria_html(txt_cor, corrigidos, "#15803d")
                + gerar_tabela_categoria_html(txt_perm, permanentes, "#c2410c")
            )
        elif tipo_notif == "LEMBRETE":
            subject = f"Lembrete: pendências NF x OB - Montagem Terceirizados - {datetime.now().strftime('%d/%m/%Y')}"
            detalhes_html = gerar_tabela_categoria_html(
                "Pendências Permanentes", permanentes, "#c2410c"
            )
        elif tipo_notif == "ACERTO":
            subject = f"Validação OK: sem divergências NF x OB - Montagem Terceirizados - {datetime.now().strftime('%d/%m/%Y')}"
            detalhes_html = ""

        html_final: str = montar_template_email(
            tipo_notif,
            total_linhas,
            total_erros,
            total_pecas_nf_incorreta,
            len(novos),
            len(corrigidos),
            len(permanentes),
            detalhes_html,
        )
        result_payload: Dict[str, Any] = {
            "subject": subject,
            "html": html_final,
            "tipo_notificacao": tipo_notif,
            "total_linhas": total_linhas,
            "total_erros": total_erros,
            "total_pecas_nf_incorreta": total_pecas_nf_incorreta,
            "novos": len(novos),
            "novos_pecas_nf_incorreta": novos_pecas_nf_incorreta,
            "corrigidos": len(corrigidos),
            "corrigidos_pecas_nf_incorreta": corrigidos_pecas_nf_incorreta,
            "permanentes": len(permanentes),
            "permanentes_pecas_nf_incorreta": permanentes_pecas_nf_incorreta,
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

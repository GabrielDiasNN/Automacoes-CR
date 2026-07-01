# -*- coding: utf-8 -*-
import json
import os
import sys
from datetime import datetime
from typing import Any

# Forca UTF-8 para garantir interoperabilidade
if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Configura o stdin para ler UTF-8-SIG do PowerShell (limpando o BOM automaticamente)
if hasattr(sys.stdin, "encoding") and sys.stdin.encoding != "utf-8-sig":
    try:
        sys.stdin.reconfigure(encoding="utf-8-sig")  # type: ignore[union-attr]
    except AttributeError:
        pass  # Evita falha durante testes (ex: pytest mock de stdin)


def log(message: str, level: str = "INFO", exec_id: str = "manual") -> None:
    """Envia logs para o stderr."""
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    raw_msg = f"[{ts}] [PY-HTML] [{level}] [ExecId:{exec_id}] {message}"
    sys.stderr.write(f"{raw_msg}\n")
    sys.stderr.flush()


def html_escape(text: Any) -> str:
    if not text:
        return "&nbsp;"
    s = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
    char_map = {
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


def generate_html() -> str:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    exec_id: str = sys.argv[1] if len(sys.argv) > 1 else "manual"
    script_dir: str = os.path.dirname(os.path.abspath(__file__))
    config_path: str = os.path.join(script_dir, "receitas_config.json")

    # 1. Carregar Dados via STDIN (IPC)
    try:
        log("Lendo dados do stdin...", "INFO", exec_id)
        input_data: str = sys.stdin.read()
        if not input_data:
            log("Nenhum dado recebido via stdin.", "ERROR", exec_id)
            sys.exit(1)
        data: list[dict[str, Any]] = json.loads(input_data)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log(f"Falha ao decodificar JSON do stdin: {e}", "ERROR", exec_id)
        sys.exit(1)

    # 2. Carregar Config
    try:
        if not os.path.exists(config_path):
            log(f"Configuracao nao encontrada: {config_path}", "ERROR", exec_id)
            sys.exit(1)
        with open(config_path, "r", encoding="utf-8") as f:
            config: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log(f"Erro ao carregar configuracoes: {e}", "ERROR", exec_id)
        sys.exit(1)

    if not data:
        log("Conjunto de dados vazio.", "WARN", exec_id)
        return ""

    # 3. Agrupar e Ordenar Dados
    data_sorted = sorted(
        data,
        key=lambda x: (
            x.get("INICIO_TING") or "9999-12-31",
            str(x.get("GRUPO") or "0"),
            str(x.get("NUMERO_OB") or ""),
        ),
    )

    machines: dict[str, dict[str, Any]] = {}
    total_weight: int = 0
    max_machine_weight: int = 0
    recipe_count: int = 0

    for row in data_sorted:
        mq = str(row.get("MQ_TING") or "SEM MAQ").strip()
        grupo = str(row.get("GRUPO") or "0").strip()
        ob = str(row.get("NUMERO_OB") or "")
        inicio = row.get("INICIO_TING") or ""

        if inicio and "T" in inicio:
            try:
                dt = datetime.fromisoformat(inicio)
                inicio = dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass

        if mq not in machines:
            machines[mq] = {"groups": {}, "weight": 1, "recipes": 0}

        if grupo not in machines[mq]["groups"]:
            machines[mq]["groups"][grupo] = []
            if grupo != "0":
                machines[mq]["weight"] += 1
                machines[mq]["recipes"] += 1

        machines[mq]["groups"][grupo].append({"ob": ob, "inicio": inicio})
        machines[mq]["weight"] += 1
        if grupo == "0":
            machines[mq]["recipes"] += 1

    machine_count = len(machines)
    for mq, machine_data in machines.items():
        total_weight += machine_data["weight"]
        recipe_count += machine_data["recipes"]
        if machine_data["weight"] > max_machine_weight:
            max_machine_weight = machine_data["weight"]

    # 4. Logica de Layout Adaptativo
    volume_score = (
        total_weight + (machine_count * 2.2) + max_machine_weight + (recipe_count / 3)
    )
    compress_factor = min(1.0, (volume_score - 54) / 72) if volume_score > 54 else 0
    column_count = (
        3
        if (volume_score >= 72 or max_machine_weight >= 16 or machine_count >= 11)
        else 2
    )
    container_width = 696 if column_count == 3 else 680
    column_gap = max(6, int(14 - (compress_factor * 8)))
    outer_pad = max(4, int(12 - (compress_factor * 6)))

    title_font = max(10.5, 13.5 - (compress_factor * 2.7))
    meta_font = max(6.3, 8.4 - (compress_factor * 1.8))
    section_font = max(6.1, 8.4 - (compress_factor * 2.0))
    header_font = max(5.9, 7.9 - (compress_factor * 1.8))
    body_font = max(5.6, 7.8 - (compress_factor * 2.2))

    title_line = max(13, int(title_font * 1.35))
    meta_line = max(9, int(meta_font * 1.35))
    section_line = max(9, int(section_font * 1.35))
    header_line = max(8, int(header_font * 1.35))
    body_line = max(8, int(body_font * 1.35))

    row_pad_y = max(1, int(4 - (compress_factor * 3)))
    row_pad_x = max(3, int(6 - (compress_factor * 3)))
    block_pad_y = max(3, int(6 - (compress_factor * 3)))
    spacer_height = max(2, int(6 - (compress_factor * 4)))

    column_width = (container_width - ((column_count - 1) * column_gap)) // column_count
    ob_width = int(column_width * 0.47)
    inicio_width = column_width - ob_width

    # 5. Distribuicao das Maquinas
    columns_html = ["" for _ in range(column_count)]
    columns_current_weight = [0 for _ in range(column_count)]
    sorted_machines = sorted(machines.keys())

    for mq_name in sorted_machines:
        mq_data = machines[mq_name]
        best_col = columns_current_weight.index(min(columns_current_weight))

        html = f"""
        <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='{column_width}' style='width:{column_width}px;margin:0;page-break-inside:avoid;'>
            <tr>
                <td colspan='2' align='center' style='padding:{block_pad_y}px {row_pad_x}px;border:1px solid #000000;background-color:#E9EEF7;font-size:{section_font:.1f}pt;font-weight:bold;line-height:{section_line}px;text-align:center;'>
                    {html_escape(mq_name)} | {mq_data['recipes']} receita{'s' if mq_data['recipes'] != 1 else ''}
                </td>
            </tr>
        """

        for g_name in sorted(mq_data["groups"].keys()):
            if g_name != "0":
                html += f"<tr><td colspan='2' align='center' style='padding:{row_pad_y}px {row_pad_x}px;border-left:1px solid #000000;border-right:1px solid #000000;border-bottom:1px solid #D9D9D9;background-color:#F2F2F2;font-size:{header_font:.1f}pt;font-weight:bold;line-height:{header_line}px;text-align:center;'>Grupo {html_escape(g_name)}</td></tr>"

            for item in mq_data["groups"][g_name]:
                html += f"<tr><td width='{ob_width}' style='width:{ob_width}px;padding:{row_pad_y}px {row_pad_x}px;border-left:1px solid #000000;border-bottom:1px solid #D9D9D9;font-size:{body_font:.1f}pt;line-height:{body_line}px;color:#000000;white-space:nowrap;'>{html_escape(item['ob'])}</td><td width='{inicio_width}' align='center' style='width:{inicio_width}px;padding:{row_pad_y}px {row_pad_x}px;border-right:1px solid #000000;border-bottom:1px solid #D9D9D9;font-size:{body_font:.1f}pt;line-height:{body_line}px;color:#000000;white-space:nowrap;text-align:center;'>{html_escape(item['inicio'])}</td></tr>"

        html += f"<tr><td colspan='2' style='height:{spacer_height}px;font-size:0;line-height:0;border-left:1px solid #000000;border-right:1px solid #000000;border-bottom:1px solid #000000;'>&nbsp;</td></tr></table>"
        html += f"<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='{column_width}' style='width:{column_width}px;'><tr><td height='{spacer_height}' style='height:{spacer_height}px;font-size:0;line-height:0;'>&nbsp;</td></tr></table>"

        columns_html[best_col] += html
        columns_current_weight[best_col] += mq_data["weight"]

    # 6. Montar HTML
    header_row = ""
    content_row = ""
    for i in range(column_count):
        header_row += f"<td width='{column_width}' align='center' valign='middle' style='width:{column_width}px;padding:{block_pad_y}px {row_pad_x}px;border:1px solid #000000;background-color:#D9E2F3;font-size:{header_font:.1f}pt;font-weight:bold;line-height:{header_line}px;text-align:center;'>Máquina / Grupo / OB / Início</td>"
        content_row += f"<td width='{column_width}' valign='top' style='width:{column_width}px;padding-top:{block_pad_y}px;vertical-align:top;'>{columns_html[i] or '&nbsp;'}</td>"
        if i < column_count - 1:
            header_row += f"<td width='{column_gap}' style='width:{column_gap}px;font-size:0;line-height:0;'>&nbsp;</td>"
            content_row += f"<td width='{column_gap}' style='width:{column_gap}px;font-size:0;line-height:0;'>&nbsp;</td>"

    full_html = f"""<html><body style='margin:0;padding:0;background-color:#FFFFFF;'><div class='WordSection1'>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;background-color:#FFFFFF;border-collapse:collapse;'>
    <tr><td align='center' style='padding:{outer_pad}px;'>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='{container_width}' style='width:{container_width}px;background-color:#FFFFFF;border-collapse:collapse;'>
    <tr><td style='padding:{block_pad_y}px {row_pad_x}px;border:1px solid #D9E2F3;background-color:#FFFFFF;'>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;border-collapse:collapse;'>
    <tr><td align='center' style='padding:0 0 2px 0;font-size:{title_font:.1f}pt;font-weight:bold;line-height:{title_line}px;color:#000000;text-align:center;'>{html_escape(config['layout']['title'])}</td></tr>
    <tr><td align='center' style='padding:0 0 2px 0;font-size:{meta_font:.1f}pt;line-height:{meta_line}px;color:#333333;text-align:center;'>{html_escape(config['layout']['subtitle'])}</td></tr>
    <tr><td align='center' style='padding:0 0 {block_pad_y}px 0;font-size:{meta_font:.1f}pt;line-height:{meta_line}px;color:#333333;text-align:center;'>Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Máquinas: {machine_count} | Receitas: {recipe_count}</td></tr>
    </table>
    <table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;border-collapse:collapse;'>
    <tr>{header_row}</tr><tr>{content_row}</tr>
    </table></td></tr></table></td></tr></table></div></body></html>"""

    # Envia o HTML final para STDOUT (IPC)
    sys.stdout.write(full_html)
    sys.stdout.flush()
    log("Relatório HTML gerado com sucesso para stdout.", "INFO", exec_id)
    return full_html


if __name__ == "__main__":
    generate_html()

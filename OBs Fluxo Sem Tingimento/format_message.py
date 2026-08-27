# pylint: disable=broad-exception-caught, wrong-import-position
# {
#   "version": "1.0.0",
#   "contract": "exit-0=message.txt-gerado, exit-2=nada-a-enviar, exit-1=erro",
#   "description": "Le ofst_result.json e gera message.txt no template do grupo Expedicao Tinturaria"
# }
"""Camada de apresentacao do OFST-06.

Le ofst_result.json (ja validado pelo extrator) e escreve message.txt. O envio
em si e do run.ps1 via lib/Send-WhatsApp.ps1 — este script nao conhece WhatsApp,
so texto.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "python")
)

from automation_log import ensure_utf8_streams, make_logger

ensure_utf8_streams()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "ofst_result.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")

log = make_logger("OFST-FORMAT")


def _fmt_entrega(valor: Any) -> str:
    """DT_ENTREGA chega em isoformat (serialize_rows); exibe dd/mm/aaaa ou '—'."""
    if not valor:
        return "—"
    try:
        return datetime.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


def _fmt_artigo(valor: Any) -> str:
    """Artigo cru e texto alfanumerico no Oracle ('0A231'); exibe sem truncar.

    Codigo puramente numerico continua saindo sem os zeros a esquerda, como
    quando o campo ainda era coagido para int — a mudanca de tipo em
    `coerce_ob_row` nao deve alterar a mensagem que a Expedicao ja conhece.
    """
    if valor is None:
        return "—"
    texto = str(valor).strip()
    if not texto:
        return "—"
    try:
        return str(int(texto))
    except (TypeError, ValueError):
        return texto


def _bloco_ob(row: dict[str, Any]) -> str:
    artigo = row.get("CODIGO_ARTIGO_CRU")
    filial = row.get("NOME_CLIENTE")
    return (
        f"*OB: {row['NUMERO_OB']}*\n"
        f"Artigo: {_fmt_artigo(artigo)}\n"
        f"Reduzido: {row['CODIGO_REDUZIDO_CRU']}\n"
        f"Quantidade necessária: {row['TOTAL_PECAS']} peças\n"
        f"Estoque disponível: {row['QTD_PECAS_DISPONIVEIS']} peças\n"
        f"Data de entrega: {_fmt_entrega(row.get('DT_ENTREGA'))}\n"
        f"Filial destino: {filial if filial else '—'}\n"
        f"Status: ✅ Pronta para montagem"
    )


def build_message(payload: dict[str, Any]) -> str:
    """Monta a mensagem final. Funcao pura — testada sem I/O.

    Tempo de consulta e grupo destino ficam FORA da mensagem (irrelevantes para
    os integrantes do grupo) — seguem disponiveis em ofst_result.json (resumo)
    e nos logs do extrator para observabilidade.
    """
    rows: list[dict[str, Any]] = payload.get("rows", [])

    titulo = "🎯 *Depósito 95 - OBs Fluxo Sem Tingimento*"
    if len(rows) > 1:
        titulo += f"\n_{len(rows)} OBs prontas para montagem_"

    corpo = "\n\n".join(_bloco_ob(row) for row in rows)
    return f"{titulo}\n\n{corpo}\n"


def main() -> None:
    exec_id = sys.argv[1] if len(sys.argv) > 1 else "manual"

    if not os.path.exists(RESULT_FILE):
        log("ofst_result.json nao encontrado.", "ERROR", exec_id)
        sys.exit(1)

    try:
        with open(RESULT_FILE, encoding="utf-8") as f:
            payload: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log(f"Falha ao ler ofst_result.json: {e}", "ERROR", exec_id)
        sys.exit(1)

    if not payload.get("rows"):
        log("Nenhuma OB a notificar.", "INFO", exec_id)
        sys.exit(2)

    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        f.write(build_message(payload))

    log(f"message.txt gerado com {len(payload['rows'])} OB(s).", "INFO", exec_id)
    sys.exit(0)


if __name__ == "__main__":
    main()

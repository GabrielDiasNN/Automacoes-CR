# pylint: disable=broad-exception-caught
# {
#   "version": "1.0.0",
#   "contract": "exit-0=message.txt-gerado, exit-2=nada-a-enviar, exit-1=erro",
#   "description": "Le orb_result.json e gera message.txt no template do grupo Expedicao Tinturaria"
# }
"""Camada de apresentacao do ORB-07.

Le orb_result.json (ja validado pelo extrator) e escreve message.txt. O envio
em si e do run.ps1 via lib/Send-WhatsApp.ps1 — este script nao conhece WhatsApp,
so texto.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(SCRIPT_DIR, "orb_result.json")
MESSAGE_FILE = os.path.join(SCRIPT_DIR, "message.txt")


def _fmt_codigo(valor: Any, largura: int) -> str:
    """Exibe códigos numéricos com largura mínima, sem truncar valores.

    O Oracle pode devolver artigo como NUMBER (perdendo zeros à esquerda) e
    cor como texto preenchido. Converter primeiro para inteiro garante o
    padrão de comunicação (artigo com 3 dígitos e cor com 2), enquanto manter
    códigos maiores que a largura evita mascarar um dado inesperado.
    """
    if valor is None:
        return "—"
    texto = str(valor).strip()
    if not texto:
        return "—"
    try:
        numero = int(texto)
    except (TypeError, ValueError):
        return texto
    return f"{numero:0{largura}d}"


def _fmt_restricoes(row: dict[str, Any]) -> tuple[str, str]:
    """Retorna (rótulo, valor) das finalidades presentes no saldo distinto."""
    itens = row.get("RESTRICOES_DISPONIVEIS") or []
    restricoes: list[str] = []
    if isinstance(itens, list):
        for item in itens:
            if not isinstance(item, dict):
                continue
            codigo = item.get("codigo")
            descricao = str(item.get("descricao") or "").strip()
            if codigo is None or not descricao:
                continue
            restricoes.append(f"{_fmt_codigo(codigo, 1)} — {descricao}")

    # Sem branch de compatibilidade com o payload legado (CODIGO_RESTRICAO/
    # DESCRICAO_RESTRICAO): o extrator sempre grava RESTRICOES_DISPONIVEIS, o
    # orb_result.json é regravado a cada ciclo e está no .gitignore. A defesa era
    # morta de qualquer forma — `_bloco_ob` indexa direto (row['CODIGO_FLUXO'] etc.)
    # e o payload legado levantaria KeyError duas linhas adiante.
    if not restricoes:
        return "Restrição da peça", "—"
    rotulo = "Restrição da peça" if len(restricoes) == 1 else "Restrições da peça"
    return rotulo, "; ".join(restricoes)


def _fmt_entrega(valor: Any) -> str:
    """DT_ENTREGA chega em isoformat (serialize_rows); exibe dd/mm/aaaa ou '—'."""
    if not valor:
        return "—"
    try:
        return datetime.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


def _bloco_ob(row: dict[str, Any], descontado: bool = False) -> str:
    artigo = row.get("CODIGO_ARTIGO_CRU")
    filial = row.get("NOME_CLIENTE")
    cor = row.get("CODIGO_COR_TINGIMENTO")
    rotulo_restricao, restricoes = _fmt_restricoes(row)
    # `descontado`: uma OB anterior DESTA mensagem ja consumiu o mesmo reduzido.
    # QTD_PECAS_DISPONIVEIS e o saldo no momento da avaliacao daquela OB (ver
    # alocar_estoque), entao sem essa ressalva o mesmo deposito parece ter um
    # estoque diferente em cada bloco (809 -> 754 -> 699 ... na mesma mensagem).
    #
    # Limitacao conhecida (item 10 da revisao de 26/08/2026): `vistos` em
    # build_message so' enxerga reduzidos repetidos DENTRO de `rows`, que contem
    # so' as OBs novas deste ciclo. Quando o saldo exibido ja foi reduzido por
    # OBs de ciclos anteriores (via `reservado`) ou por OBs ja notificadas do
    # mesmo ciclo, a ressalva nao aparece — o numero parece estoque bruto do
    # deposito, que e exatamente o que ela existe para evitar. Corrigir exige
    # levar o estoque bruto ate orb_result.json; nao corrigido por ora
    # (custo/beneficio — avaliar se voltar a incomodar operacionalmente).
    sufixo_estoque = " (após as OBs acima)" if descontado else ""
    return (
        f"*OB: {row['NUMERO_OB']}*\n"
        f"Fluxo: {row['CODIGO_FLUXO']}\n"
        f"Cor programada: {_fmt_codigo(cor, 2)}\n"
        f"Classificação: {row['DS_CLASSIFICACAO_COR']}\n"
        f"{rotulo_restricao}: {restricoes}\n"
        f"Artigo: {_fmt_codigo(artigo, 3)}\n"
        f"Reduzido: {row['CODIGO_REDUZIDO_CRU']}\n"
        f"Quantidade necessária: {row['TOTAL_PECAS']} peças\n"
        f"Estoque disponível: {row['QTD_PECAS_DISPONIVEIS']} peças{sufixo_estoque}\n"
        f"Data de entrega: {_fmt_entrega(row.get('DT_ENTREGA'))}\n"
        f"Filial destino: {filial if filial else '—'}\n"
        f"Status: ✅ Pronta para montagem"
    )


def build_message(payload: dict[str, Any]) -> str:
    """Monta a mensagem final. Funcao pura — testada sem I/O.

    Tempo de consulta e grupo destino ficam FORA da mensagem (irrelevantes para
    os integrantes do grupo) — seguem disponiveis em orb_result.json (resumo)
    e nos logs do extrator para observabilidade.
    """
    rows: list[dict[str, Any]] = payload.get("rows", [])

    titulo = "🎯 *Depósito 95 - OBs Restrição Branco*"
    if len(rows) > 1:
        titulo += f"\n_{len(rows)} OBs prontas para montagem_"

    # Um reduzido ja citado antes na mesma mensagem significa que o saldo do
    # bloco atual ja esta descontado das OBs anteriores.
    vistos: set[Any] = set()
    blocos: list[str] = []
    for row in rows:
        reduzido = row.get("CODIGO_REDUZIDO_CRU")
        blocos.append(_bloco_ob(row, descontado=reduzido in vistos))
        vistos.add(reduzido)

    corpo = "\n\n".join(blocos)
    return f"{titulo}\n\n{corpo}\n"


def main() -> None:
    """Lê o resultado validado e grava o preview textual do aviso."""
    if not os.path.exists(RESULT_FILE):
        sys.stderr.write("[ERROR] orb_result.json nao encontrado.\n")
        sys.exit(1)

    try:
        with open(RESULT_FILE, encoding="utf-8") as f:
            payload: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[ERROR] Falha ao ler orb_result.json: {e}\n")
        sys.exit(1)

    if not payload.get("rows"):
        sys.stderr.write("[INFO] Nenhuma OB a notificar.\n")
        sys.exit(2)

    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        f.write(build_message(payload))

    sys.stderr.write(f"[INFO] message.txt gerado com {len(payload['rows'])} OB(s).\n")
    sys.exit(0)


if __name__ == "__main__":
    main()

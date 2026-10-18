"""Decisão por regra fixa da revisão de SQL de produção, lida dos JSONs de evidência.

O workflow `.claude/workflows/revisao-sql-producao-oracle.js` usa este script como
fonte única da decisão: os campos que o agente transcreve servem só para exibição.
Lê, para uma unidade, os artefatos que o passo Validar grava em disco (validar,
medições do HEAD e da versão de trabalho, comparação de equivalência e o texto cru)
e imprime um JSON com `acao` e `motivo`. Com `--exigir ACAO`, sai com código 1
quando a decisão calculada for outra — o passo Aplicar só reverte com exit 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from medir_sql_oracle import DEFAULT_MIN_GAIN_PCT, decide  # noqa: E402

_COMENTARIO_OU_LITERAL = re.compile(r"/\*.*?\*/|--[^\n]*|'(?:[^']|'')*'", re.S)


def _ler_json(caminho: Path) -> dict[str, Any] | None:
    try:
        dado = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dado if isinstance(dado, dict) else None


def sem_ponto_e_virgula(sql: str) -> bool:
    """True se não houver ';' fora de comentários e literais (o runner falharia)."""
    return ";" not in _COMENTARIO_OU_LITERAL.sub(" ", sql)


def _d(acao: str, motivo: str) -> dict[str, str]:
    return {"acao": acao, "motivo": motivo}


def _evidencia_basica(
    prefixo: Path, sql_wt: Path
) -> tuple[dict[str, str] | None, tuple[dict[str, Any], dict[str, Any]] | None]:
    """Texto cru, validação e medições. Devolve (decisão final, None) ou (None, resumos)."""
    try:
        texto = sql_wt.read_text(encoding="utf-8")
    except OSError:
        return _d("pendente", f"texto cru ilegível: {sql_wt}"), None
    if not sem_ponto_e_virgula(texto):
        motivo = "texto cru tem ponto e vírgula: o runner falha com ORA-00933"
        return _d("reverter_head", motivo), None
    validar = _ler_json(Path(f"{prefixo}-validar-wt.json"))
    head = _ler_json(Path(f"{prefixo}-head-medicao.json"))
    wt = _ler_json(Path(f"{prefixo}-wt-medicao.json"))
    if validar is None or head is None or wt is None:
        return _d("pendente", "evidência de validação ou medição ausente"), None
    if validar.get("status") != "validated":
        return _d("reverter_head", "versão de trabalho não passa parse/smoke"), None
    resumo_head, resumo_wt = head.get("summary"), wt.get("summary")
    if not resumo_head or not resumo_wt:
        return _d("pendente", "medição sem summary"), None
    return None, (resumo_head, resumo_wt)


def _decidir_por_saida(
    prefixo: Path, resumo_head: dict[str, Any], resumo_wt: dict[str, Any]
) -> dict[str, str]:
    """Paridade de saída (equivalência) e, com paridade, ganho medido."""
    equivalencia = _ler_json(Path(f"{prefixo}-equivalencia.json"))
    if equivalencia is None:
        return _d("pendente", "relatório de equivalência ausente")
    divergencias = equivalencia.get("divergences") or []
    if divergencias:
        return _d(
            "reverter_head", f"saída diverge do HEAD ({len(divergencias)} divergências)"
        )
    veredito = decide(resumo_head, resumo_wt, DEFAULT_MIN_GAIN_PCT)["verdict"]
    if veredito == "MELHORA":
        return _d("manter_wt", "saída igual ao HEAD e ganho medido")
    return _d("reverter_head", f"sem ganho medido (veredito: {veredito})")


def decidir(
    prefixo: Path,
    sql_wt: Path,
    *,
    tem_wt_diferente: bool,
    correcao_aprovada: bool = False,
) -> dict[str, str]:
    """Aplica a regra fixa sobre os arquivos `<prefixo>-*.json` da unidade."""
    if not tem_wt_diferente:
        return _d("manter", "HEAD e versão de trabalho idênticos")
    final, resumos = _evidencia_basica(prefixo, sql_wt)
    if final is not None or resumos is None:
        return final or _d("pendente", "evidência incompleta")
    resumo_head, resumo_wt = resumos
    if correcao_aprovada:
        # Correção aprovada muda a saída por decisão registrada: a paridade não se
        # aplica, só o teto de custo de 2x a mediana do HEAD.
        if float(resumo_wt["median_ms"]) <= 2 * float(resumo_head["median_ms"]):
            return _d("manter_wt", "correção aprovada, custo dentro de 2x")
        return _d("reverter_head", "correção aprovada, mas custo acima de 2x")
    return _decidir_por_saida(prefixo, resumo_head, resumo_wt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefixo", type=Path, required=True)
    parser.add_argument("--sql-wt", type=Path, required=True)
    parser.add_argument("--tem-wt-diferente", action="store_true")
    parser.add_argument("--correcao-aprovada", action="store_true")
    parser.add_argument("--exigir", help="Sai com 1 se a decisão calculada for outra")
    args = parser.parse_args(argv)
    decisao = decidir(
        args.prefixo,
        args.sql_wt,
        tem_wt_diferente=args.tem_wt_diferente,
        correcao_aprovada=args.correcao_aprovada,
    )
    print(json.dumps(decisao, ensure_ascii=False))
    if args.exigir and decisao["acao"] != args.exigir:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

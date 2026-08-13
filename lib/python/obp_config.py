"""Configuracao compartilhada de fases monitoradas para OBP-04 (OBs Paradas Fase).

`format_message.py` e `generate_phase_cards.py` definiam `DEFAULT_FASES_MONITORADAS`
e as funcoes auxiliares que a consomem de forma independente. Ao longo do tempo os
dois arquivos divergiram em `threshold_dias` e no responsavel de algumas fases, o que
podia fazer a mensagem de texto e o card de imagem da MESMA execucao reportarem
conjuntos diferentes de OBs paradas para o mesmo destinatario (achado de revisao
OBP-04 Q1, severidade critica). Este modulo passa a ser a fonte unica de verdade
para os dois scripts, seguindo a convencao de `lib/python/` do projeto para codigo
compartilhado entre scripts de dominio (CLAUDE.md).

Reconciliacao dos valores que divergiam entre os dois arquivos: `generate_phase_cards.py`
foi adotado como fonte da verdade (arquivo mais recentemente mantido — inclui a fase 47,
ausente em format_message.py, e um contato dedicado `_LIDER_CQ` para a fase 160 em vez
do fallback generico `_EQUIPE_QUALIDADE`). Os valores abaixo refletem exatamente o que
estava em `generate_phase_cards.py` antes desta consolidacao:

- Fase 20 (RMC): threshold_dias = 1 (format_message.py tinha 3)
- Fase 45 (CDC): threshold_dias = 0.1 (format_message.py tinha 0.5)
- Fase 46 (PPA): threshold_dias = 1 (format_message.py tinha 0.25)
- Fase 47 (UMM): ausente em format_message.py, incluida aqui
- Fase 160 (CDQ): responsavel = _LIDER_CQ (format_message.py usava _EQUIPE_QUALIDADE)
- Fase 165 (CDF): threshold_dias = 0.1 (format_message.py tinha 1)
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


def _join_responsavel(numeros: list[Any]) -> str:
    return " @".join(str(x).strip() for x in numeros if str(x).strip())


def _resolve_contato(contato: Any) -> str:
    """Resolve uma entrada de 'contatos': objeto {nome, numero}, lista desses, ou string legada."""
    if isinstance(contato, list):
        return _join_responsavel(
            [c.get("numero", "") if isinstance(c, dict) else c for c in contato]
        )
    if isinstance(contato, dict):
        return str(contato.get("numero", "")).strip()
    return str(contato).strip()


@dataclass
class FaseConfig:
    descricao: str
    threshold_dias: float
    responsavel: str
    ativo: bool = True


# Contatos reais (nome/numero) nunca ficam no codigo-fonte nem no config.json —
# vivem só no .env local (nao versionado), lido via os.environ pelo run.ps1/Lib-Config.psm1.
# Sem .env configurado, o fallback abaixo fica vazio e a mensagem sai sem mencao.
_LIDER_1_TURNO = os.environ.get("OBP_CONTATO_LIDER_1_TURNO", "")
_LIDER_RESERVA_1_TURNO = os.environ.get("OBP_CONTATO_LIDER_RESERVA_1_TURNO", "")
_LIDER_2_TURNO = os.environ.get("OBP_CONTATO_LIDER_2_TURNO", "")
_LIDER_RESERVA_2_TURNO = os.environ.get("OBP_CONTATO_LIDER_RESERVA_2_TURNO", "")
_LIDER_3_TURNO = os.environ.get("OBP_CONTATO_LIDER_3_TURNO", "")
_LIDER_RESERVA_3_TURNO = os.environ.get("OBP_CONTATO_LIDER_RESERVA_3_TURNO", "")
_LIDER_CQ = os.environ.get("OBP_CONTATO_LIDER_CQ", "")
_EQUIPE_QUALIDADE = _join_responsavel(
    os.environ.get("OBP_CONTATO_EQUIPE_CQ", "").split(",")
)

DEFAULT_FASES_MONITORADAS: dict[str, FaseConfig] = {
    "20": FaseConfig("RMC-REVISÃO MALHA CRUA", 1, _LIDER_3_TURNO),
    "25": FaseConfig("CDP-CONFERENCIA DE PESO", 0.5, _EQUIPE_QUALIDADE, ativo=False),
    "26": FaseConfig("IVF-INVERSÃO P/FELPAGEM", 1, _LIDER_3_TURNO),
    "45": FaseConfig("CDC-CONFERENCIA DE COR", 0.1, _LIDER_RESERVA_3_TURNO),
    "46": FaseConfig("PPA-PREPARAÇÃO AMACIANTE", 1, _LIDER_1_TURNO),
    "47": FaseConfig("UMM-UMEDECIMENTO DE MALHA", 0.5, _LIDER_RESERVA_3_TURNO),
    "50": FaseConfig("HID-HIDRO UMIDO", 1, _LIDER_1_TURNO),
    "55": FaseConfig("HIS-HIDRO SECO", 1, _LIDER_1_TURNO),
    "60": FaseConfig("SEC-SECADOR", 1, _LIDER_1_TURNO),
    "65": FaseConfig("FEL-FELPAGEM", 1, _LIDER_RESERVA_1_TURNO),
    "70": FaseConfig("CLB-CALANDRA DE BRILHO", 1, _LIDER_RESERVA_1_TURNO),
    "80": FaseConfig("CLC-CALANDRA DE COMPACTACAO", 1, _LIDER_RESERVA_1_TURNO),
    "90": FaseConfig("ABR-ABRIDOR", 1, _LIDER_2_TURNO),
    "100": FaseConfig("RAU-RAMAR UMIDO", 1, _LIDER_2_TURNO),
    "110": FaseConfig("RAS-RAMAR SECO", 1, _LIDER_2_TURNO),
    "150": FaseConfig("EXP-EXPEDICAO ACABADO", 1, _LIDER_RESERVA_2_TURNO),
    "160": FaseConfig("CDQ-CONTROLE DE QUALIDADE", 1, _LIDER_CQ),
    "165": FaseConfig("CDF-CONFERÊNCIA DE FELPA", 0.1, _EQUIPE_QUALIDADE),
}
DEFAULT_PHASE_ORDER: list[int] = [
    20,
    46,
    47,
    50,
    55,
    60,
    90,
    100,
    110,
    26,
    65,
    25,
    45,
    80,
    70,
    160,
    165,
    150,
]
DEFAULT_MAX_OBS = 10

_PREFIX_RE = re.compile(r"^[A-Z0-9]{2,5}-")


def normalize_fase(fase: str) -> str:
    clean = _PREFIX_RE.sub("", fase.strip()).upper().strip()

    mapeamentos = {
        "EXPEDICAO ACABADO": "Expedição Acabado",
        "RAMAR UMIDO": "Ramar Úmido",
        "CALANDRA DE COMPACTACAO": "Calandra de Compactação",
        "CONFERENCIA": "Conferência",
        "REVISAO MALHA CRUA": "Revisão Malha Crua",
        "REVISAO": "Revisão",
        "PRODUCAO": "Produção",
        "COMPACTACAO": "Compactação",
    }

    if clean in mapeamentos:
        return mapeamentos[clean]

    return clean.title()


def _codigo_fase_key(ob: dict[str, Any]) -> str | None:
    """Normaliza CODIGO_FASE (int/float/str vindos do Oracle) para a chave usada em fases_monitoradas."""
    raw = ob.get("CODIGO_FASE")
    if raw is None:
        return None
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return None


def get_fase_config(
    codigo_key: str | None, fases_monitoradas: dict[str, FaseConfig]
) -> FaseConfig | None:
    if codigo_key is None:
        return None
    return fases_monitoradas.get(codigo_key)


def fmt_dias(dias: Any) -> str:
    try:
        return f"{float(dias):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(dias)


def fmt_kg(kilos: Any) -> str:
    try:
        return f"{float(kilos):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(kilos)


def _phase_sort_key(codigo_fase: int, ordem: list[int]) -> int:
    return ordem.index(codigo_fase) if codigo_fase in ordem else len(ordem)


def group_obs_by_phase(
    filtradas: list[dict[str, Any]],
    phase_order: list[int],
) -> list[tuple[int, list[dict[str, Any]]]]:
    """Agrupa OBs filtradas por CODIGO_FASE e ordena fases/OBs por criticidade.

    Nao aplica nenhum teto de quantidade — cada script chamador aplica seu proprio
    limite (max_obs, altura de card, etc.) sobre o resultado, mas ambos partem do
    MESMO conjunto de fases. Antes desta funcao existir, format_message.py cortava
    max_obs GLOBALMENTE antes de agrupar (podendo excluir fases inteiras por
    saturacao de outra fase mais critica) enquanto generate_phase_cards.py agrupava
    por fase primeiro — a mesma execucao podia reportar conjuntos de fases
    diferentes na mensagem de texto e nos cards de imagem (achado de revisao
    OBP-04 Q1, mesma classe de bug que motivou a criacao deste modulo).
    """
    grupos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ob in filtradas:
        codigo = int(float(ob.get("CODIGO_FASE") or 0))
        grupos[codigo].append(ob)
    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda kv: (
            _phase_sort_key(kv[0], phase_order),
            -max(o["_dias_float"] for o in kv[1]),
        ),
    )
    for _, obs_fase in grupos_ordenados:
        obs_fase.sort(key=lambda o: o["_dias_float"], reverse=True)
    return grupos_ordenados


def _apply_phase_filter(
    ob: dict[str, Any], codigo_key: str | None, phase_filters: dict[str, Any]
) -> bool:
    """Retorna True se o OB deve ser ignorado (filtro não satisfeito)."""
    regras = phase_filters.get(codigo_key) if codigo_key is not None else None
    if not regras:
        return False
    for campo, valor_esperado in regras.items():
        raw = ob.get(campo)
        try:
            val: Any = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            val = raw
        if val != valor_esperado:
            return True
    return False


def _filter_obs(
    obs: list[dict[str, Any]],
    fases_monitoradas: dict[str, FaseConfig],
    phase_filters: dict[str, Any],
) -> list[dict[str, Any]]:
    filtradas: list[dict[str, Any]] = []
    for ob in obs:
        codigo_key = _codigo_fase_key(ob)
        cfg = get_fase_config(codigo_key, fases_monitoradas)
        if cfg is None or not cfg.ativo:
            continue
        try:
            dias = float(ob.get("DIAS_PARADO") or 0)
        except (TypeError, ValueError):
            continue
        if dias < cfg.threshold_dias:
            continue
        if _apply_phase_filter(ob, codigo_key, phase_filters):
            continue
        filtradas.append({**ob, "_threshold": cfg.threshold_dias, "_dias_float": dias})
    return filtradas


def _load_contatos_from_env() -> dict[str, str]:
    """Mesmas chaves de referencia de 'responsavel' em fases_monitoradas, valor lido do .env.

    Le os.environ diretamente (em vez dos modulos `_LIDER_*` capturados na importacao
    deste modulo) porque `obp_config` e importado uma unica vez por processo: uma vez
    em `sys.modules`, seu corpo nao roda de novo, entao os testes que fazem
    `monkeypatch.setenv(...)` antes de recarregar dinamicamente format_message.py/
    generate_phase_cards.py so veem o valor atualizado se a leitura for feita aqui,
    em tempo de chamada.
    """
    return {
        "lider_1_turno": os.environ.get("OBP_CONTATO_LIDER_1_TURNO", ""),
        "lider_reserva_1_turno": os.environ.get(
            "OBP_CONTATO_LIDER_RESERVA_1_TURNO", ""
        ),
        "lider_2_turno": os.environ.get("OBP_CONTATO_LIDER_2_TURNO", ""),
        "lider_reserva_2_turno": os.environ.get(
            "OBP_CONTATO_LIDER_RESERVA_2_TURNO", ""
        ),
        "lider_3_turno": os.environ.get("OBP_CONTATO_LIDER_3_TURNO", ""),
        "lider_reserva_3_turno": os.environ.get(
            "OBP_CONTATO_LIDER_RESERVA_3_TURNO", ""
        ),
        "lider_cq": os.environ.get("OBP_CONTATO_LIDER_CQ", ""),
        "equipe_cq": _join_responsavel(
            os.environ.get("OBP_CONTATO_EQUIPE_CQ", "").split(",")
        ),
    }


def _load_config(
    config_file: str,
) -> tuple[dict[str, FaseConfig], int, dict[str, Any], list[int]]:
    """Le config.json; falha explicita (sys.exit(1)) se o arquivo existir mas nao puder
    ser interpretado — configuracao invalida e erro real, nao caso a tolerar
    silenciosamente (achado de revisao OBP-04 Q3: os dois scripts chamadores tinham
    tratamento divergente para essa falha; ambos agora se comportam igual via este
    helper compartilhado)."""
    fases_monitoradas = dict(DEFAULT_FASES_MONITORADAS)
    max_obs = DEFAULT_MAX_OBS
    phase_filters: dict[str, Any] = {}
    phase_order = list(DEFAULT_PHASE_ORDER)
    if not os.path.exists(config_file):
        return fases_monitoradas, max_obs, phase_filters, phase_order
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        max_obs = int(cfg.get("max_obs_por_mensagem", DEFAULT_MAX_OBS))
        phase_filters = {
            str(k): v for k, v in cfg.get("filtros_por_codigo_fase", {}).items()
        }
        phase_order = [
            int(c) for c in cfg.get("ordem_codigos_fase", DEFAULT_PHASE_ORDER)
        ]
        contatos = _load_contatos_from_env()
        fases_cfg = cfg.get("fases_monitoradas")
        if fases_cfg:
            fases_monitoradas = {}
            for codigo, dados in fases_cfg.items():
                resp_ref = dados.get("responsavel", "")
                responsavel = (
                    contatos[resp_ref]
                    if isinstance(resp_ref, str) and resp_ref in contatos
                    else _resolve_contato(resp_ref)
                )
                fases_monitoradas[str(codigo)] = FaseConfig(
                    descricao=str(dados.get("descricao", "")),
                    threshold_dias=float(dados.get("threshold_dias", 1)),
                    responsavel=responsavel,
                    ativo=bool(dados.get("ativo", True)),
                )
    except Exception as e:  # pylint: disable=broad-exception-caught
        # config.json existe mas nao pode ser interpretado: falhar explicitamente em vez de
        # degradar silenciosamente para defaults hardcoded, que podem estar desatualizados
        # em relacao ao config de producao (thresholds, fases ativas).
        print(
            f"[ERROR] config.json existe mas falhou ao processar: {e}. "
            "Corrija o arquivo antes de reexecutar; defaults hardcoded nao serao usados como fallback silencioso.",
            file=sys.stderr,
        )
        sys.exit(1)
    return fases_monitoradas, max_obs, phase_filters, phase_order

"""Popula o SQLite beneficiamento_historico.db com dados ricos de mock para testes e DX."""
# pylint: disable=all
# mypy: ignore-errors

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Adicionar src ao path
BASE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from beneficiamento.historico_db import salvar_historico, init_db


def populate():
    # Garantir que o banco esteja inicializado
    db_path = init_db()
    print(f"Banco SQLite inicializado em: {db_path}")

    hoje = datetime.now()
    ontem = hoje - timedelta(days=1)
    anteontem = hoje - timedelta(days=2)

    records = [
        # OB 240125 - Percurso Completo Estável (3 Fases)
        {
            "NUMERO_OB": "240125",
            "SEQ": 1,
            "DATA_FIM": anteontem.replace(hour=8, minute=0, second=0).isoformat(),
            "NUMERO_MAQUINA": 105,
            "NOME_MAQUINA": "PREPARADORA 01",
            "CD_DS_FASE": "01 - PREPARAÇÃO",
            "REDUZ": "005391",
            "CODIGO_ALTERNATIVO": "ALT-5391",
            "DESCR_ITEM": "MALHA DE ALGODÃO PIMA",
            "ARTIGO": "ALGODÃO PIMA PREMIUM",
            "DESCR_ARTIGO": "ART-ALGODAO-PIMA",
            "COR": "12-BLACK",
            "DESCR_COR": "PRETO ABSOLUTO",
            "QT_KG": 500.0,
            "QT_MT": 1200.0,
            "ANO_MES": anteontem.strftime("%Y%m"),
            "ANO_SEM": int(anteontem.strftime("%Y%W")),
            "OPERADOR_FINAL": "MARIO SOUZA",
            "REPROCESSO": 0,
            "MIN_REAL": 45.0,
            "MIN_PREV": 40.0,
            "DESVIO_MIN": 5.0,
        },
        {
            "NUMERO_OB": "240125",
            "SEQ": 2,
            "DATA_FIM": anteontem.replace(hour=14, minute=30, second=0).isoformat(),
            "NUMERO_MAQUINA": 204,
            "NOME_MAQUINA": "TINGIDORA JET 04",
            "CD_DS_FASE": "03 - TINGIMENTO",
            "REDUZ": "005391",
            "CODIGO_ALTERNATIVO": "ALT-5391",
            "DESCR_ITEM": "MALHA DE ALGODÃO PIMA",
            "ARTIGO": "ALGODÃO PIMA PREMIUM",
            "DESCR_ARTIGO": "ART-ALGODAO-PIMA",
            "COR": "12-BLACK",
            "DESCR_COR": "PRETO ABSOLUTO",
            "QT_KG": 500.0,
            "QT_MT": 1200.0,
            "ANO_MES": anteontem.strftime("%Y%m"),
            "ANO_SEM": int(anteontem.strftime("%Y%W")),
            "OPERADOR_FINAL": "LUCAS SILVA",
            "REPROCESSO": 0,
            "MIN_REAL": 220.0,
            "MIN_PREV": 240.0,
            "DESVIO_MIN": -20.0,
        },
        {
            "NUMERO_OB": "240125",
            "SEQ": 3,
            "DATA_FIM": anteontem.replace(hour=18, minute=15, second=0).isoformat(),
            "NUMERO_MAQUINA": 302,
            "NOME_MAQUINA": "RAMA DORNier 02",
            "CD_DS_FASE": "10 - RAMA",
            "REDUZ": "005391",
            "CODIGO_ALTERNATIVO": "ALT-5391",
            "DESCR_ITEM": "MALHA DE ALGODÃO PIMA",
            "ARTIGO": "ALGODÃO PIMA PREMIUM",
            "DESCR_ARTIGO": "ART-ALGODAO-PIMA",
            "COR": "12-BLACK",
            "DESCR_COR": "PRETO ABSOLUTO",
            "QT_KG": 492.0,
            "QT_MT": 1185.0,
            "ANO_MES": anteontem.strftime("%Y%m"),
            "ANO_SEM": int(anteontem.strftime("%Y%W")),
            "OPERADOR_FINAL": "PEDRO GOMES",
            "REPROCESSO": 0,
            "MIN_REAL": 95.0,
            "MIN_PREV": 75.0,
            "DESVIO_MIN": 20.0, # Atraso de 20 min
        },

        # OB 240126 - Com Reprocesso/Atraso (3 Fases)
        {
            "NUMERO_OB": "240126",
            "SEQ": 1,
            "DATA_FIM": ontem.replace(hour=9, minute=15, second=0).isoformat(),
            "NUMERO_MAQUINA": 105,
            "NOME_MAQUINA": "PREPARADORA 01",
            "CD_DS_FASE": "01 - PREPARAÇÃO",
            "REDUZ": "008842",
            "CODIGO_ALTERNATIVO": "ALT-8842",
            "DESCR_ITEM": "MEIA MALHA POLIESTER LIGHT",
            "ARTIGO": "POLIESTER LIGHT ACTIVE",
            "DESCR_ARTIGO": "ART-POLY-LIGHT",
            "COR": "45-NEON-GREEN",
            "DESCR_COR": "VERDE NEON",
            "QT_KG": 320.0,
            "QT_MT": 950.0,
            "ANO_MES": ontem.strftime("%Y%m"),
            "ANO_SEM": int(ontem.strftime("%Y%W")),
            "OPERADOR_FINAL": "JOSE ALVES",
            "REPROCESSO": 0,
            "MIN_REAL": 35.0,
            "MIN_PREV": 35.0,
            "DESVIO_MIN": 0.0,
        },
        {
            "NUMERO_OB": "240126",
            "SEQ": 2,
            "DATA_FIM": ontem.replace(hour=16, minute=0, second=0).isoformat(),
            "NUMERO_MAQUINA": 201,
            "NOME_MAQUINA": "TINGIDORA JET 01",
            "CD_DS_FASE": "03 - TINGIMENTO",
            "REDUZ": "008842",
            "CODIGO_ALTERNATIVO": "ALT-8842",
            "DESCR_ITEM": "MEIA MALHA POLIESTER LIGHT",
            "ARTIGO": "POLIESTER LIGHT ACTIVE",
            "DESCR_ARTIGO": "ART-POLY-LIGHT",
            "COR": "45-NEON-GREEN",
            "DESCR_COR": "VERDE NEON",
            "QT_KG": 320.0,
            "QT_MT": 950.0,
            "ANO_MES": ontem.strftime("%Y%m"),
            "ANO_SEM": int(ontem.strftime("%Y%W")),
            "OPERADOR_FINAL": "CARLOS SANTOS",
            "REPROCESSO": 1, # Reprocesso ativo
            "MIN_REAL": 310.0,
            "MIN_PREV": 220.0,
            "DESVIO_MIN": 90.0, # Grande desvio
        },
        {
            "NUMERO_OB": "240126",
            "SEQ": 3,
            "DATA_FIM": ontem.replace(hour=19, minute=45, second=0).isoformat(),
            "NUMERO_MAQUINA": 301,
            "NOME_MAQUINA": "RAMA DORNier 01",
            "CD_DS_FASE": "10 - RAMA",
            "REDUZ": "008842",
            "CODIGO_ALTERNATIVO": "ALT-8842",
            "DESCR_ITEM": "MEIA MALHA POLIESTER LIGHT",
            "ARTIGO": "POLIESTER LIGHT ACTIVE",
            "DESCR_ARTIGO": "ART-POLY-LIGHT",
            "COR": "45-NEON-GREEN",
            "DESCR_COR": "VERDE NEON",
            "QT_KG": 318.0,
            "QT_MT": 942.0,
            "ANO_MES": ontem.strftime("%Y%m"),
            "ANO_SEM": int(ontem.strftime("%Y%W")),
            "OPERADOR_FINAL": "PEDRO GOMES",
            "REPROCESSO": 0,
            "MIN_REAL": 70.0,
            "MIN_PREV": 70.0,
            "DESVIO_MIN": 0.0,
        },

        # OB 240127 - Produção Recente de Hoje (Apenas Preparada)
        {
            "NUMERO_OB": "240127",
            "SEQ": 1,
            "DATA_FIM": hoje.replace(hour=10, minute=30, second=0).isoformat(),
            "NUMERO_MAQUINA": 105,
            "NOME_MAQUINA": "PREPARADORA 01",
            "CD_DS_FASE": "01 - PREPARAÇÃO",
            "REDUZ": "003115",
            "CODIGO_ALTERNATIVO": "ALT-3115",
            "DESCR_ITEM": "SUEDE LIGHT ELASTANO",
            "ARTIGO": "SUEDE CONFORT",
            "DESCR_ARTIGO": "ART-SUEDE",
            "COR": "02-NAVY",
            "DESCR_COR": "AZUL MARINHO",
            "QT_KG": 620.0,
            "QT_MT": 1800.0,
            "ANO_MES": hoje.strftime("%Y%m"),
            "ANO_SEM": int(hoje.strftime("%Y%W")),
            "OPERADOR_FINAL": "MARIO SOUZA",
            "REPROCESSO": 0,
            "MIN_REAL": 50.0,
            "MIN_PREV": 45.0,
            "DESVIO_MIN": 5.0,
        }
    ]

    inserted = salvar_historico(records)
    print(f"Mock Historico populado com sucesso! {inserted} registros inseridos.")


if __name__ == "__main__":
    populate()

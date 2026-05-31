"""Gerenciamento e persistência do histórico do Beneficiamento em SQLite."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements,unused-import,trailing-whitespace,line-too-long

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from .settings import DOMAIN_ROOT


def resolve_db_path(override: Path | str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    # Pasta padrão de snapshots
    folder = DOMAIN_ROOT / "snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "beneficiamento_historico.db"


def init_db(db_path: Path | str | None = None) -> Path:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        # Habilitar modo WAL e synchronous NORMAL para máxima resiliência e performance de I/O
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")

        # Tabela Fato de Produção Histórica
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fato_producao_historica (
                NUMERO_OB TEXT NOT NULL,
                SEQ INTEGER NOT NULL,
                DATA_FIM TEXT,
                NUMERO_MAQUINA INTEGER,
                NOME_MAQUINA TEXT,
                CD_DS_FASE TEXT,
                REDUZ TEXT,
                CODIGO_ALTERNATIVO TEXT,
                DESCR_ITEM TEXT,
                ARTIGO TEXT,
                DESCR_ARTIGO TEXT,
                COR TEXT,
                DESCR_COR TEXT,
                QT_KG REAL,
                QT_MT REAL,
                ANO_MES TEXT,
                ANO_SEM INTEGER,
                OPERADOR_FINAL TEXT,
                REPROCESSO INTEGER,
                MIN_REAL REAL,
                MIN_PREV REAL,
                DESVIO_MIN REAL,
                DADOS_COMPLETOS TEXT, -- Payload completo serializado em JSON
                PRIMARY KEY (NUMERO_OB, SEQ)
            );
            """
        )

        # Criação de índices para pesquisas rápidas
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_numero_ob ON fato_producao_historica(NUMERO_OB);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_alternativo ON fato_producao_historica(CODIGO_ALTERNATIVO);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_reduz ON fato_producao_historica(REDUZ);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_data ON fato_producao_historica(DATA_FIM);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_anosem ON fato_producao_historica(ANO_SEM);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_anomes ON fato_producao_historica(ANO_MES);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_producao_maquina ON fato_producao_historica(NUMERO_MAQUINA);"
        )

        conn.commit()

    return path


def salvar_historico(records: list[dict[str, Any]], db_path: Path | str | None = None) -> int:
    if not records:
        return 0

    path = init_db(db_path)
    inserted = 0

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")

        cursor = conn.cursor()

        # Query de inserção/substituição idempotente baseada na chave composta NUMERO_OB e SEQ
        query = """
            INSERT OR REPLACE INTO fato_producao_historica (
                NUMERO_OB,
                SEQ,
                DATA_FIM,
                NUMERO_MAQUINA,
                NOME_MAQUINA,
                CD_DS_FASE,
                REDUZ,
                CODIGO_ALTERNATIVO,
                DESCR_ITEM,
                ARTIGO,
                DESCR_ARTIGO,
                COR,
                DESCR_COR,
                QT_KG,
                QT_MT,
                ANO_MES,
                ANO_SEM,
                OPERADOR_FINAL,
                REPROCESSO,
                MIN_REAL,
                MIN_PREV,
                DESVIO_MIN,
                DADOS_COMPLETOS
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """

        for rec in records:
            # Obter campos com fallbacks seguros
            numero_ob = str(rec.get("NUMERO_OB", "")).strip()
            # Se não houver número de OB, pular registro inconsistente
            if not numero_ob:
                continue

            seq = rec.get("SEQ")
            if seq is None:
                seq = 0
            else:
                try:
                    seq = int(seq)
                except ValueError:
                    seq = 0

            # Datas podem vir como datetime, date ou string. Serializar para ISO8601 string
            data_fim = rec.get("DATA_HORA_FIM") or rec.get("DATA_FIM") or rec.get("DATA_PROD")
            if isinstance(data_fim, (datetime, date)):
                data_fim_str = data_fim.isoformat()
            elif data_fim:
                data_fim_str = str(data_fim).strip()
            else:
                data_fim_str = None

            # Demais campos de filtro e KPI
            numero_maquina = rec.get("NUMERO_MAQUINA")
            try:
                numero_maquina = int(numero_maquina) if numero_maquina is not None else None
            except ValueError:
                numero_maquina = None

            nome_maquina = rec.get("NOME_MAQUINA")
            nome_maquina_str = str(nome_maquina).strip() if nome_maquina else None

            cd_ds_fase = rec.get("CD_DS_FASE")
            cd_ds_fase_str = str(cd_ds_fase).strip() if cd_ds_fase else None

            reduz = rec.get("REDUZ")
            reduz_str = str(reduz).strip() if reduz is not None else None

            codigo_alternativo = rec.get("CODIGO_ALTERNATIVO")
            codigo_alternativo_str = str(codigo_alternativo).strip() if codigo_alternativo else None

            descr_item = rec.get("DESCR_ITEM")
            descr_item_str = str(descr_item).strip() if descr_item else None

            artigo = rec.get("ARTIGO")
            artigo_str = str(artigo).strip() if artigo else None

            descr_artigo = rec.get("DESCR_ARTIGO")
            descr_artigo_str = str(descr_artigo).strip() if descr_artigo else None

            cor = rec.get("COR")
            cor_str = str(cor).strip() if cor else None

            descr_cor = rec.get("DESCR_COR")
            descr_cor_str = str(descr_cor).strip() if descr_cor else None

            qt_kg = rec.get("QT_KG")
            try:
                qt_kg = float(qt_kg) if qt_kg is not None else 0.0
            except ValueError:
                qt_kg = 0.0

            qt_mt = rec.get("QT_MT")
            try:
                qt_mt = float(qt_mt) if qt_mt is not None else 0.0
            except ValueError:
                qt_mt = 0.0

            ano_mes = rec.get("ANO_MES")
            ano_mes_str = str(ano_mes).strip() if ano_mes else None

            ano_sem = rec.get("ANO_SEM")
            try:
                ano_sem = int(ano_sem) if ano_sem is not None else None
            except ValueError:
                ano_sem = None

            operador_final = rec.get("OPERADOR_FINAL")
            operador_final_str = str(operador_final).strip() if operador_final else None

            reprocesso = rec.get("REPROCESSO")
            try:
                reprocesso = int(reprocesso) if reprocesso is not None else 0
            except ValueError:
                reprocesso = 0

            min_real = rec.get("MIN_REAL")
            try:
                min_real = float(min_real) if min_real is not None else 0.0
            except ValueError:
                min_real = 0.0

            min_prev = rec.get("MIN_PREV")
            try:
                min_prev = float(min_prev) if min_prev is not None else 0.0
            except ValueError:
                min_prev = 0.0

            desvio_min = rec.get("DESVIO_MIN")
            try:
                desvio_min = float(desvio_min) if desvio_min is not None else 0.0
            except ValueError:
                desvio_min = 0.0

            # Salvar o payload original completo
            # Vamos converter objetos datetime no dict para strings para que json.dumps funcione
            serialized_rec = {}
            for k, v in rec.items():
                if isinstance(v, (datetime, date)):
                    serialized_rec[k] = v.isoformat()
                else:
                    serialized_rec[k] = v

            dados_completos = json.dumps(serialized_rec, ensure_ascii=False)

            cursor.execute(
                query,
                (
                    numero_ob,
                    seq,
                    data_fim_str,
                    numero_maquina,
                    nome_maquina_str,
                    cd_ds_fase_str,
                    reduz_str,
                    codigo_alternativo_str,
                    descr_item_str,
                    artigo_str,
                    descr_artigo_str,
                    cor_str,
                    descr_cor_str,
                    qt_kg,
                    qt_mt,
                    ano_mes_str,
                    ano_sem,
                    operador_final_str,
                    reprocesso,
                    min_real,
                    min_prev,
                    desvio_min,
                    dados_completos,
                ),
            )
            inserted += 1

        conn.commit()

    return inserted


def buscar_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    path = init_db(db_path)
    records: list[dict[str, Any]] = []

    # Construir query SQL dinâmica
    sql = "SELECT DADOS_COMPLETOS FROM fato_producao_historica WHERE 1=1"
    params: list[Any] = []

    # Filtro: Número da OB (exato ou prefixo)
    ob = filtros.get("ob")
    if ob:
        sql += " AND NUMERO_OB LIKE ?"
        params.append(f"{str(ob).strip()}%")

    # Filtro: Alternativo ou Reduz (exato)
    alternativo = filtros.get("alternativo")
    if alternativo:
        sql += " AND (CODIGO_ALTERNATIVO = ? OR REDUZ = ?)"
        params.append(str(alternativo).strip())
        params.append(str(alternativo).strip())

    # Filtro: Range de Datas
    dt_inicio = filtros.get("dt_inicio")
    if dt_inicio:
        sql += " AND DATA_FIM >= ?"
        params.append(str(dt_inicio).strip())

    dt_fim = filtros.get("dt_fim")
    if dt_fim:
        sql += " AND DATA_FIM <= ?"
        params.append(str(dt_fim).strip())

    # Filtro: Semanas (ex: 202622 para semana 22 de 2026)
    ano_sem = filtros.get("ano_sem")
    if ano_sem:
        try:
            sql += " AND ANO_SEM = ?"
            params.append(int(ano_sem))
        except ValueError:
            pass

    # Filtro: Ano/Mês (ex: 202605)
    ano_mes = filtros.get("ano_mes")
    if ano_mes:
        sql += " AND ANO_MES = ?"
        params.append(str(ano_mes).strip())

    # Ordenar por data decrescente e sequencial
    sql += " ORDER BY DATA_FIM DESC, NUMERO_OB DESC, SEQ ASC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            raw_json = row["DADOS_COMPLETOS"]
            if raw_json:
                try:
                    records.append(json.loads(raw_json))
                except json.JSONDecodeError:
                    pass

    return records


def obter_analytics_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None
) -> dict[str, Any]:
    path = init_db(db_path)
    
    # 1. Construir a cláusula WHERE baseada nos filtros
    where_clauses = ["1=1"]
    params: list[Any] = []
    
    ob = filtros.get("ob")
    if ob:
        where_clauses.append("NUMERO_OB LIKE ?")
        params.append(f"{str(ob).strip()}%")
        
    alternativo = filtros.get("alternativo")
    if alternativo:
        where_clauses.append("(CODIGO_ALTERNATIVO = ? OR REDUZ = ?)")
        params.append(str(alternativo).strip())
        params.append(str(alternativo).strip())
        
    dt_inicio = filtros.get("dt_inicio")
    if dt_inicio:
        where_clauses.append("DATA_FIM >= ?")
        params.append(str(dt_inicio).strip())
        
    dt_fim = filtros.get("dt_fim")
    if dt_fim:
        where_clauses.append("DATA_FIM <= ?")
        params.append(str(dt_fim).strip())
        
    ano_sem = filtros.get("ano_sem")
    if ano_sem:
        try:
            where_clauses.append("ANO_SEM = ?")
            params.append(int(ano_sem))
        except ValueError:
            pass
            
    ano_mes = filtros.get("ano_mes")
    if ano_mes:
        where_clauses.append("ANO_MES = ?")
        params.append(str(ano_mes).strip())
        
    where_sql = " AND ".join(where_clauses)
    
    payload: dict[str, Any] = {}
    
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # A. KPIs Gerais de PCP e OEE
        kpis_sql = f"""
            SELECT 
                COUNT(DISTINCT NUMERO_OB) as ob_distintas,
                COUNT(NUMERO_OB) as total_fases,
                SUM(QT_KG) as kg_total,
                SUM(QT_MT) as mt_total,
                SUM(MIN_REAL) as min_real_total,
                SUM(MIN_PREV) as min_prev_total,
                SUM(REPROCESSO) as total_reprocesso,
                COUNT(DISTINCT OPERADOR_FINAL) as total_operadores,
                COUNT(DISTINCT NUMERO_MAQUINA) as maquinas_distintas
            FROM fato_producao_historica
            WHERE {where_sql}
        """
        cursor.execute(kpis_sql, params)
        kpi_row = cursor.fetchone()
        
        kg_total = kpi_row["kg_total"] or 0.0
        mt_total = kpi_row["mt_total"] or 0.0
        total_fases = kpi_row["total_fases"] or 0
        min_real = kpi_row["min_real_total"] or 0.0
        min_prev = kpi_row["min_prev_total"] or 0.0
        total_reprocesso = kpi_row["total_reprocesso"] or 0
        
        efic_tempo = (min_prev / min_real * 100) if min_real > 0 else 100.0
        taxa_reprocesso = (total_reprocesso / total_fases * 100) if total_fases > 0 else 0.0
        produtividade_kgh = (kg_total * 60.0 / min_real) if min_real > 0 else 0.0
        
        payload["geral"] = {
            "ob_distintas": kpi_row["ob_distintas"] or 0,
            "total_fases": total_fases,
            "maquinas_distintas": kpi_row["maquinas_distintas"] or 0,
            "total_operadores": kpi_row["total_operadores"] or 0,
            "kg_total": round(kg_total, 2),
            "mt_total": round(mt_total, 2),
            "min_real_total": round(min_real, 2),
            "min_prev_total": round(min_prev, 2),
            "desvio_min_total": round(min_real - min_prev, 2),
            "efic_tempo_media": round(efic_tempo, 2),
            "taxa_reprocesso": round(taxa_reprocesso, 2),
            "produtividade_kgh": round(produtividade_kgh, 2),
        }
        
        # B. Ranking de Operadores (Chão de Fábrica)
        operadores_sql = f"""
            SELECT 
                OPERADOR_FINAL as operador,
                SUM(QT_KG) as kg_total,
                SUM(QT_MT) as mt_total,
                COUNT(NUMERO_OB) as total_fases,
                SUM(MIN_REAL) as min_real,
                SUM(MIN_PREV) as min_prev
            FROM fato_producao_historica
            WHERE {where_sql} AND OPERADOR_FINAL IS NOT NULL AND OPERADOR_FINAL != ''
            GROUP BY OPERADOR_FINAL
            ORDER BY kg_total DESC
            LIMIT 10
        """
        cursor.execute(operadores_sql, params)
        operadores = []
        for r in cursor.fetchall():
            o_min_real = r["min_real"] or 0.0
            o_min_prev = r["min_prev"] or 0.0
            o_efic = (o_min_prev / o_min_real * 100) if o_min_real > 0 else 100.0
            operadores.append({
                "operador": r["operador"],
                "kg_total": round(r["kg_total"] or 0.0, 2),
                "mt_total": round(r["mt_total"] or 0.0, 2),
                "total_fases": r["total_fases"] or 0,
                "efic_tempo": round(o_efic, 2),
            })
        payload["operadores"] = operadores
        
        # C. Destaques de Máquinas e Tempos (Setup vs Processo)
        maquinas_sql = f"""
            SELECT 
                NOME_MAQUINA as maquina,
                SUM(QT_KG) as kg_total,
                SUM(QT_MT) as mt_total,
                SUM(MIN_REAL) as min_real,
                SUM(MIN_PREV) as min_prev,
                COUNT(NUMERO_OB) as total_fases
            FROM fato_producao_historica
            WHERE {where_sql} AND NOME_MAQUINA IS NOT NULL
            GROUP BY NOME_MAQUINA
            ORDER BY kg_total DESC
            LIMIT 10
        """
        cursor.execute(maquinas_sql, params)
        maquinas = []
        for r in cursor.fetchall():
            m_min_real = r["min_real"] or 0.0
            m_setup = round(m_min_real * 0.15, 2)
            m_processo = round(m_min_real * 0.85, 2)
            
            maquinas.append({
                "maquina": r["maquina"],
                "kg_total": round(r["kg_total"] or 0.0, 2),
                "mt_total": round(r["mt_total"] or 0.0, 2),
                "total_fases": r["total_fases"] or 0,
                "min_real": round(m_min_real, 2),
                "min_setup": m_setup,
                "min_processo": m_processo,
            })
        payload["maquinas"] = maquinas
        
        # D. Tabela de Produtos Dinâmica Enriquecida
        produtos_sql = f"""
            SELECT 
                REDUZ as reduz,
                DESCR_ITEM as produto,
                ARTIGO as artigo,
                SUM(QT_KG) as kg_total,
                SUM(QT_MT) as mt_total,
                SUM(REPROCESSO) as reprocessos,
                COUNT(NUMERO_OB) as total_fases,
                SUM(MIN_REAL) as min_real
            FROM fato_producao_historica
            WHERE {where_sql} AND REDUZ IS NOT NULL
            GROUP BY REDUZ, DESCR_ITEM, ARTIGO
            ORDER BY kg_total DESC
            LIMIT 50
        """
        cursor.execute(produtos_sql, params)
        produtos = []
        for r in cursor.fetchall():
            p_fases = r["total_fases"] or 0
            p_reprocessos = r["reprocessos"] or 0
            p_min_real = r["min_real"] or 0.0
            p_taxa_rep = (p_reprocessos / p_fases * 100) if p_fases > 0 else 0.0
            p_prod = (r["kg_total"] * 60.0 / p_min_real) if p_min_real > 0 else 0.0
            
            produtos.append({
                "reduz": r["reduz"],
                "produto": r["produto"] or "Sem descrição",
                "artigo": r["artigo"] or "Sem artigo",
                "kg_total": round(r["kg_total"] or 0.0, 2),
                "mt_total": round(r["mt_total"] or 0.0, 2),
                "taxa_reprocesso": round(p_taxa_rep, 2),
                "produtividade_kgh": round(p_prod, 2),
            })
        payload["produtos"] = produtos
        
        # E. Distribuição por Turno (via JSON extract nativo do SQLite)
        turnos_sql = f"""
            SELECT 
                COALESCE(json_extract(DADOS_COMPLETOS, '$.turno'), json_extract(DADOS_COMPLETOS, '$.TURNO'), 'Indefinido') as turno,
                SUM(QT_KG) as kg_total
            FROM fato_producao_historica
            WHERE {where_sql}
            GROUP BY turno
            ORDER BY kg_total DESC
        """
        cursor.execute(turnos_sql, params)
        turnos = []
        for r in cursor.fetchall():
            turnos.append({
                "turno": r["turno"] or "Indefinido",
                "kg_total": round(r["kg_total"] or 0.0, 2)
            })
        payload["turnos"] = turnos

    return payload

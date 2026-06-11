"""Gerenciamento e persistência do histórico do Beneficiamento em SQLite."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements,unused-import,trailing-whitespace,line-too-long,import-outside-toplevel

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .settings import DOMAIN_ROOT


DERIVED_COLUMNS: dict[str, str] = {
    "TURNO_ID": "TEXT",
    "TURNO_LABEL": "TEXT",
    "MAQUINA_KEY": "TEXT",
    "FASE_KEY": "TEXT",
    "CODIGO_KEY": "TEXT",
}

DERIVED_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_producao_turno_label ON fato_producao_historica(TURNO_LABEL);",
    "CREATE INDEX IF NOT EXISTS idx_producao_maquina_key ON fato_producao_historica(MAQUINA_KEY);",
    "CREATE INDEX IF NOT EXISTS idx_producao_fase_key ON fato_producao_historica(FASE_KEY);",
    "CREATE INDEX IF NOT EXISTS idx_producao_codigo_key ON fato_producao_historica(CODIGO_KEY);",
    "CREATE INDEX IF NOT EXISTS idx_producao_data_maquina_fase ON fato_producao_historica(DATA_FIM, MAQUINA_KEY, FASE_KEY);",
)

HISTORICO_SCHEMA_VERSION = 1


def _safe_strip(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date_filter(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_turno_fields(record: dict[str, Any]) -> tuple[str | None, str | None]:
    turno_id = _safe_strip(record.get("TURNO_PROD") or record.get("turno") or record.get("TURNO"))
    turno_label = _safe_strip(record.get("TURNO_DESC"))
    if not turno_label and turno_id:
        turno_label = f"TURNO {turno_id}"
    return (turno_id or None, turno_label or None)


def _derive_record_fields(record: dict[str, Any]) -> dict[str, Any]:
    turno_id, turno_label = _normalize_turno_fields(record)
    codigo_key = _safe_strip(record.get("CODIGO_ALTERNATIVO") or record.get("REDUZ"))
    return {
        "turno_id": turno_id,
        "turno_label": turno_label or "Indefinido",
        "maquina_key": _safe_strip(record.get("NOME_MAQUINA")),
        "fase_key": _safe_strip(record.get("CD_DS_FASE")),
        "codigo_key": codigo_key or None,
    }


def _ensure_derived_schema(conn: sqlite3.Connection) -> None:
    current_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(fato_producao_historica);").fetchall()
    }

    for column_name, column_type in DERIVED_COLUMNS.items():
        if column_name not in current_columns:
            conn.execute(
                f"ALTER TABLE fato_producao_historica ADD COLUMN {column_name} {column_type};"
            )


def _backfill_derived_columns(conn: sqlite3.Connection) -> None:
    pending = conn.execute(
        """
        SELECT NUMERO_OB, SEQ, DADOS_COMPLETOS
        FROM fato_producao_historica
        WHERE TURNO_LABEL IS NULL
           OR MAQUINA_KEY IS NULL
           OR FASE_KEY IS NULL
           OR CODIGO_KEY IS NULL
        """
    ).fetchall()
    if not pending:
        return

    updates: list[tuple[Any, ...]] = []
    for numero_ob, seq, raw_payload in pending:
        if raw_payload:
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}
        derived = _derive_record_fields(payload)
        updates.append(
            (
                derived["turno_id"],
                derived["turno_label"],
                derived["maquina_key"],
                derived["fase_key"],
                derived["codigo_key"],
                numero_ob,
                seq,
            )
        )

    conn.executemany(
        """
        UPDATE fato_producao_historica
        SET TURNO_ID = ?,
            TURNO_LABEL = ?,
            MAQUINA_KEY = ?,
            FASE_KEY = ?,
            CODIGO_KEY = ?
        WHERE NUMERO_OB = ? AND SEQ = ?
        """,
        updates,
    )


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

        current_version = int(conn.execute("PRAGMA user_version;").fetchone()[0] or 0)
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'fato_producao_historica';"
        ).fetchone() is not None
        if table_exists and current_version >= HISTORICO_SCHEMA_VERSION:
            return path

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
                TURNO_ID TEXT,
                TURNO_LABEL TEXT,
                MAQUINA_KEY TEXT,
                FASE_KEY TEXT,
                CODIGO_KEY TEXT,
                DADOS_COMPLETOS TEXT, -- Payload completo serializado em JSON
                PRIMARY KEY (NUMERO_OB, SEQ)
            );
            """
        )

        _ensure_derived_schema(conn)

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
        for index_sql in DERIVED_INDEXES:
            conn.execute(index_sql)

        _backfill_derived_columns(conn)
        conn.execute(f"PRAGMA user_version = {HISTORICO_SCHEMA_VERSION};")

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
                TURNO_ID,
                TURNO_LABEL,
                MAQUINA_KEY,
                FASE_KEY,
                CODIGO_KEY,
                DADOS_COMPLETOS
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
            nome_maquina_str = _safe_strip(nome_maquina) or None

            cd_ds_fase = rec.get("CD_DS_FASE")
            cd_ds_fase_str = _safe_strip(cd_ds_fase) or None

            reduz = rec.get("REDUZ")
            reduz_str = _safe_strip(reduz) or None

            codigo_alternativo = rec.get("CODIGO_ALTERNATIVO")
            codigo_alternativo_str = _safe_strip(codigo_alternativo) or None

            descr_item = rec.get("DESCR_ITEM")
            descr_item_str = _safe_strip(descr_item) or None

            artigo = rec.get("ARTIGO")
            artigo_str = _safe_strip(artigo) or None

            descr_artigo = rec.get("DESCR_ARTIGO")
            descr_artigo_str = _safe_strip(descr_artigo) or None

            cor = rec.get("COR")
            cor_str = _safe_strip(cor) or None

            descr_cor = rec.get("DESCR_COR")
            descr_cor_str = _safe_strip(descr_cor) or None

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

            derived = _derive_record_fields(serialized_rec)
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
                    derived["turno_id"],
                    derived["turno_label"],
                    derived["maquina_key"],
                    derived["fase_key"],
                    derived["codigo_key"],
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
        inicio = _parse_date_filter(dt_inicio)
        if inicio:
            sql += " AND DATA_FIM >= ?"
            params.append(f"{inicio.isoformat()}T00:00:00")

    dt_fim = filtros.get("dt_fim")
    if dt_fim:
        fim = _parse_date_filter(dt_fim)
        if fim:
            sql += " AND DATA_FIM < ?"
            params.append(f"{(fim + timedelta(days=1)).isoformat()}T00:00:00")

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
                    item = json.loads(raw_json)
                    turno_id = str(item.get("TURNO_PROD") or item.get("turno") or item.get("TURNO") or "").strip()
                    turno_desc = str(item.get("TURNO_DESC") or "").strip()
                    if not turno_desc and turno_id:
                        turno_desc = f"TURNO {turno_id}"
                    item["TURNO_PROD"] = turno_id or item.get("TURNO_PROD")
                    item["TURNO_DESC"] = turno_desc or item.get("TURNO_DESC") or "Indefinido"
                    records.append(item)
                except json.JSONDecodeError:
                    pass

    return records


def descrever_schema_historico(
    db_path: Path | str | None = None,
) -> dict[str, dict[str, str] | list[str]]:
    """Expõe metadados mínimos do histórico pela camada autorizada do domínio."""
    path = init_db(db_path)
    with sqlite3.connect(path) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(fato_producao_historica)").fetchall()
        }
        indexes = [
            row[1]
            for row in conn.execute("PRAGMA index_list(fato_producao_historica)").fetchall()
        ]
    return {"columns": columns, "indexes": indexes}


def obter_overview_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Monta o contrato operacional V1 do Beneficiamento sem abrir Oracle."""
    from .overview_v1 import obter_overview_historico as _obter_overview_historico_v1

    return _obter_overview_historico_v1(filtros, db_path=db_path)


def obter_detail_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Retorna o drill-down operacional V1 do Beneficiamento."""
    from .overview_v1 import obter_detail_historico as _obter_detail_historico_v1

    return _obter_detail_historico_v1(filtros, db_path=db_path)


def obter_analytics_historico(
    filtros: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Compatibilidade legada: deriva o contrato antigo do overview V0."""
    overview_filters = {
        "dt_inicio": filtros.get("dt_inicio"),
        "dt_fim": filtros.get("dt_fim"),
        "maquina": filtros.get("maquina"),
        "fase": filtros.get("fase"),
        "turno": filtros.get("turno"),
        "alternativo": filtros.get("alternativo"),
        "q": filtros.get("busca") or filtros.get("ob") or filtros.get("alternativo"),
    }
    overview = obter_overview_historico(overview_filters, db_path=db_path)
    kpis = overview.get("kpis", {})
    rankings = overview.get("rankings", {})
    filter_options = overview.get("filter_options", {})

    maquinas = []
    for item in rankings.get("gargalos", []):
        maquinas.append({
            "maquina": item.get("maquina") or "Sem máquina",
            "kg_total": item.get("kg_total") or 0.0,
            "mt_total": item.get("mt_total") or 0.0,
            "total_fases": item.get("fases_concluidas") or 0,
            "min_real": item.get("desvio_min") or 0.0,
            "min_setup": 0.0,
            "min_processo": item.get("desvio_min") or 0.0,
        })

    produtos = [{
        "reduz": item.get("codigo") or "-",
        "produto": item.get("produto") or "Sem descrição",
        "artigo": item.get("artigo") or "Sem artigo",
        "kg_total": item.get("kg_total") or 0.0,
        "mt_total": item.get("mt_total") or 0.0,
        "taxa_reprocesso": item.get("reprocesso_kg_pct") or 0.0,
        "produtividade_kgh": item.get("produtividade_kg_h") or 0.0,
    } for item in rankings.get("produtos_principais", [])]

    fases = [{
        "fase": item.get("fase") or "Sem fase",
        "kg_total": item.get("kg_total") or 0.0,
        "mt_total": 0.0,
        "total_fases": item.get("fases_concluidas") or 0,
        "reprocesso_percent": item.get("reprocesso_kg_pct") or 0.0,
        "efic_tempo": item.get("eficiencia_tempo_pct") or 0.0,
    } for item in rankings.get("fases_criticas", [])]

    return {
        "geral": {
            "ob_distintas": kpis.get("ob_distintas") or 0,
            "total_fases": kpis.get("fases_concluidas") or 0,
            "maquinas_distintas": len(filter_options.get("maquinas", [])),
            "total_operadores": 0,
            "kg_total": kpis.get("kg_total") or 0.0,
            "mt_total": kpis.get("mt_total") or 0.0,
            "min_real_total": 0.0,
            "min_prev_total": 0.0,
            "desvio_min_total": kpis.get("desvio_tempo_min") or 0.0,
            "efic_tempo_media": kpis.get("eficiencia_tempo_pct") or 0.0,
            "taxa_reprocesso": kpis.get("reprocesso_kg_pct") or 0.0,
            "produtividade_kgh": kpis.get("produtividade_kg_h") or 0.0,
        },
        "operadores": [],
        "maquinas": maquinas,
        "produtos": produtos,
        "turnos": [{"turno": value, "kg_total": 0.0} for value in filter_options.get("turnos", [])],
        "fases": fases,
        "artigos": [],
        "cores": [],
    }

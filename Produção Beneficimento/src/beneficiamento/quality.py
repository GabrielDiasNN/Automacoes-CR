"""Checks de qualidade e contrato dos snapshots do Beneficiamento."""
# pylint: disable=too-many-locals

from __future__ import annotations

from typing import Any

from .analytics import safe_text, to_float


DETAILED_REQUIRED_COLUMNS = (
    "NUMEROUP",
    "NUMERO_OB",
    "NUMERO_MAQUINA",
    "CODIGO_FASE",
    "TURNO_PROD",
    "TURNO_DESC",
    "STATUS_UP",
    "STATUS_FASE",
    "DESTINO_RECEITA",
    "QT_KG",
    "QT_MT",
    "MIN_REAL",
    "MIN_PREV",
    "DESVIO_MIN",
    "DESVIO_MIN_ABS",
    "RENDIMENTO",
    "CARGA_PREV_GRUPO",
    "EFIC_CARGA",
    "EFIC_TEMPO",
    "ANO_SEM",
    "LOCAL_PRODUCAO",
    "NOME_UNIDADE_FABRIL",
)

ANNUAL_REQUIRED_COLUMNS = (
    "ANO_MES",
    "CD_DS_FASE",
    "NUMERO_MAQUINA",
    "TURNO_PROD",
    "TURNO_DESC",
    "STATUS_UP",
    "STATUS_FASE",
    "DESTINO_RECEITA",
    "QT_KG",
    "QT_MT",
    "MIN_REAL",
    "MIN_PREV",
    "DESVIO_MIN",
    "DESVIO_MIN_ABS",
    "RENDIMENTO_MEDIO",
    "CARGA_PREV_GRUPO",
    "EFIC_CARGA_MEDIA",
    "EFIC_TEMPO_MEDIA",
)


def _count_duplicate_keys(
    records: list[dict[str, Any]], key_fields: tuple[str, ...]
) -> tuple[int, int]:
    seen: set[tuple[str, ...]] = set()
    duplicate_rows = 0
    for record in records:
        key = tuple(safe_text(record.get(field)) for field in key_fields)
        if key in seen:
            duplicate_rows += 1
        else:
            seen.add(key)
    return duplicate_rows, len(seen)


def assess_quality(
    period: str,
    report: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    variant = "anual" if period == "anual" else "detalhado"
    required_columns = ANNUAL_REQUIRED_COLUMNS if period == "anual" else DETAILED_REQUIRED_COLUMNS
    duplicate_key_fields = (
        (
            "ANO_MES",
            "CD_DS_FASE",
            "NUMERO_MAQUINA",
            "TURNO_PROD",
            "STATUS_UP",
            "STATUS_FASE",
            "DESTINO_RECEITA",
        )
        if period == "anual"
        else (
            "NUMEROUP",
            "NUMERO_OB",
            "NUMERO_MAQUINA",
            "CODIGO_FASE",
            "TURNO_PROD",
            "STATUS_UP",
            "STATUS_FASE",
            "DESTINO_RECEITA",
        )
    )
    column_map = {item["column"]: item for item in report.get("columns", [])}
    missing_required = [column for column in required_columns if column not in column_map]
    critical_issues: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    if not report.get("total_rows"):
        critical_issues.append("consulta sem linhas retornadas")
    if missing_required:
        critical_issues.append("colunas obrigatorias ausentes: " + ", ".join(missing_required))
    checks.append(
        {
            "name": "schema_presence",
            "status": "ok" if not missing_required else "blocked",
            "missing": missing_required,
        }
    )

    critical_nulls = [
        {
            "column": column,
            "null": int(column_map[column].get("null", 0)),
            "total": int(report.get("total_rows") or 0),
        }
        for column in required_columns
        if column in column_map and int(column_map[column].get("null", 0)) > 0
    ]
    if critical_nulls:
        critical_issues.append(
            "nulos criticos em: "
            + ", ".join(f"{item['column']}({item['null']})" for item in critical_nulls)
        )
    checks.append(
        {
            "name": "critical_nulls",
            "status": "ok" if not critical_nulls else "blocked",
            "columns": critical_nulls,
        }
    )

    duplicate_rows, distinct_key_count = _count_duplicate_keys(records, duplicate_key_fields)
    if duplicate_rows:
        critical_issues.append(
            f"chave analitica duplicada em {duplicate_rows} linha(s)"
        )
    checks.append(
        {
            "name": "group_key_uniqueness",
            "status": "ok" if duplicate_rows == 0 else "blocked",
            "key_fields": list(duplicate_key_fields),
            "duplicate_rows": duplicate_rows,
            "distinct_keys": distinct_key_count,
        }
    )

    negative_metrics: list[str] = []
    for metric in ("QT_KG", "QT_MT", "MIN_REAL", "MIN_PREV", "CARGA_PREV_GRUPO"):
        item = column_map.get(metric)
        if item and "min" in item and to_float(item["min"]) < 0:
            negative_metrics.append(metric)
    if negative_metrics:
        warnings.append("metricas com minimo negativo: " + ", ".join(negative_metrics))
    checks.append(
        {
            "name": "metric_ranges",
            "status": "ok" if not negative_metrics else "attention",
            "negative_metrics": negative_metrics,
        }
    )

    status = "blocked" if critical_issues else ("attention" if warnings else "ok")
    return {
        "variant": variant,
        "status": status,
        "ready_for_kpi": status != "blocked",
        "ready_for_powerbi": status != "blocked",
        "ready_for_python": status != "blocked",
        "total_rows": report.get("total_rows", 0),
        "total_columns": report.get("total_columns", 0),
        "duplicate_key_fields": list(duplicate_key_fields),
        "duplicate_key_rows": duplicate_rows,
        "critical_issues": critical_issues,
        "warnings": warnings,
        "checks": checks,
        "notes": [
            "Snapshot validado por contrato de colunas, nulos criticos "
            "e unicidade do grao analitico.",
            "GETs da API consomem apenas snapshots locais; Oracle fica "
            "restrito ao refresh controlado.",
        ],
    }

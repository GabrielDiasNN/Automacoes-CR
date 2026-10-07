#!/usr/bin/env python3
"""Compara deterministicamente duas saídas SQL em JSON ou CSV.

O comparador é deliberadamente local e auditável. Ele rejeita fixtures vazios
por padrão, confronta o contrato de colunas e nulos e compara chaves/métricas
com tolerância numérica explícita.

Colunas, chaves e métricas pedidas na CLI precisam existir nos dois lados (sem
diferenciar maiúsculas); nome ausente é divergência, nunca equivalência. Sem
``--chaves`` as linhas são ordenadas e comparadas par a par (multiconjunto).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VERSION = "1.2.0"


@dataclass(frozen=True)
class CompareSpec:
    """O que comparar e com qual rigor."""

    keys: list[str]
    metrics: list[str]
    columns: list[str]
    tolerance: float
    require_non_empty: bool
    rel_tolerance: float = 1e-12


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
            columns: list[str] = []
            types: dict[str, str] = {}
        elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            rows = payload["rows"]
            raw_columns = payload.get("columns", [])
            columns = (
                [str(value) for value in raw_columns]
                if isinstance(raw_columns, list)
                else []
            )
            raw_types = payload.get("types", {})
            types = (
                {str(key).upper(): str(value) for key, value in raw_types.items()}
                if isinstance(raw_types, dict)
                else {}
            )
        else:
            raise ValueError("JSON deve conter uma lista ou objeto com chave 'rows'")
    elif path.suffix.lower() in {".csv", ".txt"}:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = [
                {key: (None if value == "" else value) for key, value in row.items()}
                for row in reader
            ]
            columns = list(reader.fieldnames or [])
            types = {}
    else:
        raise ValueError(f"Extensão não suportada: {path.suffix}")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Linhas inválidas em {path}; cada linha deve ser objeto")
    if not columns and rows:
        columns = list(rows[0].keys())
    return rows, columns, types


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(" ", ""))
        except ValueError:
            return None
    return None


def _get(row: dict[str, Any], name: str) -> Any:
    target = name.upper()
    for key, value in row.items():
        if str(key).upper() == target:
            return value
    return None


def _columns(rows: list[dict[str, Any]], declared: list[str]) -> list[str]:
    if declared:
        return declared
    result: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            normalized = str(key).upper()
            if normalized not in seen:
                seen.add(normalized)
                result.append(str(key))
    return result


def _same_value(left: Any, right: Any, numeric: bool, spec: CompareSpec) -> bool:
    if numeric:
        left_number = _number(left)
        right_number = _number(right)
        if left_number is not None and right_number is not None:
            return math.isclose(
                left_number,
                right_number,
                rel_tol=spec.rel_tolerance,
                abs_tol=spec.tolerance,
            )
    # Mesma forma canônica das chaves: CSV ("5", "ABC ") e JSON (5, "ABC")
    # descrevem o mesmo valor e não podem divergir só pelo formato.
    return _key_part(left) == _key_part(right)


def _key_part(value: Any) -> str:
    """Forma canônica de uma parte da chave: 1, 1.0 e "1" (JSON vs CSV) viram
    "1"; texto é comparado sem espaços nas pontas. "0012" continua "0012"."""
    if value is None:
        return "<NULL>"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


Dataset = tuple[list[dict[str, Any]], list[str], dict[str, str]]


def _shape_divergences(
    control: Dataset, candidate: Dataset, spec: CompareSpec
) -> list[str]:
    """Pré-condições e contrato: elegibilidade, cardinalidade, colunas e tipos."""
    control_rows, control_declared, control_types = control
    candidate_rows, candidate_declared, candidate_types = candidate
    divergences: list[str] = []
    if spec.require_non_empty and (not control_rows or not candidate_rows):
        divergences.append(
            "Fixture vazio: equivalência não é elegível sem dados não vazios"
        )
    if len(control_rows) != len(candidate_rows):
        divergences.append(
            f"Cardinalidade diverge: controle={len(control_rows)}, candidata={len(candidate_rows)}"
        )
    control_columns = _columns(control_rows, control_declared)
    candidate_columns = _columns(candidate_rows, candidate_declared)
    if [column.upper() for column in control_columns] != [
        column.upper() for column in candidate_columns
    ]:
        divergences.append(
            f"Colunas/aliases divergem: controle={control_columns}, candidata={candidate_columns}"
        )
    for name, expected in control_types.items():
        actual = candidate_types.get(name)
        if actual is not None and actual != expected:
            divergences.append(
                f"Tipo declarado diverge para {name}: controle={expected}, candidata={actual}"
            )
    return divergences


def _null_divergences(
    control_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    names: list[str],
) -> list[str]:
    divergences: list[str] = []
    for name in names:
        control_nulls = sum(_get(row, name) is None for row in control_rows)
        candidate_nulls = sum(_get(row, name) is None for row in candidate_rows)
        if control_nulls != candidate_nulls:
            divergences.append(
                f"Nulos divergem em {name}: controle={control_nulls}, candidata={candidate_nulls}"
            )
    return divergences


def _index_by_key(
    rows: list[dict[str, Any]], keys: list[str], label: str, divergences: list[str]
) -> dict[tuple[str, ...], dict[str, Any]]:
    indexed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(_key_part(_get(row, name)) for name in keys)
        if key in indexed:
            divergences.append(f"Chave duplicada {label}: {key}")
        indexed[key] = row
    return indexed


def _cell_divergences(
    key: tuple[str, ...],
    pair: tuple[dict[str, Any], dict[str, Any]],
    names: list[str],
    spec: CompareSpec,
) -> list[str]:
    metric_names = {metric.upper() for metric in spec.metrics}
    divergences: list[str] = []
    for name in names:
        left_value, right_value = _get(pair[0], name), _get(pair[1], name)
        if not _same_value(left_value, right_value, name.upper() in metric_names, spec):
            divergences.append(
                f"Valor diverge em {name}, chave={key}: controle={left_value!r}, candidata={right_value!r}"
            )
    return divergences


def _keyed_divergences(
    control_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    names: list[str],
    spec: CompareSpec,
) -> list[str]:
    """Casa as linhas pela chave e compara coluna a coluna."""
    divergences: list[str] = []
    control_map = _index_by_key(control_rows, spec.keys, "no controle", divergences)
    candidate_map = _index_by_key(
        candidate_rows, spec.keys, "na candidata", divergences
    )
    missing = sorted(set(control_map) - set(candidate_map))
    extra = sorted(set(candidate_map) - set(control_map))
    if missing:
        divergences.append(f"Chaves ausentes na candidata: {missing[:3]}")
    if extra:
        divergences.append(f"Chaves extras na candidata: {extra[:3]}")
    for key in sorted(set(control_map) & set(candidate_map)):
        divergences += _cell_divergences(
            key, (control_map[key], candidate_map[key]), names, spec
        )
    return divergences


def _missing_names(
    dataset: Dataset, requested: dict[str, str], label: str
) -> list[str]:
    """Nomes pedidos (nome -> papel) que não existem nas colunas do dataset."""
    known = {column.upper() for column in _columns(dataset[0], dataset[1])}
    if not known:
        return (
            []
        )  # dataset vazio sem colunas declaradas: sinalizado em collect_warnings
    return [
        f"{role} '{name}' não existe no {label}: colunas={sorted(known)}"
        for name, role in requested.items()
        if name.upper() not in known
    ]


def _requested_names(spec: CompareSpec) -> dict[str, str]:
    requested: dict[str, str] = {}
    for role, values in (
        ("Chave", spec.keys),
        ("Métrica", spec.metrics),
        ("Coluna", spec.columns),
    ):
        for name in values:
            requested.setdefault(name, role)
    return requested


def _metric_type_divergences(
    rows: list[dict[str, Any]], metrics: list[str], label: str
) -> list[str]:
    """Métrica aceita número ou nulo; texto não numérico nunca vira 0."""
    divergences: list[str] = []
    for name in metrics:
        bad = [
            value
            for value in (_get(row, name) for row in rows)
            if value is not None and _number(value) is None
        ]
        if bad:
            divergences.append(
                f"Valor não numérico na métrica {name} ({label}): {len(bad)} linha(s), ex.={bad[0]!r}"
            )
    return divergences


def _sort_key(
    row: dict[str, Any], names: list[str], metric_names: set[str]
) -> tuple[Any, ...]:
    # Colunas exatas primeiro e métricas por último: valores de métrica que
    # diferem dentro da tolerância não reordenam linhas entre os dois lados.
    exact: list[Any] = []
    metrics: list[Any] = []
    for name in names:
        value = _get(row, name)
        if name.upper() in metric_names:
            metrics.append((0, 0.0) if value is None else (1, _number(value) or 0.0))
        else:
            exact.append((0, "") if value is None else (1, _key_part(value)))
    return (*exact, *metrics)


def _multiset_divergences(
    control_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    names: list[str],
    spec: CompareSpec,
) -> list[str]:
    """Sem chave: ordena as duas listas e compara linha a linha (multiconjunto)."""
    if len(control_rows) != len(candidate_rows):
        return []  # cardinalidade já reportada
    metric_names = {metric.upper() for metric in spec.metrics}
    left = sorted(control_rows, key=lambda row: _sort_key(row, names, metric_names))
    right = sorted(candidate_rows, key=lambda row: _sort_key(row, names, metric_names))
    divergences: list[str] = []
    for index, pair in enumerate(zip(left, right, strict=True)):
        found = _cell_divergences((f"#{index}",), pair, names, spec)
        if found:
            divergences.append(
                f"Linha {index} do multiconjunto ordenado diverge: {found[0]}"
            )
            if len(divergences) >= 20:
                break
    return divergences


def collect_warnings(control: Dataset, candidate: Dataset) -> list[str]:
    warnings: list[str] = []
    if not control[0] and not candidate[0]:
        warnings.append(
            "Ambos os datasets vazios: nada foi comparado (equivalência vácua)"
        )
    for label, dataset in (("controle", control), ("candidata", candidate)):
        if not _columns(dataset[0], dataset[1]):
            warnings.append(
                f"Colunas do {label} desconhecidas (vazio sem colunas declaradas)"
            )
    return warnings


def compare(control: Dataset, candidate: Dataset, spec: CompareSpec) -> list[str]:
    control_rows, candidate_rows = control[0], candidate[0]
    divergences = _shape_divergences(control, candidate, spec)
    requested = _requested_names(spec)
    missing = _missing_names(control, requested, "controle") + _missing_names(
        candidate, requested, "candidata"
    )
    if missing:
        return divergences + missing  # sem colunas válidas, comparar seria vácuo
    key_names = {key.upper() for key in spec.keys}
    names = spec.columns or [
        column
        for column in _columns(control_rows, control[1])
        if column.upper() not in key_names
    ]
    present = {name.upper() for name in names}
    names = names + [metric for metric in spec.metrics if metric.upper() not in present]
    type_errors = _metric_type_divergences(
        control_rows, spec.metrics, "controle"
    ) + _metric_type_divergences(candidate_rows, spec.metrics, "candidata")
    divergences += type_errors
    divergences += _null_divergences(control_rows, candidate_rows, names)
    if spec.keys:
        divergences += _keyed_divergences(control_rows, candidate_rows, names, spec)
    elif not type_errors:
        divergences += _multiset_divergences(control_rows, candidate_rows, names, spec)
    return divergences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controle", required=True, type=Path)
    parser.add_argument("--candidata", required=True, type=Path)
    parser.add_argument("--chaves", default="")
    parser.add_argument("--metricas", default="")
    parser.add_argument("--colunas", default="")
    parser.add_argument(
        "--tolerancia",
        type=float,
        default=1e-6,
        help="tolerância ABSOLUTA para métricas numéricas (padrão 1e-6)",
    )
    parser.add_argument(
        "--tolerancia-relativa",
        type=float,
        default=1e-12,
        help="tolerância RELATIVA para métricas numéricas (padrão 1e-12)",
    )
    parser.add_argument("--permitir-vazio", action="store_true")
    parser.add_argument("--relatorio", type=Path)
    args = parser.parse_args(argv)
    try:
        control = _load(args.controle)
        candidate = _load(args.candidata)
        spec = CompareSpec(
            keys=[item.strip() for item in args.chaves.split(",") if item.strip()],
            metrics=[item.strip() for item in args.metricas.split(",") if item.strip()],
            columns=[item.strip() for item in args.colunas.split(",") if item.strip()],
            tolerance=args.tolerancia,
            require_non_empty=not args.permitir_vazio,
            rel_tolerance=args.tolerancia_relativa,
        )
        divergences = compare(control, candidate, spec)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    report = {
        "schema": "oracle-equivalence/v1",
        "version": VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "control_sha256": _sha256(args.controle),
        "candidate_sha256": _sha256(args.candidata),
        "control_rows": len(control[0]),
        "candidate_rows": len(candidate[0]),
        "tolerance": args.tolerancia,
        "rel_tolerance": args.tolerancia_relativa,
        "warnings": collect_warnings(control, candidate),
        "divergences": divergences,
        "status": "EQUIVALENCIA_TOTAL" if not divergences else "DIVERGENCIA",
    }
    if args.relatorio:
        args.relatorio.parent.mkdir(parents=True, exist_ok=True)
        args.relatorio.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if divergences:
        print(f"DIVERGENCIA DETECTADA ({len(divergences)} problemas):", file=sys.stderr)
        for item in divergences[:20]:
            print(f"  - {item}", file=sys.stderr)
        return 1
    for warning in collect_warnings(control, candidate):
        print(f"AVISO: {warning}", file=sys.stderr)
    print(f"EQUIVALENCIA TOTAL: {len(control[0])} registros conferidos com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

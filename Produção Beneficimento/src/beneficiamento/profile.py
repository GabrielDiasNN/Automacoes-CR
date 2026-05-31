"""Profiling leve de colunas para snapshots do Beneficiamento."""
# pylint: disable=missing-class-docstring,too-many-instance-attributes

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass
class ColumnProfile:
    name: str
    non_null: int = 0
    null: int = 0
    distinct_values: set[str] = field(default_factory=set)
    sample_values: list[str] = field(default_factory=list)
    numeric_values: list[float] = field(default_factory=list)
    min_value: Any = None
    max_value: Any = None

    def add(self, value: Any, sample_limit: int) -> None:
        if value is None:
            self.null += 1
            return
        self.non_null += 1
        normalized = normalize_value(value)
        if len(self.sample_values) < sample_limit:
            self.sample_values.append(normalized)
        if len(self.distinct_values) < 200000:
            self.distinct_values.add(normalized)
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            self.numeric_values.append(float(value))
        if isinstance(value, (datetime, date, int, float, Decimal, str)):
            if self.min_value is None or value < self.min_value:
                self.min_value = value
            if self.max_value is None or value > self.max_value:
                self.max_value = value


def normalize_value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value).strip()


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def rows_to_records(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [
        {column: serialize_value(value) for column, value in zip(columns, row)}
        for row in rows
    ]


def profile_rows(
    columns: list[str], rows: list[tuple[Any, ...]], sample_limit: int
) -> list[ColumnProfile]:
    profiles = [ColumnProfile(name=column) for column in columns]
    for row in rows:
        for profile, value in zip(profiles, row):
            profile.add(value, sample_limit)
    return profiles


def summarize_profiles(
    profiles: list[ColumnProfile],
    total_rows: int,
    duplicate_columns: dict[str, list[int]],
) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    constant_columns: list[str] = []
    mostly_null_columns: list[str] = []
    high_cardinality_columns: list[str] = []

    for profile in profiles:
        distinct_count = len(profile.distinct_values)
        null_ratio = round(profile.null / total_rows, 4) if total_rows else 0.0
        non_null_ratio = round(profile.non_null / total_rows, 4) if total_rows else 0.0
        summary = {
            "column": profile.name,
            "non_null": profile.non_null,
            "null": profile.null,
            "null_ratio": null_ratio,
            "non_null_ratio": non_null_ratio,
            "distinct_count": distinct_count,
            "sample_values": profile.sample_values,
        }
        if profile.min_value is not None:
            summary["min"] = normalize_value(profile.min_value)
        if profile.max_value is not None:
            summary["max"] = normalize_value(profile.max_value)
        columns.append(summary)

        if total_rows and profile.non_null == total_rows and distinct_count == 1:
            constant_columns.append(profile.name)
        if total_rows and null_ratio >= 0.95:
            mostly_null_columns.append(profile.name)
        if total_rows and distinct_count / total_rows >= 0.80:
            high_cardinality_columns.append(profile.name)

    return {
        "total_rows": total_rows,
        "total_columns": len(profiles),
        "duplicate_source_names": duplicate_columns,
        "constant_columns": constant_columns,
        "mostly_null_columns": mostly_null_columns,
        "high_cardinality_columns": high_cardinality_columns,
        "columns": columns,
    }

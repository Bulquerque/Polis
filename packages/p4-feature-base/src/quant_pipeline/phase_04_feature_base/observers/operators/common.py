from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from fnmatch import fnmatchcase
from typing import Any

from ...runtime.datetime_utils import parse_aware_datetime


def numeric_value(row: Mapping[str, Any]) -> float | None:
    if row.get("value_number") is not None:
        return float(row["value_number"])
    if row.get("value_integer") is not None:
        return float(row["value_integer"])
    if row.get("value_boolean") is not None:
        return float(bool(row["value_boolean"]))
    return None


def matches(variable_id: str, pattern: str) -> bool:
    return fnmatchcase(variable_id.lower(), pattern.lower())


def series_by_entity(
    records: list[Mapping[str, Any]],
    pattern: str,
) -> dict[str, list[tuple[datetime, Mapping[str, Any], float]]]:
    grouped: dict[str, list[tuple[datetime, Mapping[str, Any], float]]] = (
        defaultdict(list)
    )
    for row in records:
        if not matches(str(row.get("variable_id", "")), pattern):
            continue
        value = numeric_value(row)
        if value is None:
            continue
        when = parse_aware_datetime(row["decision_time"], "decision_time")
        grouped[str(row["entity_id"])].append((when, row, value))
    for values in grouped.values():
        values.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("source_record_id", "")),
            )
        )
    return dict(grouped)


def feature_record(
    spec: Mapping[str, Any],
    row: Mapping[str, Any],
    value: float | None,
    status: str,
    *,
    entity_id: str | None = None,
) -> dict[str, Any]:
    return {
        "observer_id": spec["observer_id"],
        "hypothesis_id": spec["hypothesis_id"],
        "family_id": spec["family_id"],
        "decision_time": row["decision_time"],
        "entity_id": entity_id or str(row.get("entity_id")),
        "feature_value": value,
        "execution_status": status,
        "input_variable_ids": list(spec["input_variables"]),
        "parameter_role": spec["parameter_role"],
        "source_observation_id": str(row.get("observation_id", "")),
        "source_lineage_id": str(row.get("source_lineage_id", "")),
    }

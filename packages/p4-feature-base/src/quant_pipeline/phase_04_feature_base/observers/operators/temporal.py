from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from math import sqrt
from statistics import fmean
from typing import Any

from .common import feature_record, series_by_entity

CAUSAL_OPERATORS = frozenset(
    {
        "identity",
        "lag",
        "difference",
        "return",
        "rolling_mean",
        "rolling_std",
        "ewma",
        "zscore",
        "slope",
        "drawdown",
        "rank",
    }
)


def _window(values: list[float], index: int, size: int) -> list[float]:
    return values[max(0, index - size + 1) : index + 1]


def _mean(values: list[float]) -> float:
    return float(fmean(values))


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance)


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = _mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    numerator = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    )
    return numerator / denominator


def _ewma(sample: list[float], span: float) -> float:
    alpha = 2.0 / (span + 1.0)
    level = sample[0]
    for value in sample[1:]:
        level = alpha * value + (1 - alpha) * level
    return level


def _lagged_value(
    operator: str,
    values: list[float],
    index: int,
    periods: int,
) -> tuple[float | None, str]:
    if index < periods:
        return None, "INSUFFICIENT_HISTORY"
    previous = values[index - periods]
    if operator == "lag":
        return previous, "READY"
    if operator == "difference":
        return values[index] - previous, "READY"
    if previous == 0:
        return None, "NUMERIC_DOMAIN_ERROR"
    return values[index] / previous - 1.0, "READY"


def _window_value(
    operator: str,
    current: float,
    sample: list[float],
    parameters: Mapping[str, Any],
) -> tuple[float, str]:
    if operator == "rolling_mean":
        return _mean(sample), "READY"
    if operator == "rolling_std":
        return _std(sample), "READY"
    if operator == "zscore":
        deviation = _std(sample)
        return (0.0 if deviation == 0 else (current - _mean(sample)) / deviation), "READY"
    if operator == "slope":
        return _slope(sample), "READY"
    if operator == "drawdown":
        peak = max(sample)
        return (0.0 if peak == 0 else current / peak - 1.0), "READY"
    span = float(parameters.get("span", len(sample)))
    return _ewma(sample, span), "READY"


def _point(
    operator: str,
    values: list[float],
    index: int,
    parameters: Mapping[str, Any],
) -> tuple[float | None, str]:
    current = values[index]
    if operator == "identity":
        return current, "READY"
    periods = int(parameters.get("periods", 1))
    if operator in {"lag", "difference", "return"}:
        return _lagged_value(operator, values, index, periods)
    window = int(parameters.get("window", 5))
    sample = _window(values, index, window)
    if len(sample) < window:
        return None, "INSUFFICIENT_HISTORY"
    return _window_value(operator, current, sample, parameters)


def _rank_records(
    spec: Mapping[str, Any],
    records: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped = series_by_entity(records, str(spec["input_variables"][0]))
    by_time: dict[str, list[tuple[str, Mapping[str, Any], float]]] = defaultdict(list)
    for entity, series in grouped.items():
        for _, row, value in series:
            by_time[str(row["decision_time"])].append((entity, row, value))
    output: list[dict[str, Any]] = []
    for items in (by_time[key] for key in sorted(by_time)):
        ordered_values = sorted(set(value for _, _, value in items))
        ranks = {
            value: (ordered_values.index(value) + 1) / len(ordered_values)
            for value in ordered_values
        }
        for entity, row, value in sorted(items, key=lambda item: item[0]):
            output.append(
                feature_record(
                    spec,
                    row,
                    ranks[value],
                    "READY",
                    entity_id=entity,
                )
            )
    return output


def _series_records(
    spec: Mapping[str, Any],
    records: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    feature_rows: list[dict[str, Any]] = []
    grouped = series_by_entity(records, str(spec["input_variables"][0]))
    for entity, series in sorted(grouped.items()):
        values = [item[2] for item in series]
        for index, (_, row, _) in enumerate(series):
            value, status = _point(
                str(spec["operator"]),
                values,
                index,
                spec.get("parameters", {}),
            )
            feature_rows.append(
                feature_record(spec, row, value, status, entity_id=entity)
            )
    return feature_rows


def execute_causal(
    specs: list[Mapping[str, Any]],
    records: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    for spec in specs:
        operator = str(spec["operator"])
        if operator not in CAUSAL_OPERATORS:
            continue
        feature_rows = (
            _rank_records(spec, records)
            if operator == "rank"
            else _series_records(spec, records)
        )
        output.extend(feature_rows)
        states.append(
            {
                "observer_id": spec["observer_id"],
                "operator": operator,
                "execution_status": (
                    "COMPLETED" if feature_rows else "UNAVAILABLE_INPUT"
                ),
                "record_count": len(feature_rows),
                "parameters": dict(spec.get("parameters", {})),
            }
        )
    output.sort(
        key=lambda item: (
            item["observer_id"],
            item["decision_time"],
            item["entity_id"],
        )
    )
    states.sort(key=lambda item: item["observer_id"])
    return output, states

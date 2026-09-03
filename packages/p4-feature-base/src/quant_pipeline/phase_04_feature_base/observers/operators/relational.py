from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from math import sqrt
from statistics import fmean
from typing import Any

import numpy as np

from .common import feature_record, series_by_entity

RELATIONAL_OPERATORS = frozenset(
    {
        "beta",
        "correlation",
        "residual",
        "spread",
        "market_mode_share",
        "connectedness_proxy",
    }
)


def _aligned(
    records: list[Mapping[str, Any]],
    left_pattern: str,
    right_pattern: str,
) -> dict[str, list[tuple[Mapping[str, Any], float, float]]]:
    left = series_by_entity(records, left_pattern)
    right = series_by_entity(records, right_pattern)
    result: dict[str, list[tuple[Mapping[str, Any], float, float]]] = {}
    for entity in sorted(set(left) & set(right)):
        right_by_time = {
            str(row["decision_time"]): value
            for _, row, value in right[entity]
        }
        values = [
            (row, value, right_by_time[str(row["decision_time"])])
            for _, row, value in left[entity]
            if str(row["decision_time"]) in right_by_time
        ]
        if values:
            result[entity] = values
    return result


def _fit(y_values: list[float], x_values: list[float], alpha: float) -> tuple[float, float]:
    design = np.column_stack(
        [np.ones(len(x_values)), np.asarray(x_values, dtype=float)]
    )
    target = np.asarray(y_values, dtype=float)
    gram = design.T @ design
    gram[1, 1] += alpha
    coefficients = np.linalg.solve(gram, design.T @ target)
    return float(coefficients[0]), float(coefficients[1])


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return 0.0
    left_mean = fmean(left)
    right_mean = fmean(right)
    left_dev = [value - left_mean for value in left]
    right_dev = [value - right_mean for value in right]
    denominator = sqrt(
        sum(value * value for value in left_dev)
        * sum(value * value for value in right_dev)
    )
    if denominator == 0:
        return 0.0
    numerator = sum(
        left_value * right_value
        for left_value, right_value in zip(left_dev, right_dev, strict=True)
    )
    return numerator / denominator


def _spread_records(
    spec: Mapping[str, Any],
    aligned: dict[str, list[tuple[Mapping[str, Any], float, float]]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for entity, series in aligned.items():
        for row, left, right in series:
            output.append(
                feature_record(
                    spec,
                    row,
                    left - right,
                    "READY",
                    entity_id=entity,
                )
            )
    return output


def _rolling_pair_records(
    spec: Mapping[str, Any],
    aligned: dict[str, list[tuple[Mapping[str, Any], float, float]]],
) -> list[dict[str, Any]]:
    operator = str(spec["operator"])
    parameters = spec.get("parameters", {})
    window = int(parameters.get("window", 5))
    alpha = float(parameters.get("ridge_alpha", 1e-8))
    output: list[dict[str, Any]] = []
    for entity, series in aligned.items():
        for index, (row, left, right) in enumerate(series):
            sample = series[max(0, index - window + 1) : index + 1]
            if len(sample) < window:
                output.append(
                    feature_record(
                        spec,
                        row,
                        None,
                        "INSUFFICIENT_HISTORY",
                        entity_id=entity,
                    )
                )
                continue
            left_values = [item[1] for item in sample]
            right_values = [item[2] for item in sample]
            if operator == "correlation":
                value = _correlation(left_values, right_values)
            else:
                intercept, beta = _fit(left_values, right_values, alpha)
                value = beta if operator == "beta" else left - (intercept + beta * right)
            output.append(
                feature_record(spec, row, value, "READY", entity_id=entity)
            )
    return output


def _pair_spec(
    spec: Mapping[str, Any],
    records: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    inputs = list(spec["input_variables"])
    aligned = _aligned(records, inputs[0], inputs[1])
    if spec["operator"] == "spread":
        return _spread_records(spec, aligned)
    return _rolling_pair_records(spec, aligned)


def _system_inputs(
    spec: Mapping[str, Any],
    records: list[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, float]], dict[str, Mapping[str, Any]]]:
    grouped = series_by_entity(records, str(spec["input_variables"][0]))
    by_time: dict[str, dict[str, float]] = defaultdict(dict)
    row_by_time: dict[str, Mapping[str, Any]] = {}
    for entity, series in grouped.items():
        for _, row, value in series:
            decision_time = str(row["decision_time"])
            by_time[decision_time][entity] = value
            row_by_time[decision_time] = row
    return dict(by_time), row_by_time


def _system_value(operator: str, matrix: np.ndarray) -> float:
    correlation = np.nan_to_num(
        np.corrcoef(matrix, rowvar=False),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    entity_count = correlation.shape[0]
    if operator == "market_mode_share":
        eigenvalues = np.linalg.eigvalsh(correlation)
        return float(
            max(eigenvalues) / max(float(sum(eigenvalues)), 1e-12)
        )
    numerator = np.abs(correlation).sum() - entity_count
    denominator = max(entity_count * (entity_count - 1), 1)
    return float(numerator / denominator)


def _system_spec(
    spec: Mapping[str, Any],
    records: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    parameters = spec.get("parameters", {})
    window = int(parameters.get("window", 5))
    minimum_entities = int(parameters.get("min_entities", 2))
    by_time, row_by_time = _system_inputs(spec, records)
    times = sorted(by_time)
    output: list[dict[str, Any]] = []
    for index, decision_time in enumerate(times):
        window_times = times[max(0, index - window + 1) : index + 1]
        entity_sets = [set(by_time[item]) for item in window_times]
        entities = sorted(set.intersection(*entity_sets)) if entity_sets else []
        if len(window_times) < window or len(entities) < minimum_entities:
            output.append(
                feature_record(
                    spec,
                    row_by_time[decision_time],
                    None,
                    "INSUFFICIENT_HISTORY",
                    entity_id="__SYSTEM__",
                )
            )
            continue
        matrix = np.asarray(
            [[by_time[item][entity] for entity in entities] for item in window_times],
            dtype=float,
        )
        value = _system_value(str(spec["operator"]), matrix)
        output.append(
            feature_record(
                spec,
                row_by_time[decision_time],
                value,
                "READY",
                entity_id="__SYSTEM__",
            )
        )
    return output


def execute_relational(
    specs: list[Mapping[str, Any]],
    records: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    for spec in specs:
        operator = str(spec["operator"])
        if operator not in RELATIONAL_OPERATORS:
            continue
        feature_rows = (
            _system_spec(spec, records)
            if operator in {"market_mode_share", "connectedness_proxy"}
            else _pair_spec(spec, records)
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

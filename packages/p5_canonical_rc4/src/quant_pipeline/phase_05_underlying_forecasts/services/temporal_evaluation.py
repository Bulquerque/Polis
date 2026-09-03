"""Target-specific, session-indexed walk-forward planning with purge and embargo."""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from typing import Any

from ..domain.training import TemporalEvaluationPlan, TemporalFold, TemporalPartition
from ..errors import DataQualityError, ReasonCode
from .identifiers import as_utc, iso_utc

_WINDOW_TYPES = {"EXPANDING", "ROLLING", "ANCHORED"}


def build_evaluation_plan(
    records: list[dict[str, Any]], *, window_type: str = "EXPANDING",
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = window_type.upper()
    if normalized not in _WINDOW_TYPES:
        raise DataQualityError(f"unsupported walk-forward window type: {window_type}")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(str(row["target_id"]), str(row["horizon"]))].append(row)
    target_plans = [_target_plan(key, rows, normalized) for key, rows in sorted(grouped.items())]
    folds = tuple(
        TemporalFold.model_validate(fold)
        for plan in target_plans
        for fold in plan["folds"]
    )
    plan_model = TemporalEvaluationPlan(
        folds=folds,
        session_source="OBSERVED_POINT_IN_TIME_TRADING_SESSIONS",
    )
    latest = target_plans[0]["folds"][-1]
    compatibility_partitions = {
        row["name"]: row["timestamps"] for row in latest["partitions"]
    }
    plan = {
        **plan_model.model_dump(mode="json"),
        "target_plans": target_plans,
        "partitions": compatibility_partitions,
        "purge_policy": "TARGET_LABEL_AVAILABILITY_STRICTLY_BEFORE_NEXT_PARTITION",
        "embargo_policy": "TARGET_HORIZON_SESSION_SPAN",
    }
    receipt = _receipt(target_plans)
    return plan, receipt


def select_target_folds(
    plan: dict[str, Any], target_id: str, horizon: str,
) -> list[dict[str, Any]]:
    for row in plan.get("target_plans", []):
        if row.get("target_id") == target_id and row.get("horizon") == horizon:
            return list(row.get("folds", []))
    raise DataQualityError(
        f"temporal plan lacks target {target_id}/{horizon}",
        reason_code=ReasonCode.TARGET_UNAVAILABLE,
    )


def _target_plan(
    key: tuple[str, str], rows: list[dict[str, Any]], window_type: str,
) -> dict[str, Any]:
    timestamps = sorted({as_utc(row["prediction_timestamp"]) for row in rows})
    if len(timestamps) < 24:
        raise DataQualityError(
            f"target {key[0]}/{key[1]} requires at least 24 distinct sessions",
            reason_code=ReasonCode.INSUFFICIENT_HISTORY,
        )
    test_size = max(3, int(round(len(timestamps) * 0.12)))
    development, test = timestamps[:-test_size], timestamps[-test_size:]
    validation_size = max(3, min(10, len(development) // 12))
    calibration_size = max(3, min(10, len(development) // 12))
    fold_count = min(3, (len(development) - 10) // (validation_size + calibration_size))
    if fold_count < 2:
        raise DataQualityError("walk-forward planning could not create two folds")
    holdout = fold_count * (validation_size + calibration_size)
    base_train_end = len(development) - holdout
    availability = _availability_by_timestamp(rows)
    embargo = _embargo_sessions(timestamps, rows)
    folds = []
    for index in range(fold_count):
        train_end = base_train_end + index * (validation_size + calibration_size)
        validation_end = train_end + validation_size
        calibration_end = validation_end + calibration_size
        train = _training_window(development, train_end, window_type, base_train_end)
        validation = development[train_end:validation_end]
        calibration = development[validation_end:calibration_end]
        partitions, purge_count = _purge_and_embargo(
            train, validation, calibration, test, availability, embargo,
        )
        fold = TemporalFold(
            fold_id=f"{key[0]}-{key[1]}-fold-{index + 1:02d}",
            window_type=window_type,
            target_id=key[0],
            horizon=key[1],
            partitions=tuple(
                TemporalPartition(name=name, timestamps=tuple(partitions[name]))
                for name in ("TRAIN", "VALIDATION", "CALIBRATION", "TEST")
            ),
            purge_count=purge_count,
            embargo_sessions=embargo,
            calendar_id="P5_DEFAULT_TRADING_CALENDAR",
        )
        folds.append(fold.model_dump(mode="json"))
    return {
        "target_id": key[0],
        "horizon": key[1],
        "folds": folds,
        "test_sealed": True,
        "test_session_count": len(test),
    }


def _training_window(
    development: list, train_end: int, window_type: str, base_train_end: int,
) -> list:
    if window_type in {"EXPANDING", "ANCHORED"}:
        return development[:train_end]
    width = max(base_train_end, 24)
    return development[max(0, train_end - width):train_end]


def _availability_by_timestamp(records: list[dict[str, Any]]) -> dict:
    output = {}
    for row in records:
        timestamp = as_utc(row["prediction_timestamp"])
        availability = max(as_utc(row["label_end_time"]), as_utc(row["available_at"]))
        output[timestamp] = max(output.get(timestamp, availability), availability)
    return output


def _embargo_sessions(timestamps: list, records: list[dict[str, Any]]) -> int:
    positions = {value: index for index, value in enumerate(timestamps)}
    spans = []
    for row in records:
        start = as_utc(row["prediction_timestamp"])
        end = max(as_utc(row["label_end_time"]), as_utc(row["available_at"]))
        spans.append(max(0, bisect_right(timestamps, end) - positions[start] - 1))
    return max(spans, default=0)


def _purge_and_embargo(
    train: list, validation: list, calibration: list, test: list,
    availability: dict, embargo: int,
) -> tuple[dict[str, list], int]:
    partitions = {
        "TRAIN": list(train),
        "VALIDATION": list(validation),
        "CALIBRATION": list(calibration),
        "TEST": list(test),
    }
    purge_count = 0
    for previous, following in (("TRAIN", "VALIDATION"), ("VALIDATION", "CALIBRATION"), ("CALIBRATION", "TEST")):
        boundary = partitions[following][0]
        retained = [value for value in partitions[previous] if availability[value] < boundary]
        purge_count += len(partitions[previous]) - len(retained)
        partitions[previous] = retained
    if embargo:
        partitions["VALIDATION"] = partitions["VALIDATION"][embargo:]
        partitions["CALIBRATION"] = partitions["CALIBRATION"][embargo:]
    if any(not partitions[name] for name in partitions):
        raise DataQualityError("purge or embargo emptied a walk-forward partition")
    return partitions, purge_count


def _receipt(target_plans: list[dict[str, Any]]) -> dict[str, Any]:
    folds = [fold for plan in target_plans for fold in plan["folds"]]
    return {
        "sealed_holdout": "TEST",
        "excluded_from_training": True,
        "excluded_from_development_metrics": True,
        "target_specific": True,
        "target_plan_count": len(target_plans),
        "fold_count": len(folds),
        "purged_timestamp_count": sum(int(fold["purge_count"]) for fold in folds),
        "maximum_embargo_sessions": max(int(fold["embargo_sessions"]) for fold in folds),
        "fold_ids": [fold["fold_id"] for fold in folds],
        "test_ranges": [
            {
                "target_id": plan["target_id"],
                "horizon": plan["horizon"],
                "start": next(row["timestamps"][0] for row in plan["folds"][-1]["partitions"] if row["name"] == "TEST"),
                "end": next(row["timestamps"][-1] for row in plan["folds"][-1]["partitions"] if row["name"] == "TEST"),
            }
            for plan in target_plans
        ],
    }

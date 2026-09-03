"""Point-in-time-safe readers for native P4 V14.9 views and P2 outcomes."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np

from ..errors import CapabilityUnavailableError, DataQualityError, LeakageError
from .feature_semantics import aliases
from .horizon_policy import allowed_horizon_groups, primary_horizon_group
from .identifiers import as_utc, horizon_delta

FORBIDDEN_FIELDS = {
    "target", "label", "future_return", "future_volatility", "prediction",
    "signal_direction", "buy_sell_signal", "candidate_id", "candidate_score",
    "rank_score", "portfolio_weight", "trade_decision", "realized_pnl",
    "execution_fill", "position_size",
}
_ALLOWED_QUALITY = {"PASS", "PASS_WITH_LIMITATIONS"}
_ALLOWED_MISSINGNESS = {"EXPLICIT_MASK", "NONE", "PRECOMPUTED_IMPUTATION"}


def assert_no_forbidden_fields(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        overlap = FORBIDDEN_FIELDS.intersection(value)
        if overlap:
            raise LeakageError(f"forbidden fields at {path}: {sorted(overlap)}")
        for key, item in value.items():
            assert_no_forbidden_fields(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_no_forbidden_fields(item, path=f"{path}[{index}]")


def normalize_view_bundle(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    views = bundle.get("views")
    if not isinstance(views, list) or not views:
        raise DataQualityError("consumer view bundle requires non-empty views")
    normalized: dict[str, dict[str, Any]] = {}
    for raw in views:
        if not isinstance(raw, dict):
            raise DataQualityError("consumer view must be an object")
        view_id = str(raw.get("view_id", "")).strip()
        if not view_id or view_id in normalized:
            raise DataQualityError(f"missing or duplicate consumer view_id: {view_id!r}")
        records = raw.get("records")
        if not isinstance(records, list) or not records:
            raise DataQualityError(f"consumer view {view_id} requires records")
        quality = str(raw.get("quality_state", "")).strip()
        if quality not in _ALLOWED_QUALITY:
            raise DataQualityError(f"consumer view {view_id} quality is not consumable: {quality}")
        lineage = str(raw.get("lineage_id", "")).strip()
        if not lineage:
            raise DataQualityError(f"consumer view {view_id} requires lineage_id")
        grain = tuple(raw.get("grain", ()))
        if not {"underlying", "decision_time", "horizon_group"}.issubset(grain):
            raise DataQualityError(f"consumer view {view_id} has invalid native grain")
        missingness = str(raw.get("missingness_policy", "")).strip()
        if missingness not in _ALLOWED_MISSINGNESS:
            raise DataQualityError(f"unsupported missingness policy for {view_id}: {missingness}")
        assert_no_forbidden_fields(records, path=f"view[{view_id}]")
        _validate_record_keys(records, view_id)
        normalized[view_id] = {
            **raw, "view_id": view_id, "grain": grain, "records": records,
            "missingness_policy": missingness, "lineage_id": lineage,
            "quality_state": quality,
        }
    return normalized


def _validate_record_keys(records: list[dict[str, Any]], view_id: str) -> None:
    seen: set[tuple[str, datetime, str]] = set()
    for raw in records:
        if not isinstance(raw, dict):
            raise DataQualityError(f"view {view_id} record must be an object")
        entity = str(raw.get("underlying") or "").strip()
        timestamp = raw.get("decision_time") or raw.get("as_of_time")
        horizon_group = str(raw.get("horizon_group") or "").strip()
        if not entity or timestamp is None or not horizon_group:
            raise DataQualityError(f"view {view_id} record lacks entity/time/horizon_group")
        key = (entity, as_utc(timestamp), horizon_group)
        if key in seen:
            raise DataQualityError(f"duplicate native view key for {view_id}: {key}")
        seen.add(key)


def feature_rows(view: dict[str, Any], *, as_of_time: datetime | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in view.get("records", []):
        entity = str(raw.get("underlying") or "").strip()
        timestamp = raw.get("decision_time") or raw.get("as_of_time")
        horizon_group = str(raw.get("horizon_group") or "").strip()
        features = raw.get("features")
        if not entity or timestamp is None or not horizon_group or not isinstance(features, dict):
            raise DataQualityError("feature row requires entity/time/horizon_group/features")
        decision_time = as_utc(timestamp)
        if raw.get("available_at") is None:
            raise DataQualityError("feature row requires explicit available_at")
        available_at = as_utc(raw["available_at"])
        if available_at > decision_time:
            raise LeakageError("P4 feature available_at exceeds decision_time")
        if as_of_time is not None and (decision_time > as_of_time or available_at > as_of_time):
            continue
        numeric = _numeric_features(features)
        if not numeric or all(value is None for value in numeric.values()):
            continue
        lineage = str(raw.get("lineage_id") or view.get("lineage_id") or "").strip()
        if not lineage:
            raise DataQualityError("feature row requires lineage_id")
        rows.append({
            "underlying": entity, "decision_time": decision_time, "as_of_time": decision_time,
            "available_at": available_at, "horizon_group": horizon_group,
            "features": numeric, "missingness_mask": dict(raw.get("missingness_mask", {})),
            "feature_state_ids": dict(raw.get("feature_state_ids", {})),
            "quality_state": str(raw.get("quality_state", "PASS")), "lineage_id": lineage,
        })
    return sorted(rows, key=lambda row: (row["decision_time"], row["underlying"], row["horizon_group"]))


def _numeric_features(features: dict[str, Any]) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    for key, value in features.items():
        if value is None:
            output[str(key)] = None
            continue
        number = float(value)
        if not np.isfinite(number):
            raise DataQualityError(f"feature {key} is non-finite")
        output[str(key)] = number
    return output


def target_rows(
    bundle: dict[str, Any], *, training_cutoff: datetime | None = None,
) -> list[dict[str, Any]]:
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise DataQualityError("offline outcome bundle requires records")
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, datetime, str, str]] = set()
    for raw in records:
        timestamp = raw.get("prediction_timestamp") or raw.get("as_of_time")
        label_end = raw.get("label_end_time") or raw.get("realized_at")
        if timestamp is None or label_end is None:
            raise DataQualityError("outcome requires prediction_timestamp and label_end_time")
        prediction_timestamp, label_end_time = as_utc(timestamp), as_utc(label_end)
        if raw.get("available_at") is None:
            raise DataQualityError("outcome requires explicit available_at")
        available_at = as_utc(raw["available_at"])
        if label_end_time <= prediction_timestamp or available_at < label_end_time:
            raise DataQualityError("outcome temporal order is invalid")
        if training_cutoff is not None and available_at > as_utc(training_cutoff):
            continue
        horizon = str(raw["horizon"]).strip().upper(); horizon_delta(horizon)
        key = (str(raw["underlying"]), prediction_timestamp, str(raw["target_id"]), horizon)
        if key in seen:
            raise DataQualityError(f"duplicate outcome key: {key}")
        seen.add(key)
        value = float(raw["value"])
        if not np.isfinite(value) or (raw.get("unit", "decimal_return") == "decimal_return" and value < -1.0):
            raise DataQualityError("outcome value is invalid")
        lineage = str(raw.get("lineage_id", "")).strip()
        if not lineage:
            raise DataQualityError("outcome requires lineage_id")
        output.append({
            "underlying": key[0], "prediction_timestamp": prediction_timestamp,
            "label_end_time": label_end_time, "available_at": available_at,
            "target_id": key[2], "horizon": key[3], "unit": str(raw.get("unit", "decimal_return")),
            "value": value, "lineage_id": lineage,
        })
    return sorted(output, key=lambda row: (row["prediction_timestamp"], row["underlying"]))


def align_features_targets(
    features: list[dict[str, Any]], targets: list[dict[str, Any]], target_id: str, horizon: str,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], tuple[str, ...]]:
    selected = [row for row in targets if row["target_id"] == target_id and row["horizon"] == horizon]
    by_key = {(row["underlying"], row["prediction_timestamp"]): row for row in selected}
    if len(by_key) != len(selected):
        raise DataQualityError("target alignment key is not unique")
    merged = merge_horizon_rows(features, horizon=horizon)
    feature_names = tuple(sorted({name for row in merged for name in row["features"]}))
    if not feature_names:
        raise DataQualityError("no P4 features align with target horizon")
    aligned, matrix, labels = [], [], []
    for row in merged:
        target = by_key.get((row["underlying"], row["decision_time"]))
        if target is None:
            continue
        matrix.append([np.nan if row["features"].get(name) is None else float(row["features"][name]) for name in feature_names])
        labels.append(target["value"]); aligned.append({**row, **target})
    if len(aligned) < 12:
        raise DataQualityError("at least 12 horizon-aligned observations are required")
    return np.asarray(matrix, dtype=float), np.asarray(labels, dtype=float), aligned, feature_names


def merge_horizon_rows(rows: list[dict[str, Any]], *, horizon: str) -> list[dict[str, Any]]:
    allowed = set(allowed_horizon_groups(horizon)); primary = primary_horizon_group(horizon)
    grouped: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["horizon_group"] in allowed:
            grouped[(row["underlying"], row["decision_time"])].append(row)
    output: list[dict[str, Any]] = []
    for key, candidates in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][0])):
        selected = [row for row in candidates if row["horizon_group"] == primary]
        selected += [row for row in candidates if row["horizon_group"] == "CROSS_HORIZON"]
        if not selected:
            continue
        features: dict[str, float | None] = {}
        state_ids: dict[str, str] = {}
        lineage: list[str] = []
        available_at = max(row["available_at"] for row in selected)
        for row in selected:
            overlap = set(features).intersection(row["features"])
            if overlap:
                raise DataQualityError(f"duplicate feature names across horizon projections: {sorted(overlap)}")
            features.update(row["features"]); state_ids.update(row.get("feature_state_ids", {})); lineage.append(row["lineage_id"])
        output.append({
            "underlying": key[0], "decision_time": key[1], "as_of_time": key[1],
            "available_at": available_at, "horizon_group": primary, "features": features,
            "feature_state_ids": state_ids, "source_horizon_groups": sorted({row["horizon_group"] for row in selected}),
            "lineage_id": "|".join(sorted(lineage)),
        })
    return output


def latest_feature_rows(view: dict[str, Any], *, as_of_time: datetime, horizon: str) -> list[dict[str, Any]]:
    rows = merge_horizon_rows(feature_rows(view, as_of_time=as_of_time), horizon=horizon)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["underlying"]].append(row)
    output = [max(values, key=lambda row: row["decision_time"]) for values in grouped.values()]
    if not output:
        raise DataQualityError("view has no rows available for requested horizon")
    return sorted(output, key=lambda row: row["underlying"])


def series_by_underlying(
    view: dict[str, Any], feature: str, *, as_of_time: datetime | None = None,
    horizon: str = "1D",
) -> dict[str, np.ndarray]:
    grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    rows = merge_horizon_rows(feature_rows(view, as_of_time=as_of_time), horizon=horizon)
    for row in rows:
        value = row["features"].get(feature)
        if value is not None:
            grouped[row["underlying"]].append((row["decision_time"], float(value)))
    return {entity: np.asarray([value for _, value in sorted(values)], dtype=float) for entity, values in grouped.items() if len(values) >= 8}


def semantic_series(
    view: dict[str, Any], role: str, *, as_of_time: datetime | None = None,
    horizon: str = "1D",
) -> tuple[str, dict[str, np.ndarray]]:
    try:
        candidates = aliases(role)
    except KeyError as exc:
        raise DataQualityError(f"unknown P4 feature semantic role: {role}") from exc
    for feature in candidates:
        series = series_by_underlying(view, feature, as_of_time=as_of_time, horizon=horizon)
        if series:
            return feature, series
    raise DataQualityError(f"P4 view lacks exact semantic role {role}")


def multivariate_series(
    view: dict[str, Any], feature: str, *, as_of_time: datetime | None = None,
    horizon: str = "1D",
) -> tuple[tuple[str, ...], np.ndarray]:
    rows = merge_horizon_rows(feature_rows(view, as_of_time=as_of_time), horizon=horizon)
    timestamps = sorted({row["decision_time"] for row in rows})
    entities = tuple(sorted({row["underlying"] for row in rows}))
    mapping = {(row["decision_time"], row["underlying"]): row["features"].get(feature) for row in rows}
    matrix = np.asarray([[mapping.get((time, entity), np.nan) for entity in entities] for time in timestamps], dtype=float)
    matrix = matrix[np.all(np.isfinite(matrix), axis=1)]
    if matrix.shape[0] < 8 or matrix.shape[1] < 2:
        raise DataQualityError("multivariate view requires eight complete rows and two entities")
    return entities, matrix


def simple_return_series(view: dict[str, Any], *, as_of_time: datetime | None = None) -> tuple[str, dict[str, np.ndarray]]:
    for feature in ("return_1d", "return"):
        series = series_by_underlying(view, feature, as_of_time=as_of_time)
        if series:
            return feature, series
    log_series = series_by_underlying(view, "log_return", as_of_time=as_of_time)
    if log_series:
        return "log_return", {key: np.expm1(values) for key, values in log_series.items()}
    raise DataQualityError("P4 view contains no raw return series; use trained/OOF model evidence")


def simple_return_matrix(view: dict[str, Any], *, as_of_time: datetime | None = None) -> tuple[str, tuple[str, ...], np.ndarray]:
    rows = feature_rows(view, as_of_time=as_of_time)
    available_names = {
        str(name)
        for row in rows
        for name, value in row.get("features", {}).items()
        if value is not None
    }
    for feature in ("return_1d", "return"):
        if feature not in available_names:
            continue
        entities, matrix = multivariate_series(view, feature, as_of_time=as_of_time)
        return feature, entities, matrix
    if "log_return" in available_names:
        entities, matrix = multivariate_series(view, "log_return", as_of_time=as_of_time)
        return "log_return", entities, np.expm1(matrix)
    raise CapabilityUnavailableError(
        "P4 view contains no raw return series; regime fallback must use an explicit aggregate capability"
    )

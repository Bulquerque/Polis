from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np

from quant_pipeline.common.hashing import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .errors import P4S7Error
from .records import HorizonFeatureRecord, TransformPolicyRecord


_STATELESS = {"identity", "signed_log1p"}


def _fit_parameters(
    values: np.ndarray, policy: TransformPolicyRecord
) -> tuple[dict[str, float], str]:
    if policy.transform_type in _STATELESS:
        return {}, "VALIDATED"
    if policy.transform_type == "standard_zscore":
        center = float(np.mean(values))
        scale = float(np.std(values, ddof=0))
        quality = "VALIDATED" if scale > policy.epsilon else "DEGENERATE_SCALE"
        return {"center": center, "scale": scale if scale > policy.epsilon else 1.0}, quality
    low = float(np.quantile(values, policy.lower_quantile))
    high = float(np.quantile(values, policy.upper_quantile))
    fitted = np.clip(values, low, high) if policy.transform_type.startswith("winsorized") else values
    center = float(np.median(fitted))
    q1, q3 = np.quantile(fitted, [0.25, 0.75])
    scale = float(q3 - q1)
    quality = "VALIDATED" if scale > policy.epsilon else "DEGENERATE_SCALE"
    parameters = {"center": center, "scale": scale if scale > policy.epsilon else 1.0}
    if policy.transform_type.startswith("winsorized"):
        parameters.update({"lower": low, "upper": high})
    return parameters, quality


def _apply_transform(
    value: float, policy: TransformPolicyRecord, parameters: dict[str, float]
) -> float:
    if policy.transform_type == "identity":
        return value
    if policy.transform_type == "signed_log1p":
        return math.copysign(math.log1p(abs(value)), value)
    candidate = value
    if policy.transform_type == "winsorized_robust_zscore":
        candidate = float(np.clip(candidate, parameters["lower"], parameters["upper"]))
    return (candidate - parameters["center"]) / parameters["scale"]


def _training_records(
    records: list[HorizonFeatureRecord],
    current_time: datetime,
    policy: TransformPolicyRecord,
) -> list[HorizonFeatureRecord]:
    past = [record for record in records if record.decision_time < current_time]
    if policy.window_type == "rolling":
        times = sorted({record.decision_time for record in past})
        keep = set(times[-int(policy.lookback_timestamps or 1) :])
        past = [record for record in past if record.decision_time in keep]
    return [record for record in past if record.feature_value is not None]


def _prepare_inputs(
    feature_artifact: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> tuple[
    dict[tuple[str, str], list[HorizonFeatureRecord]],
    dict[tuple[str, str], TransformPolicyRecord],
]:
    policies = [TransformPolicyRecord.model_validate(record) for record in policy_artifact.records]
    policy_map = {(policy.feature_id, policy.horizon_group): policy for policy in policies}
    groups: dict[tuple[str, str], list[HorizonFeatureRecord]] = defaultdict(list)
    for raw_record in feature_artifact.records:
        record = HorizonFeatureRecord.model_validate(raw_record)
        if record.decision_time > context.as_of_time:
            raise P4S7Error("P4_S7_M01_TEMPORAL_VIOLATION", record.feature_id)
        groups[(record.feature_id, record.horizon_group)].append(record)
    missing = sorted(set(groups) - set(policy_map))
    if missing:
        raise P4S7Error("P4_S7_M01_INPUT_INVALID", f"missing transform policies: {missing}")
    return groups, policy_map


def _stateless_state(
    policy: TransformPolicyRecord, first_time: datetime
) -> tuple[dict[str, Any], dict[str, Any]]:
    state_id = f"stateless:{policy.feature_id}:{policy.horizon_group}:{policy.transform_type}"
    active = {"fit_state_id": state_id, "parameters": {}, "quality_state": "VALIDATED"}
    record = {
        "fit_state_id": state_id,
        "feature_id": policy.feature_id,
        "horizon_group": policy.horizon_group,
        "transform_type": policy.transform_type,
        "fit_start": None,
        "fit_end": None,
        "apply_start": first_time.isoformat(),
        "parameters": {},
        "training_record_count": 0,
        "input_hash": canonical_sha256([]),
        "quality_state": "VALIDATED",
    }
    return active, record


def _fit_state(
    key: tuple[str, str],
    records: list[HorizonFeatureRecord],
    current_time: datetime,
    policy: TransformPolicyRecord,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    training = _training_records(records, current_time, policy)
    if len(training) < policy.min_observations:
        return None
    values = np.asarray([record.feature_value for record in training], dtype=float)
    parameters, quality = _fit_parameters(values, policy)
    fit_end = max(record.decision_time for record in training)
    state_id = "fit:" + canonical_sha256(
        {"feature": key, "fit_end": fit_end.isoformat(), "parameters": parameters}
    )[:20]
    active = {"fit_state_id": state_id, "parameters": parameters, "quality_state": quality}
    state_record = {
        "fit_state_id": state_id,
        "feature_id": policy.feature_id,
        "horizon_group": policy.horizon_group,
        "transform_type": policy.transform_type,
        "fit_start": min(record.decision_time for record in training).isoformat(),
        "fit_end": fit_end.isoformat(),
        "apply_start": current_time.isoformat(),
        "parameters": parameters,
        "training_record_count": len(training),
        "input_hash": canonical_sha256(
            [record.model_dump(mode="json") for record in training]
        ),
        "quality_state": quality,
    }
    return active, state_record


def _transform_record(
    record: HorizonFeatureRecord,
    policy: TransformPolicyRecord,
    active_state: dict[str, Any] | None,
) -> dict[str, Any]:
    transformed: float | None = None
    status = record.missingness_state if record.feature_value is None else "OBSERVED"
    fit_state_id = active_state["fit_state_id"] if active_state else None
    if record.feature_value is not None and active_state is not None:
        transformed = _apply_transform(record.feature_value, policy, active_state["parameters"])
    elif record.feature_value is not None:
        status = "NOT_ENOUGH_HISTORY"
    return {
        **record.model_dump(mode="json", exclude={"feature_value"}),
        "raw_value": record.feature_value,
        "transformed_value": transformed,
        "fit_state_id": fit_state_id,
        "transform_status": status,
    }


def _process_group(
    key: tuple[str, str],
    group_records: list[HorizonFeatureRecord],
    policy: TransformPolicyRecord,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = sorted(group_records, key=lambda item: (item.decision_time, item.entity_id))
    times = sorted({record.decision_time for record in records})
    output: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    active_state: dict[str, Any] | None = None
    last_refit_index = -policy.refit_every_n_timestamps
    if policy.transform_type in _STATELESS:
        active_state, state_record = _stateless_state(policy, times[0])
        states.append(state_record)
    for time_index, current_time in enumerate(times):
        due = active_state is None or time_index - last_refit_index >= policy.refit_every_n_timestamps
        if policy.transform_type not in _STATELESS and due:
            fitted = _fit_state(key, records, current_time, policy)
            if fitted is not None:
                active_state, state_record = fitted
                states.append(state_record)
                last_refit_index = time_index
        current_records = [record for record in records if record.decision_time == current_time]
        output.extend(_transform_record(record, policy, active_state) for record in current_records)
    return output, states


def _build_outputs(
    output_records: list[dict[str, Any]],
    state_records: list[dict[str, Any]],
    feature_artifact: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    lineage = canonical_sha256(
        [feature_artifact.lineage_id, policy_artifact.lineage_id, "P4.S7.M01"]
    )
    panel = build_artifact(
        artifact_name="causally_transformed_feature_panel",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M01",
        context=context,
        grain=("decision_time", "entity_id", "feature_id", "horizon_group"),
        records=output_records,
        lineage_id=lineage,
        metadata={"source_artifacts": [feature_artifact.artifact_id, policy_artifact.artifact_id]},
    )
    manifest = build_artifact(
        artifact_name="causal_transform_fit_state_manifest",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M01",
        context=context,
        grain=("fit_state_id",),
        records=state_records,
        lineage_id=lineage,
        metadata={"transformed_panel_id": panel.artifact_id},
    )
    return {panel.artifact_name: panel, manifest.artifact_name: manifest}


def build_causal_transforms(
    feature_artifact: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    groups, policy_map = _prepare_inputs(feature_artifact, policy_artifact, context)
    output_records: list[dict[str, Any]] = []
    state_records: list[dict[str, Any]] = []
    for key in sorted(groups):
        transformed, states = _process_group(key, groups[key], policy_map[key])
        output_records.extend(transformed)
        state_records.extend(states)
    return _build_outputs(
        output_records, state_records, feature_artifact, policy_artifact, context
    )

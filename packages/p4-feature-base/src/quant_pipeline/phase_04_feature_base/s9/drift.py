from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .gates import build_gate_records
from .records import DriftPolicy, S9Policy


def _severity(value: float, warn: float, block: float) -> str:
    if value >= block:
        return "BLOCK"
    if value >= warn:
        return "WARN"
    return "PASS"


def _normalized_wasserstein(reference: np.ndarray, current: np.ndarray) -> float:
    scale = float(np.subtract(*np.percentile(reference, [75, 25])))
    if not isfinite(scale) or scale <= 1e-12:
        scale = float(np.std(reference))
    if not isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    scale = max(scale, 1e-4)
    return float(wasserstein_distance(reference, current) / scale)


def _window_records(
    matrix: ArtifactEnvelope, policy: DriftPolicy
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timestamps = sorted({str(item["decision_time"]) for item in matrix.records})
    needed = policy.reference_timestamps + policy.current_timestamps
    selected = timestamps[-needed:] if len(timestamps) >= needed else timestamps
    current_times = set(selected[-policy.current_timestamps :])
    reference_times = set(selected[: -policy.current_timestamps])
    reference = [item for item in matrix.records if str(item["decision_time"]) in reference_times]
    current = [item for item in matrix.records if str(item["decision_time"]) in current_times]
    return reference, current


def _values_for_feature(rows: list[dict[str, Any]], horizon: str, feature_id: str) -> tuple[list[dict[str, Any]], np.ndarray]:
    group = [row for row in rows if str(row["horizon_group"]) == horizon]
    values = np.asarray(
        [row.get("values", {}).get(feature_id) for row in group if row.get("values", {}).get(feature_id) is not None],
        dtype=float,
    )
    return group, values


def _distribution_metrics(reference: np.ndarray, current: np.ndarray, policy: DriftPolicy) -> tuple[float | None, float | None, float | None, str]:
    if len(reference) < policy.min_samples or len(current) < policy.min_samples:
        return None, None, None, "INSUFFICIENT_DATA"
    result = ks_2samp(reference, current, alternative="two-sided", method="auto")
    ks_stat = float(result.statistic)
    ks_pvalue = float(result.pvalue)
    distance = _normalized_wasserstein(reference, current)
    if ks_pvalue > policy.ks_significance_alpha:
        severity = "PASS"
    else:
        severity = max(
            _severity(ks_stat, policy.ks_warn, policy.ks_block),
            _severity(
                distance,
                policy.normalized_wasserstein_warn,
                policy.normalized_wasserstein_block,
            ),
            key={"PASS": 0, "WARN": 1, "BLOCK": 2}.get,
        )
    return ks_stat, ks_pvalue, distance, severity


def _feature_drift_record(
    key: str,
    descriptor: dict[str, Any],
    reference: list[dict[str, Any]],
    current: list[dict[str, Any]],
    policy: DriftPolicy,
) -> dict[str, Any]:
    feature_id = str(descriptor["feature_id"])
    horizon = str(descriptor["horizon_group"])
    ref_group, ref_values = _values_for_feature(reference, horizon, feature_id)
    cur_group, cur_values = _values_for_feature(current, horizon, feature_id)
    ref_missing = 1.0 - (len(ref_values) / max(len(ref_group), 1))
    cur_missing = 1.0 - (len(cur_values) / max(len(cur_group), 1))
    missing_delta = abs(cur_missing - ref_missing)
    if len(ref_values) < policy.min_samples or len(cur_values) < policy.min_samples:
        missing_severity = "INSUFFICIENT_DATA"
    else:
        missing_severity = _severity(
            missing_delta, policy.missingness_delta_warn, policy.missingness_delta_block
        )
    ks_stat, ks_pvalue, distance, distribution_severity = _distribution_metrics(
        ref_values, cur_values, policy
    )
    overall = max(
        missing_severity,
        distribution_severity,
        key={"INSUFFICIENT_DATA": -1, "PASS": 0, "WARN": 1, "BLOCK": 2}.get,
    )
    return {
        "drift_id": f"feature:{key}", "scope_type": "FEATURE", "scope_id": feature_id,
        "family_id": descriptor.get("family_id"), "horizon_group": horizon,
        "drift_type": "DISTRIBUTION_AND_MISSINGNESS", "reference_count": len(ref_values),
        "current_count": len(cur_values), "ks_statistic": ks_stat, "ks_pvalue": ks_pvalue,
        "normalized_wasserstein": distance, "reference_missingness": ref_missing,
        "current_missingness": cur_missing, "missingness_delta": missing_delta, "severity": overall,
    }


def _feature_drift(matrix: ArtifactEnvelope, policy: DriftPolicy) -> list[dict[str, Any]]:
    reference, current = _window_records(matrix, policy)
    catalog = matrix.metadata.get("feature_catalog", {})
    return [
        _feature_drift_record(key, descriptor, reference, current, policy)
        for key, descriptor in sorted(catalog.items())
    ]


def _loading_drift(states: ArtifactEnvelope, policy: DriftPolicy) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for state in states.records:
        key = (
            str(state["family_id"]),
            str(state["horizon_group"]),
            str(state["representation_type"]),
        )
        grouped[key].append(state)
    records: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: str(item["fit_end"]))
        if len(ordered) < 2:
            continue
        previous = np.asarray(ordered[-2]["components"], dtype=float)
        current = np.asarray(ordered[-1]["components"], dtype=float)
        if previous.ndim != 2 or current.ndim != 2 or previous.shape[1] != current.shape[1]:
            drift = 1.0
        else:
            previous_basis = np.linalg.qr(previous.T)[0]
            current_basis = np.linalg.qr(current.T)[0]
            similarities = np.linalg.svd(previous_basis.T @ current_basis, compute_uv=False)
            drift = 1.0 - float(np.mean(np.clip(similarities, 0.0, 1.0)))
        records.append(
            {
                "drift_id": "loading:" + "|".join(key),
                "scope_type": "REPRESENTATION",
                "scope_id": "|".join(key),
                "family_id": key[0],
                "horizon_group": key[1],
                "drift_type": "PCA_LOADING",
                "reference_count": previous.size,
                "current_count": current.size,
                "loading_drift": drift,
                "severity": _severity(
                    drift,
                    policy.loading_drift_warn,
                    policy.loading_drift_block,
                ),
            }
        )
    return records


def _reconstruction_drift(report: ArtifactEnvelope, policy: DriftPolicy) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in report.records:
        key = (
            str(record["family_id"]),
            str(record["horizon_group"]),
            str(record["representation_type"]),
        )
        grouped[key].append(record)
    records: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: str(item["fold_id"]))
        if len(ordered) < 2:
            continue
        previous = float(ordered[-2]["reconstruction_rmse"])
        current = float(ordered[-1]["reconstruction_rmse"])
        delta = max(
            0.0,
            (current - previous) / max(abs(previous), policy.reconstruction_error_floor),
        )
        records.append(
            {
                "drift_id": "reconstruction:" + "|".join(key),
                "scope_type": "REPRESENTATION",
                "scope_id": "|".join(key),
                "family_id": key[0],
                "horizon_group": key[1],
                "drift_type": "RECONSTRUCTION_ERROR",
                "reference_count": 1,
                "current_count": 1,
                "reference_rmse": previous,
                "current_rmse": current,
                "reconstruction_delta": delta,
                "severity": _severity(
                    delta,
                    policy.reconstruction_delta_warn,
                    policy.reconstruction_delta_block,
                ),
            }
        )
    return records




def build_drift_outputs(
    inputs: dict[str, ArtifactEnvelope], policy: S9Policy, context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    drift_records = [
        *_feature_drift(inputs["underlying_feature_matrix_selected"], policy.drift),
        *_loading_drift(inputs["pca_fit_state_manifest"], policy.drift),
        *_reconstruction_drift(inputs["representation_quality_report"], policy.drift),
    ]
    gate_records, final_decision, coverage_summary = build_gate_records(
        drift_records, inputs["underlying_feature_matrix_selected"], policy
    )
    lineage = canonical_sha256(
        {
            "matrix": inputs["underlying_feature_matrix_selected"].artifact_id,
            "pca": inputs["pca_fit_state_manifest"].artifact_id,
            "quality": inputs["representation_quality_report"].artifact_id,
        }
    )
    blocked = final_decision == "BLOCK_HANDOFF"
    degraded = final_decision in {"PASS_WITH_DEGRADATION", "PARTIAL_HANDOFF"}
    return {
        "drift_safety_report": build_artifact(
            artifact_name="drift_safety_report",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M02",
            context=context,
            grain=("drift_id",),
            records=drift_records,
            lineage_id=lineage,
            metadata={
                "concept_drift_supervised": False,
                "reference_mode": "trailing_windows",
                "family_coverage": coverage_summary,
            },
            execution_status="BLOCKED" if blocked else ("DEGRADED" if degraded else "PRODUCED"),
            quality_status="BLOCKED" if blocked else ("DEGRADED" if degraded else "VALIDATED"),
        ),
        "p4_quality_gate_decision": build_artifact(
            artifact_name="p4_quality_gate_decision",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M02",
            context=context,
            grain=("gate_scope", "scope_id"),
            records=gate_records,
            lineage_id=lineage,
            metadata={"final_decision": final_decision, "family_coverage": coverage_summary},
            execution_status="BLOCKED" if blocked else ("DEGRADED" if degraded else "PRODUCED"),
            quality_status="BLOCKED" if blocked else ("DEGRADED" if degraded else "VALIDATED"),
        ),
    }

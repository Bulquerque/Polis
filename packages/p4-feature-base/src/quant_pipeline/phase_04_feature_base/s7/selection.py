from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from quant_pipeline.common.hashing import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .errors import P4S7Error
from .records import StructuralSelectionPolicy


TIER_SCORE = {"FOUNDATIONAL": 3, "CORE": 3, "EXTENSION": 2, "EXPERIMENTAL": 1}


def _feature_metrics(
    matrix: ArtifactEnvelope,
) -> dict[tuple[str, str], dict[str, float | int]]:
    by_horizon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in matrix.records:
        by_horizon[record["horizon_group"]].append(record)
    metrics: dict[tuple[str, str], dict[str, float | int]] = {}
    for horizon, records in by_horizon.items():
        ordered = sorted(records, key=lambda item: (str(item["entity_id"]), str(item["decision_time"])))
        features = sorted({feature for record in ordered for feature in record["values"]})
        entities = sorted({str(record["entity_id"]) for record in ordered})
        for feature in features:
            eligible_values: list[float | None] = []
            warmup_count = 0
            for entity_id in entities:
                entity_rows = [row for row in ordered if str(row["entity_id"]) == entity_id]
                first_observed = next(
                    (index for index, row in enumerate(entity_rows) if row["values"].get(feature) is not None),
                    None,
                )
                if first_observed is None:
                    warmup_count += len(entity_rows)
                    continue
                warmup_count += first_observed
                eligible_values.extend(row["values"].get(feature) for row in entity_rows[first_observed:])
            observed = np.asarray(
                [value for value in eligible_values if value is not None], dtype=float
            )
            total = len(eligible_values)
            coverage = len(observed) / total if total else 0.0
            metrics[(horizon, feature)] = {
                "observed_count": len(observed),
                "total_count": total,
                "coverage": coverage,
                "missingness": 1.0 - coverage,
                "variance": float(np.var(observed, ddof=0)) if len(observed) else float("nan"),
                "warmup_count": warmup_count,
            }
    return metrics


def _representative(
    members: list[str],
    horizon: str,
    metrics: dict[tuple[str, str], dict[str, float | int]],
    catalog: dict[str, dict[str, Any]],
    prefer_primary: bool,
) -> str:
    def score(feature: str) -> tuple[float, float, float, float, str]:
        meta = catalog[f"{horizon}|{feature}"]
        primary = 1.0 if prefer_primary and meta["is_primary_parameterization"] else 0.0
        tier = float(TIER_SCORE.get(meta["implementation_tier"], 0))
        coverage = float(metrics[(horizon, feature)]["coverage"])
        cost = -float(meta["compute_cost"])
        return primary, tier, coverage, cost, feature

    return max(members, key=score)


def _cluster_maps(
    clusters: dict[str, dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    metrics: dict[tuple[str, str], dict[str, float | int]],
    prefer_primary: bool,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    cluster_by_feature: dict[tuple[str, str], str] = {}
    representatives: dict[tuple[str, str], str] = {}
    for cluster_id, cluster in sorted(clusters.items()):
        horizon = str(cluster["horizon_group"])
        members = [str(feature) for feature in cluster["members"]]
        valid = [feature for feature in members if f"{horizon}|{feature}" in catalog]
        if len(valid) < 2:
            continue
        representatives[(horizon, cluster_id)] = _representative(
            valid, horizon, metrics, catalog, prefer_primary
        )
        cluster_by_feature.update({(horizon, feature): cluster_id for feature in valid})
    return cluster_by_feature, representatives


def _decision_record(
    horizon: str,
    feature: str,
    item: dict[str, float | int],
    catalog: dict[str, dict[str, Any]],
    policy: StructuralSelectionPolicy,
    cluster_id: str | None,
    representative: str | None,
) -> dict[str, Any]:
    variance = float(item["variance"])
    decision, reasons = "KEEP", ["STRUCTURAL_QUALITY_PASS"]
    if float(item["coverage"]) < policy.min_coverage or float(item["missingness"]) > policy.max_missingness:
        decision, reasons = "DROP_LOW_COVERAGE", ["COVERAGE_BELOW_POLICY"]
    elif not np.isfinite(variance) or variance < policy.min_variance:
        decision, reasons = "DROP_LOW_VARIANCE", ["VARIANCE_BELOW_POLICY"]
    elif not catalog.get(f"{horizon}|{feature}", {}).get("lineage_id"):
        decision, reasons = "DROP_INCOMPLETE_LINEAGE", ["FEATURE_LINEAGE_MISSING"]
    elif representative and feature != representative:
        decision, reasons = "DROP_DUPLICATE_PARAMETERIZATION", [
            "REDUNDANCY_CLUSTER_NON_REPRESENTATIVE"
        ]
    return {
        "horizon_group": horizon,
        "feature_id": feature,
        "decision": decision,
        "reason_codes": reasons,
        "coverage": float(item["coverage"]),
        "missingness": float(item["missingness"]),
        "variance": variance if np.isfinite(variance) else None,
        "observed_count": int(item["observed_count"]),
        "total_count": int(item["total_count"]),
        "redundancy_cluster_id": cluster_id,
        "representative_feature_id": representative,
    }


def _build_selection_report(
    metrics: dict[tuple[str, str], dict[str, float | int]],
    catalog: dict[str, dict[str, Any]],
    policy: StructuralSelectionPolicy,
    cluster_by_feature: dict[tuple[str, str], str],
    representatives: dict[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    report: list[dict[str, Any]] = []
    selected: dict[str, set[str]] = defaultdict(set)
    for horizon, feature in sorted(metrics):
        cluster_id = cluster_by_feature.get((horizon, feature))
        representative = representatives.get((horizon, cluster_id)) if cluster_id else None
        record = _decision_record(
            horizon,
            feature,
            metrics[(horizon, feature)],
            catalog,
            policy,
            cluster_id,
            representative,
        )
        report.append(record)
        if record["decision"] == "KEEP":
            selected[horizon].add(feature)
    return report, selected


def _filter_record(record: dict[str, Any], keep: set[str]) -> dict[str, Any]:
    filtered = dict(record)
    for key in (
        "values",
        "raw_values",
        "transformed_values",
        "normalized_values",
        "neutralized_values",
        "missingness_mask",
        "feature_state_ids",
    ):
        filtered[key] = {name: value for name, value in record[key].items() if name in keep}
    return filtered


def _selected_matrix(
    matrix: ArtifactEnvelope,
    selected_by_horizon: dict[str, set[str]],
    catalog: dict[str, dict[str, Any]],
    lineage: str,
    context: ExecutionContext,
) -> ArtifactEnvelope:
    records = [
        _filter_record(record, selected_by_horizon[record["horizon_group"]])
        for record in matrix.records
    ]
    selected_catalog = {
        key: value
        for key, value in catalog.items()
        if value["feature_id"] in selected_by_horizon[value["horizon_group"]]
    }
    return build_artifact(
        artifact_name="underlying_feature_matrix_selected",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M04",
        context=context,
        grain=("decision_time", "entity_id", "horizon_group"),
        records=records,
        lineage_id=lineage,
        metadata={"feature_catalog": selected_catalog, "source_matrix_id": matrix.artifact_id},
    )


def _state_ids(
    states: ArtifactEnvelope, id_field: str
) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = defaultdict(list)
    for state in states.records:
        result[(state["horizon_group"], state["feature_id"])].append(state[id_field])
    return result


def _transform_manifest_records(
    report: list[dict[str, Any]],
    metrics: dict[tuple[str, str], dict[str, float | int]],
    causal_states: ArtifactEnvelope,
    normalization_states: ArtifactEnvelope,
    policy_hash: str,
    lineage: str,
) -> list[dict[str, Any]]:
    causal_ids = _state_ids(causal_states, "fit_state_id")
    norm_ids = _state_ids(normalization_states, "state_id")
    report_map = {(item["horizon_group"], item["feature_id"]): item for item in report}
    records = []
    for horizon, feature in sorted(metrics):
        records.append(
            {
                "horizon_group": horizon,
                "feature_id": feature,
                "selection_decision": report_map[(horizon, feature)]["decision"],
                "causal_fit_state_ids": sorted(causal_ids[(horizon, feature)]),
                "normalization_state_ids": sorted(norm_ids[(horizon, feature)]),
                "selection_policy_hash": policy_hash,
                "lineage_id": canonical_sha256([lineage, horizon, feature]),
            }
        )
    return records


def _build_outputs(
    matrix: ArtifactEnvelope,
    report: list[dict[str, Any]],
    selected_by_horizon: dict[str, set[str]],
    metrics: dict[tuple[str, str], dict[str, float | int]],
    causal_states: ArtifactEnvelope,
    normalization_states: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    lineage: str,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    selected = _selected_matrix(
        matrix, selected_by_horizon, matrix.metadata["feature_catalog"], lineage, context
    )
    selection_report = build_artifact(
        artifact_name="feature_selection_report",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M04",
        context=context,
        grain=("horizon_group", "feature_id"),
        records=report,
        lineage_id=lineage,
        metadata={"selected_feature_count": sum(map(len, selected_by_horizon.values()))},
    )
    transform_records = _transform_manifest_records(
        report,
        metrics,
        causal_states,
        normalization_states,
        canonical_sha256(policy_artifact.records[0]),
        lineage,
    )
    manifest = build_artifact(
        artifact_name="feature_transform_state_manifest",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M04",
        context=context,
        grain=("horizon_group", "feature_id"),
        records=transform_records,
        lineage_id=lineage,
        metadata={
            "causal_manifest_id": causal_states.artifact_id,
            "normalization_manifest_id": normalization_states.artifact_id,
            "selection_report_id": selection_report.artifact_id,
        },
    )
    return {
        selected.artifact_name: selected,
        selection_report.artifact_name: selection_report,
        manifest.artifact_name: manifest,
    }


def select_structural_features(
    matrix: ArtifactEnvelope,
    redundancy: ArtifactEnvelope,
    causal_states: ArtifactEnvelope,
    normalization_states: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    policy = StructuralSelectionPolicy.model_validate(policy_artifact.records[0])
    catalog = matrix.metadata["feature_catalog"]
    metrics = _feature_metrics(matrix)
    cluster_map, representatives = _cluster_maps(
        redundancy.metadata.get("clusters", {}),
        catalog,
        metrics,
        policy.prefer_primary_parameterization,
    )
    report, selected_by_horizon = _build_selection_report(
        metrics, catalog, policy, cluster_map, representatives
    )
    if sum(map(len, selected_by_horizon.values())) < policy.min_selected_features:
        raise P4S7Error("P4_S7_M04_OUTPUT_INVALID", "selected feature count below policy")
    lineage = canonical_sha256(
        [
            matrix.lineage_id,
            redundancy.lineage_id,
            causal_states.lineage_id,
            normalization_states.lineage_id,
            policy_artifact.lineage_id,
            "P4.S7.M04",
        ]
    )
    return _build_outputs(
        matrix,
        report,
        selected_by_horizon,
        metrics,
        causal_states,
        normalization_states,
        policy_artifact,
        lineage,
        context,
    )

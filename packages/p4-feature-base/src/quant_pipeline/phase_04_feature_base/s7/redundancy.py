from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.feature_selection import mutual_info_regression

from quant_pipeline.common.hashing import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .records import StructuralSelectionPolicy


class _UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _distance_correlation(x: np.ndarray, y: np.ndarray, maximum: int) -> float | None:
    if len(x) < 3:
        return None
    if len(x) > maximum:
        indices = np.linspace(0, len(x) - 1, maximum, dtype=int)
        x, y = x[indices], y[indices]
    a = np.abs(x[:, None] - x[None, :])
    b = np.abs(y[:, None] - y[None, :])
    a_centered = a - a.mean(0)[None, :] - a.mean(1)[:, None] + a.mean()
    b_centered = b - b.mean(0)[None, :] - b.mean(1)[:, None] + b.mean()
    covariance_sq = float(np.mean(a_centered * b_centered))
    variance_x_sq = float(np.mean(a_centered * a_centered))
    variance_y_sq = float(np.mean(b_centered * b_centered))
    denominator = (variance_x_sq * variance_y_sq) ** 0.5
    if denominator <= 0:
        return None
    return float(max(covariance_sq / denominator, 0.0) ** 0.5)


def _pair_metrics(
    left: list[float | None], right: list[float | None], policy: StructuralSelectionPolicy
) -> dict[str, float | int | None]:
    mask = np.asarray([a is not None and b is not None for a, b in zip(left, right, strict=True)])
    overlap = int(mask.sum())
    observed_left = np.asarray([value is not None for value in left])
    observed_right = np.asarray([value is not None for value in right])
    union = int(np.logical_or(observed_left, observed_right).sum())
    jaccard = overlap / union if union else None
    if overlap < policy.min_pair_overlap:
        return {"overlap_count": overlap, "observed_jaccard": jaccard,
                "pearson": None, "spearman": None, "mutual_information": None,
                "distance_correlation": None}
    x = np.asarray([left[i] for i in range(len(left)) if mask[i]], dtype=float)
    y = np.asarray([right[i] for i in range(len(right)) if mask[i]], dtype=float)
    constant_input = bool(np.isclose(np.std(x), 0.0, atol=1e-12) or np.isclose(np.std(y), 0.0, atol=1e-12))
    pearson = None if constant_input else float(np.corrcoef(x, y)[0, 1])
    spearman = None
    if not constant_input:
        spearman_result = spearmanr(x, y)
        if np.isfinite(spearman_result.statistic):
            spearman = float(spearman_result.statistic)
    if constant_input:
        mi_xy = mi_yx = 0.0
    else:
        neighbors = min(policy.mutual_info_neighbors, max(1, overlap - 1))
        mi_xy = mutual_info_regression(
            x.reshape(-1, 1), y, n_neighbors=neighbors,
            random_state=policy.random_state, n_jobs=1,
        )[0]
        mi_yx = mutual_info_regression(
            y.reshape(-1, 1), x, n_neighbors=neighbors,
            random_state=policy.random_state, n_jobs=1,
        )[0]
    return {
        "overlap_count": overlap, "observed_jaccard": jaccard,
        "pearson": pearson, "spearman": spearman,
        "mutual_information": float((mi_xy + mi_yx) / 2.0),
        "distance_correlation": _distance_correlation(x, y, policy.max_pair_samples),
    }


def _classify(metrics: dict[str, Any], same_perspective: bool, policy: StructuralSelectionPolicy) -> str:
    if metrics["overlap_count"] < policy.min_pair_overlap:
        return "INSUFFICIENT_EVIDENCE"
    pearson = abs(metrics["pearson"]) if metrics["pearson"] is not None else 0.0
    spearman = abs(metrics["spearman"]) if metrics["spearman"] is not None else 0.0
    distance = metrics["distance_correlation"] or 0.0
    if same_perspective and pearson >= policy.duplicate_abs_pearson and spearman >= policy.duplicate_abs_spearman:
        return "PARAMETRIC_DUPLICATE"
    if pearson >= policy.duplicate_abs_pearson and spearman >= policy.duplicate_abs_spearman:
        return "ECONOMICALLY_DISTINCT_CORRELATED"
    if distance >= policy.nonlinear_dependence_threshold and spearman < policy.duplicate_abs_spearman:
        return "NONLINEAR_DEPENDENCE"
    return "COMPLEMENTARY"


def _analyze_horizon(
    horizon: str,
    records: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    policy: StructuralSelectionPolicy,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    ordered = sorted(records, key=lambda item: (item["decision_time"], item["entity_id"]))
    features = sorted({feature for record in ordered for feature in record["values"]})
    values = {
        feature: [record["normalized_values"].get(feature) for record in ordered]
        for feature in features
    }
    union = _UnionFind(features)
    pairs: list[dict[str, Any]] = []
    for left, right in combinations(features, 2):
        metrics = _pair_metrics(values[left], values[right], policy)
        same_perspective = (
            catalog[f"{horizon}|{left}"]["perspective_id"]
            == catalog[f"{horizon}|{right}"]["perspective_id"]
        )
        classification = _classify(metrics, same_perspective, policy)
        if classification == "PARAMETRIC_DUPLICATE":
            union.union(left, right)
        pairs.append({
            "horizon_group": horizon, "feature_id_a": left, "feature_id_b": right,
            **metrics, "classification": classification, "redundancy_cluster_id": None,
        })
    members: dict[str, list[str]] = defaultdict(list)
    for feature in features:
        members[union.find(feature)].append(feature)
    cluster_map: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for group in sorted(members.values()):
        if len(group) < 2:
            continue
        cluster_id = "cluster:" + canonical_sha256([horizon, group])[:16]
        metadata[cluster_id] = {"horizon_group": horizon, "members": group}
        cluster_map.update({feature: cluster_id for feature in group})
    for pair in pairs:
        pair["redundancy_cluster_id"] = cluster_map.get(pair["feature_id_a"])
    return pairs, metadata


def analyze_redundancy(
    matrix_artifact: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> ArtifactEnvelope:
    policy = StructuralSelectionPolicy.model_validate(policy_artifact.records[0])
    catalog = matrix_artifact.metadata["feature_catalog"]
    by_horizon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in matrix_artifact.records:
        by_horizon[record["horizon_group"]].append(record)
    output: list[dict[str, Any]] = []
    cluster_metadata: dict[str, dict[str, Any]] = {}
    for horizon in sorted(by_horizon):
        pairs, metadata = _analyze_horizon(horizon, by_horizon[horizon], catalog, policy)
        output.extend(pairs)
        cluster_metadata.update(metadata)
    lineage = canonical_sha256(
        [matrix_artifact.lineage_id, policy_artifact.lineage_id, "P4.S7.M03"]
    )
    return build_artifact(
        artifact_name="feature_diversity_redundancy_report",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M03",
        context=context,
        grain=("horizon_group", "feature_id_a", "feature_id_b"),
        records=output,
        lineage_id=lineage,
        metadata={"clusters": cluster_metadata, "matrix_id": matrix_artifact.artifact_id},
    )

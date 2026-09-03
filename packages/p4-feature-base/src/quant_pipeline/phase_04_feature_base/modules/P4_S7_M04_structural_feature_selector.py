from __future__ import annotations

from collections.abc import Mapping

from ..s7.artifacts import ArtifactEnvelope, ExecutionContext
from ..s7.selection import select_structural_features
from ..s7.validation import require_artifacts, validate_context


def run_module(inputs: Mapping[str, ArtifactEnvelope], context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    required = (
        "underlying_feature_matrix_interpretable", "feature_diversity_redundancy_report",
        "causal_transform_fit_state_manifest", "normalization_neutralization_fit_state_manifest",
        "structural_selection_policy",
    )
    require_artifacts(inputs, required, "P4.S7.M04")
    for name in required:
        validate_context(inputs[name], context)
    return select_structural_features(*(inputs[name] for name in required), context)

from __future__ import annotations

from collections.abc import Mapping

from ..s7.artifacts import ArtifactEnvelope, ExecutionContext
from ..s7.normalization import build_normalized_matrix
from ..s7.validation import require_artifacts, validate_context


def run_module(inputs: Mapping[str, ArtifactEnvelope], context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    required = ("causally_transformed_feature_panel", "exposure_panel", "normalization_neutralization_policy")
    require_artifacts(inputs, required, "P4.S7.M02")
    for name in required:
        validate_context(inputs[name], context)
    return build_normalized_matrix(inputs[required[0]], inputs[required[1]], inputs[required[2]], context)

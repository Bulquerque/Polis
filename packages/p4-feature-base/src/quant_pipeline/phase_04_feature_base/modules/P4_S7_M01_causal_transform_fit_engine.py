from __future__ import annotations

from collections.abc import Mapping

from ..s7.artifacts import ArtifactEnvelope, ExecutionContext
from ..s7.causal_fit import build_causal_transforms
from ..s7.validation import require_artifacts, validate_context


def run_module(inputs: Mapping[str, ArtifactEnvelope], context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    required = ("horizon_feature_panel", "transform_policy_registry")
    require_artifacts(inputs, required, "P4.S7.M01")
    for name in required:
        validate_context(inputs[name], context)
    return build_causal_transforms(inputs[required[0]], inputs[required[1]], context)

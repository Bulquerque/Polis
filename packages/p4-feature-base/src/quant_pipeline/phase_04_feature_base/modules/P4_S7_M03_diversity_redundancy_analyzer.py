from __future__ import annotations

from collections.abc import Mapping

from ..s7.artifacts import ArtifactEnvelope, ExecutionContext
from ..s7.redundancy import analyze_redundancy
from ..s7.validation import require_artifacts, validate_context


def run_module(inputs: Mapping[str, ArtifactEnvelope], context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    required = ("underlying_feature_matrix_interpretable", "structural_selection_policy")
    require_artifacts(inputs, required, "P4.S7.M03")
    for name in required:
        validate_context(inputs[name], context)
    report = analyze_redundancy(inputs[required[0]], inputs[required[1]], context)
    return {report.artifact_name: report}

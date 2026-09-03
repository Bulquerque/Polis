from __future__ import annotations

from ..s9.artifacts import ArtifactEnvelope, ExecutionContext
from ..s9.lineage import build_lineage_outputs
from ..s9.validation import reject_forbidden, require_artifacts


def run_module(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    require_artifacts(inputs)
    reject_forbidden({name: artifact.model_dump(mode="json") for name, artifact in inputs.items()})
    return build_lineage_outputs(inputs, context)

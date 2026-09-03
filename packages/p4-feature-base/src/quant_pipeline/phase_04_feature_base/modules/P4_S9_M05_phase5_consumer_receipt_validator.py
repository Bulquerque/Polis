from __future__ import annotations

from ..s9.artifacts import ArtifactEnvelope, ExecutionContext
from ..s9.receipt import validate_receipt


def run_module(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    receipt = inputs.get("phase5_consumption_receipt")
    result = validate_receipt(inputs["phase5_feature_handoff_manifest"], receipt, context)
    return {"p4_to_p5_integration_receipt": result}

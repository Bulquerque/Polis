from __future__ import annotations

from ..s9.artifacts import ArtifactEnvelope, ExecutionContext
from ..s9.handoff import build_handoff


def run_module(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    generated = {
        name: inputs[name]
        for name in (
            "feature_lineage_report",
            "drift_safety_report",
            "p4_quality_gate_decision",
            "model_consumer_view_manifest",
        )
    }
    return {"phase5_feature_handoff_manifest": build_handoff(inputs, generated, context)}

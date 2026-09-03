from __future__ import annotations

from ..s9.artifacts import ArtifactEnvelope, ExecutionContext
from ..s9.validation import parse_policy
from ..s9.views import build_consumer_views


def run_module(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    policy = parse_policy(inputs["s9_policy_registry"])
    return build_consumer_views(inputs, policy.consumer_views, inputs["p4_quality_gate_decision"], context)

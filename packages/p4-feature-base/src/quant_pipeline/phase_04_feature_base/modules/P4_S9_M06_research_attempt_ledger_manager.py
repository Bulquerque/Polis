from __future__ import annotations

from ..s9.artifacts import ArtifactEnvelope, ExecutionContext
from ..s9.ledger import build_ledger_outputs
from ..s9.validation import parse_policy


def run_module(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    policy = parse_policy(inputs["s9_policy_registry"])
    return build_ledger_outputs(inputs["research_attempt_event_log"], policy.research_budget, context)

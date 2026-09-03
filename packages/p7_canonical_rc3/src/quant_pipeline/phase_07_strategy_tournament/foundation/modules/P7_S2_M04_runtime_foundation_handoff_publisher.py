"""P7.S2.M04 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s2_comparability.handoff import execute

MODULE_ID = "P7.S2.M04"
_REQUIRED = (
    "eligible_strategy_candidate_panel",
    "eligibility_blocked_candidate_panel",
    "eligibility_decision_panel",
    "candidate_comparison_group_panel",
    "candidate_metric_route_panel",
    "ranking_feedback_context",
)


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    payloads: dict[str, dict[str, JsonValue]] = {}
    for name in _REQUIRED:
        value = inputs.get(name)
        if not isinstance(value, dict):
            raise TypeError(f"M04 requires {name} object")
        payloads[name] = value
    input_hash = content_sha256(dict(inputs))
    outputs = execute(payloads, dict(config))
    response = ModuleResponse(
        module_id=MODULE_ID,
        status="PASS",
        outputs=outputs,
        receipt={
            "input_hash": input_hash,
            "output_hash": content_sha256(outputs),
            "output_artifact_names": sorted(outputs),
        },
    )
    return response.model_dump(mode="json")

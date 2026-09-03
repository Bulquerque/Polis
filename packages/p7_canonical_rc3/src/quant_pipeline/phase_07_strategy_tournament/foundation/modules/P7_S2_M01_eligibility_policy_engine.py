"""P7.S2.M01 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s2_comparability.eligibility import execute

MODULE_ID = "P7.S2.M01"


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    bundle = inputs.get("temporally_safe_candidate_bundle")
    feedback = inputs.get("ranking_feedback_context")
    registry = inputs.get("eligibility_policy_registry")
    if not isinstance(bundle, dict) or not isinstance(feedback, dict) or not isinstance(registry, dict):
        raise TypeError("M01 requires candidate bundle, feedback context and eligibility registry objects")
    input_hash = content_sha256(dict(inputs))
    outputs = execute(bundle, feedback, registry, dict(config))
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

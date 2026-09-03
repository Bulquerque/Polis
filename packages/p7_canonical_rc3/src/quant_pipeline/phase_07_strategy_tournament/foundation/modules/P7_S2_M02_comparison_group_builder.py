"""P7.S2.M02 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s2_comparability.comparison_groups import execute

MODULE_ID = "P7.S2.M02"


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    eligible = inputs.get("eligible_strategy_candidate_panel")
    registry = inputs.get("comparison_group_policy")
    if not isinstance(eligible, dict) or not isinstance(registry, dict):
        raise TypeError("M02 requires eligible panel and comparison policy objects")
    input_hash = content_sha256(dict(inputs))
    outputs = execute(eligible, registry, dict(config))
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

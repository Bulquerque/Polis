"""P7.S2.M03 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s2_comparability.metric_routing import execute

MODULE_ID = "P7.S2.M03"


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    eligible = inputs.get("eligible_strategy_candidate_panel")
    groups = inputs.get("candidate_comparison_group_panel")
    metrics = inputs.get("metric_semantics_registry")
    objectives = inputs.get("objective_family_registry")
    if not all(isinstance(item, dict) for item in (eligible, groups, metrics, objectives)):
        raise TypeError("M03 requires eligible, group, metric and objective registry objects")
    input_hash = content_sha256(dict(inputs))
    outputs = execute(eligible, groups, metrics, objectives, dict(config))
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

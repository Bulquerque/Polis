"""P7.S1.M01 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s1_boundary.handoff_validation import execute

MODULE_ID = "P7.S1.M01"


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    try:
        input_hash = content_sha256(dict(inputs))
    except (TypeError, ValueError):
        input_hash = "UNHASHABLE_INVALID_INPUT"
    manifest = inputs.get("phase7_strategy_handoff_manifest")
    artifacts = inputs.get("declared_p6_artifacts")
    if not isinstance(manifest, dict) or not isinstance(artifacts, list):
        raise TypeError("M01 requires manifest object and declared_p6_artifacts list")
    outputs = execute(manifest, artifacts, config)
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

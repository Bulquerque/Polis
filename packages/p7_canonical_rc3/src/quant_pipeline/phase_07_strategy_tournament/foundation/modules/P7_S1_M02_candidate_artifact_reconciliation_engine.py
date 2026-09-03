"""P7.S1.M02 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s1_boundary.reconciliation import execute

MODULE_ID = "P7.S1.M02"


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    try:
        input_hash = content_sha256(dict(inputs))
    except (TypeError, ValueError):
        input_hash = "UNHASHABLE_INVALID_INPUT"
    index = inputs.get("verified_p6_artifact_index")
    if not isinstance(index, dict):
        raise TypeError("M02 requires verified_p6_artifact_index")
    outputs = execute(index, config)
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

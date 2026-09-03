"""P7.S1.M04 public wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from pydantic import JsonValue

from ..canonical import content_sha256
from ..models import ModuleResponse
from ..s1_boundary.feedback import execute

MODULE_ID = "P7.S1.M04"


def run_module(
    inputs: Mapping[str, JsonValue],
    config: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    try:
        input_hash = content_sha256(dict(inputs))
    except (TypeError, ValueError):
        input_hash = "UNHASHABLE_INVALID_INPUT"
    report = inputs.get("ranking_feedback_report")
    manifest = inputs.get("ranking_feedback_manifest")
    if report is not None and not isinstance(report, dict):
        raise TypeError("ranking_feedback_report must be an object or null")
    if manifest is not None and not isinstance(manifest, dict):
        raise TypeError("ranking_feedback_manifest must be an object or null")
    outputs = execute(report, manifest, config)
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

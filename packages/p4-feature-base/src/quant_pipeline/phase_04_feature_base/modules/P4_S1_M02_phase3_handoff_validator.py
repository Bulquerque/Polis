from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..boundary.phase3 import validate_phase3_handoff
from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import output_schemas, upstream_schema_root

MODULE_ID = "P4.S1.M02"
MODULE_NAME = "phase3_handoff_validator"
REQUIRED_INPUTS = (
    "social_feature_panel",
    "evidence_tag_panel",
    "agent_disagreement_panel",
    "context_memory_feature_panel",
    "hypothesis_registry",
    "phase4_social_handoff_manifest",
)


def execute(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    return validate_phase3_handoff(
        inputs,
        context,
        upstream_schema_root("p3"),
        output_schemas(),
    )


def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    outputs = execute(inputs, context_from_config(config))
    return module_response(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        required_inputs=REQUIRED_INPUTS,
        outputs=outputs,
    )

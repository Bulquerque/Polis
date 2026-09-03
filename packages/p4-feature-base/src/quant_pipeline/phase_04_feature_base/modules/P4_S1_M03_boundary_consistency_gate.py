from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..boundary.consistency import validate_boundary_consistency
from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import output_schemas

MODULE_ID = "P4.S1.M03"
MODULE_NAME = "boundary_consistency_gate"
REQUIRED_INPUTS = ("validated_phase2_bundle", "validated_phase3_bundle")


def execute(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    raw_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return validate_boundary_consistency(
        inputs,
        raw_inputs or {},
        context,
        output_schemas(),
    )


def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    config_mapping = dict(config or {})
    outputs = execute(
        inputs,
        context_from_config(config_mapping),
        config_mapping.get("raw_boundary_inputs", {}),
    )
    return module_response(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        required_inputs=REQUIRED_INPUTS,
        outputs=outputs,
    )

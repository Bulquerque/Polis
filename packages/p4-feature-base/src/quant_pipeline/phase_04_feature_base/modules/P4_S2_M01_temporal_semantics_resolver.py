from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import s1_output_schemas, s2_output_schemas
from ..temporal.resolve import resolve_temporal_semantics

MODULE_ID = "P4.S2.M01"
MODULE_NAME = "temporal_semantics_resolver"
REQUIRED_INPUTS = (
    "validated_p4_boundary_bundle",
    "validated_phase2_bundle",
    "validated_phase3_bundle",
    "phase2_capability_matrix",
    "phase3_capability_matrix",
)


def execute(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    return resolve_temporal_semantics(
        inputs,
        context,
        s1_schemas=s1_output_schemas(),
        s2_schemas=s2_output_schemas(),
    )


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    outputs = execute(inputs, context_from_config(config))
    return module_response(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        required_inputs=REQUIRED_INPUTS,
        outputs=outputs,
        subphase="P4.S2",
    )

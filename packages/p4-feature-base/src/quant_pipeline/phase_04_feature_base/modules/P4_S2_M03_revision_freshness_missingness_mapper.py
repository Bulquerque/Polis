from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import s2_output_schemas
from ..temporal.freshness import map_freshness_and_missingness

MODULE_ID = "P4.S2.M03"
MODULE_NAME = "revision_freshness_missingness_mapper"
REQUIRED_INPUTS = (
    "entity_aligned_observation_bundle",
    "phase2_capability_matrix",
    "phase3_capability_matrix",
)


def execute(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    schemas = s2_output_schemas()
    return map_freshness_and_missingness(
        inputs,
        context,
        input_schema=schemas["entity_aligned_observation_bundle"],
        s2_schemas=schemas,
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

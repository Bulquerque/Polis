from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..boundary.variable_evolution import register_variable_evolution
from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import output_schemas

MODULE_ID = "P4.S1.M04"
MODULE_NAME = "n_plus_1_variable_evolution_intake"
REQUIRED_INPUTS = ("validated_p4_boundary_bundle",)


def execute(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    schemas = output_schemas()
    registry = register_variable_evolution(
        inputs,
        context,
        schemas["observer_change_proposal_registry"],
        schemas["validated_p4_boundary_bundle"],
    )
    return {"observer_change_proposal_registry": registry}


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

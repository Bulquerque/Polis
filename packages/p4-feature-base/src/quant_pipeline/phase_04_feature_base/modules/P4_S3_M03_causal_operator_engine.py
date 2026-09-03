from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..observers.execution import run_causal
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import s2_output_schemas, s3_output_schemas

MODULE_ID = "P4.S3.M03"
MODULE_NAME = "causal_operator_engine"
REQUIRED_INPUTS = ('canonical_observation_panel', 'approved_observer_execution_registry')


def execute(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    return run_causal(inputs, context, schemas={**s2_output_schemas(), **s3_output_schemas()})


def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = context_from_config(config)
    outputs = run_causal(
        inputs, context, schemas={**s2_output_schemas(), **s3_output_schemas()},
        materialize=bool((config or {}).get("materialize_operator_diagnostics", False)),
    )
    return module_response(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        required_inputs=REQUIRED_INPUTS,
        outputs=outputs,
        subphase="P4.S3",
    )

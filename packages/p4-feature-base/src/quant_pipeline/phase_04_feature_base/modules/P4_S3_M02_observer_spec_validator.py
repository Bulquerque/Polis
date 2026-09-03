from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..observers.specification import validate_specs
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import s3_output_schemas

MODULE_ID = "P4.S3.M02"
MODULE_NAME = "observer_spec_validator"
REQUIRED_INPUTS = ('feature_observer_registry', 'foundational_hypothesis_core_registry')


def execute(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    return validate_specs(inputs, context, schemas=s3_output_schemas())


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
        subphase="P4.S3",
    )

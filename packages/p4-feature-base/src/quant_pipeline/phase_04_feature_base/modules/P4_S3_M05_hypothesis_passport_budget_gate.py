from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..observers.budget import apply_budget
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import s3_output_schemas

MODULE_ID = "P4.S3.M05"
MODULE_NAME = "hypothesis_passport_budget_gate"
REQUIRED_INPUTS = (
    'validated_observer_spec_registry',
    'foundational_hypothesis_core_registry',
    'feature_parameter_policy_registry',
    'observer_change_review_registry',
)


def execute(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    return apply_budget(inputs, context, schemas=s3_output_schemas())


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

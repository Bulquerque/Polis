from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..boundary.phase2 import validate_phase2_handoff
from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import output_schemas, upstream_schema_root

MODULE_ID = "P4.S1.M01"
MODULE_NAME = "phase2_handoff_validator"
REQUIRED_INPUTS = (
    "clean_underlying_panel",
    "clean_macro_br_panel",
    "clean_macro_us_panel",
    "clean_benchmark_panel",
    "clean_calendar_panel",
    "clean_corporate_actions_panel",
    "quality_report_phase_2",
    "phase4_handoff_manifest",
)


def execute(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    return validate_phase2_handoff(
        inputs,
        context,
        upstream_schema_root("p2"),
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

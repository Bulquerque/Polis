from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.module_api import context_from_config, module_response
from ..runtime.resources import s2_output_schemas
from ..temporal.canonical_store import build_canonical_store

MODULE_ID = "P4.S2.M04"
MODULE_NAME = "canonical_observation_store_builder"
REQUIRED_INPUTS = ("quality_enriched_observation_bundle",)


def execute(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    schemas = s2_output_schemas()
    return build_canonical_store(
        inputs,
        context,
        input_schema=schemas["quality_enriched_observation_bundle"],
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

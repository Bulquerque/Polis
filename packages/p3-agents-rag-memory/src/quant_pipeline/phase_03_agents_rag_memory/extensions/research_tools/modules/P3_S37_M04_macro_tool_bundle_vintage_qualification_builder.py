from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..families.macro._compat import (
    validate_json,
)
from ..families.macro.qualification import (
    MacroQualificationBuilder,
)
from ..families.macro.qualification_contracts import (
    HandlerBundleManifest,
    OperationModeQualificationPanel,
)

MODULE_ID = "P3.S37.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "macro_tool_bundle_vintage_qualification_builder"
SUBPHASE = "P3.S37"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S37_M04_macro_tool_bundle_vintage_qualification_builder.yaml"
REQUIRED_INPUTS = (
    "macro_observation_handler_bundle",
    "macro_observation_operation_mode_qualification",
    "macro_context_handler_bundle",
    "macro_context_operation_mode_qualification",
)
PRODUCED_OUTPUTS = (
    "macro_tool_handler_bundle",
    "macro_operation_mode_qualification",
    "macro_tool_readiness_report",
)


async def execute(inputs: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    bundles = (
        validate_json(HandlerBundleManifest, inputs["macro_observation_handler_bundle"]),
        validate_json(HandlerBundleManifest, inputs["macro_context_handler_bundle"]),
    )
    panels = (
        validate_json(
            OperationModeQualificationPanel,
            inputs["macro_observation_operation_mode_qualification"],
        ),
        validate_json(OperationModeQualificationPanel, inputs["macro_context_operation_mode_qualification"]),
    )
    snapshot_id = panels[0].snapshot_id
    bundle, panel, report = MacroQualificationBuilder().consolidate(
        snapshot_id=snapshot_id,
        bundles=bundles,
        panels=panels,
    )
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "subphase": SUBPHASE,
        "outputs": {
            "macro_tool_handler_bundle": bundle.model_dump(mode="json"),
            "macro_operation_mode_qualification": panel.model_dump(mode="json"),
            "macro_tool_readiness_report": report.model_dump(mode="json"),
        },
    }

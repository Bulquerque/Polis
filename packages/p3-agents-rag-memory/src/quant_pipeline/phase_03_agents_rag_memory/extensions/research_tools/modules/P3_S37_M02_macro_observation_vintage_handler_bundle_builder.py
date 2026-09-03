from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..families.macro._compat import (
    validate_json,
)
from ..families.macro.catalog_contracts import (
    MacroSeriesReleaseCatalog,
    MacroViewReadinessReport,
)
from ..families.macro.qualification import (
    MacroQualificationBuilder,
)

MODULE_ID = "P3.S37.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "macro_observation_vintage_handler_bundle_builder"
SUBPHASE = "P3.S37"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S37_M02_macro_observation_vintage_handler_bundle_builder.yaml"
REQUIRED_INPUTS = ("macro_series_release_catalog", "macro_view_readiness_report")
PRODUCED_OUTPUTS = (
    "macro_observation_handler_bundle",
    "macro_observation_operation_mode_qualification",
)


async def execute(inputs: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    catalog = validate_json(MacroSeriesReleaseCatalog, inputs["macro_series_release_catalog"])
    readiness = validate_json(MacroViewReadinessReport, inputs["macro_view_readiness_report"])
    if catalog.snapshot_id != readiness.snapshot_id:
        raise ValueError("macro catalog/readiness snapshot_id mismatch")
    if len(catalog.records) != readiness.series_count:
        raise ValueError("macro readiness series_count does not match catalog")
    vintage_count = sum(1 for item in catalog.records if item.vintage_support)
    if vintage_count != readiness.vintage_capable_series_count:
        raise ValueError("macro readiness vintage count does not match catalog")
    bundle, panel = MacroQualificationBuilder().observation_bundle(
        snapshot_id=readiness.snapshot_id,
        readiness=readiness,
    )
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "subphase": SUBPHASE,
        "outputs": {
            "macro_observation_handler_bundle": bundle.model_dump(mode="json"),
            "macro_observation_operation_mode_qualification": panel.model_dump(mode="json"),
        },
    }

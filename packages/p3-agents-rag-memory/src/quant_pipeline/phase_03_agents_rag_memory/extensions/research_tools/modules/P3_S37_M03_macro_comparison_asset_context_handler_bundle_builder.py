from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..families.macro._compat import (
    validate_json,
)
from ..families.macro.catalog_contracts import (
    AssetMacroContextRegistrySnapshot,
    MacroSeriesReleaseCatalog,
    MacroViewReadinessReport,
)
from ..families.macro.qualification import (
    MacroQualificationBuilder,
)

MODULE_ID = "P3.S37.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "macro_comparison_asset_context_handler_bundle_builder"
SUBPHASE = "P3.S37"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S37_M03_macro_comparison_asset_context_handler_bundle_builder.yaml"
REQUIRED_INPUTS = (
    "macro_series_release_catalog",
    "macro_view_readiness_report",
    "macro_asset_context_config_snapshot",
)
PRODUCED_OUTPUTS = (
    "macro_context_handler_bundle",
    "macro_context_operation_mode_qualification",
)


async def execute(inputs: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    catalog = validate_json(MacroSeriesReleaseCatalog, inputs["macro_series_release_catalog"])
    readiness = validate_json(MacroViewReadinessReport, inputs["macro_view_readiness_report"])
    contexts = validate_json(
        AssetMacroContextRegistrySnapshot,
        inputs["macro_asset_context_config_snapshot"],
    )
    snapshot_ids = {catalog.snapshot_id, readiness.snapshot_id, contexts.snapshot_id}
    if len(snapshot_ids) != 1:
        raise ValueError("macro catalog/readiness/context snapshot_id mismatch")
    known_series = {item.series_id for item in catalog.records}
    unknown_series = sorted(
        {
            series_id
            for context_record in contexts.records
            for series_id in context_record.series_ids
            if series_id not in known_series
        }
    )
    if unknown_series:
        raise ValueError(f"macro asset contexts reference unknown series: {unknown_series}")
    bundle, panel = MacroQualificationBuilder().context_bundle(
        snapshot_id=readiness.snapshot_id,
        readiness=readiness,
    )
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "subphase": SUBPHASE,
        "outputs": {
            "macro_context_handler_bundle": bundle.model_dump(mode="json"),
            "macro_context_operation_mode_qualification": panel.model_dump(mode="json"),
        },
    }

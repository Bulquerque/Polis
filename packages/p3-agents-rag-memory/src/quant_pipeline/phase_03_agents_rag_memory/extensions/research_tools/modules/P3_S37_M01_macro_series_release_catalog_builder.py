from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..families.macro.catalog import (
    MacroSeriesReleaseCatalogBuilder,
)

MODULE_ID = "P3.S37.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "macro_series_release_catalog_builder"
SUBPHASE = "P3.S37"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S37_M01_macro_series_release_catalog_builder.yaml"
REQUIRED_INPUTS = ("research_data_boundary_bundle",)
OPTIONAL_INPUTS = ("macro_series_metadata_registry", "macro_asset_context_registry")
PRODUCED_OUTPUTS = (
    "macro_series_release_catalog",
    "macro_view_readiness_report",
    "macro_asset_context_config_snapshot",
)


def _artifacts(bundle: Mapping[str, Any]) -> Mapping[str, object]:
    for key in ("artifacts", "views", "p2_artifacts"):
        value = bundle.get(key)
        if isinstance(value, Mapping):
            return value
    return bundle


async def execute(inputs: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    bundle = inputs["research_data_boundary_bundle"]
    if not isinstance(bundle, Mapping):
        raise TypeError("research_data_boundary_bundle must be a mapping")
    raw_snapshot_id = bundle.get("snapshot_id")
    if not isinstance(raw_snapshot_id, str) or not raw_snapshot_id.strip():
        raise ValueError("research_data_boundary_bundle.snapshot_id is required")
    snapshot_id = raw_snapshot_id.strip()
    catalog, readiness, contexts = MacroSeriesReleaseCatalogBuilder().build(
        snapshot_id=snapshot_id,
        artifacts=_artifacts(bundle),
        metadata_registry=inputs.get("macro_series_metadata_registry"),
        asset_context_registry=inputs.get("macro_asset_context_registry"),
    )
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "subphase": SUBPHASE,
        "outputs": {
            "macro_series_release_catalog": catalog.model_dump(mode="json"),
            "macro_view_readiness_report": readiness.model_dump(mode="json"),
            "macro_asset_context_config_snapshot": contexts.model_dump(mode="json"),
        },
    }

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.view_binding import (
    MarketViewBindingBuilder,
)

MODULE_ID = "P3.S36.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "market_view_binding_builder"
SUBPHASE = "P3.S36"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S36_M01_market_view_binding_builder.yaml"
REQUIRED_INPUTS = ("research_data_boundary_bundle",)
PRODUCED_OUTPUTS = (
    "market_view_binding",
    "options_view_binding",
    "market_view_readiness_report",
    "options_view_readiness_report",
)


def _artifacts(bundle: Mapping[str, Any]) -> Mapping[str, object]:
    for key in ("artifacts", "views", "p2_artifacts"):
        value = bundle.get(key)
        if isinstance(value, Mapping):
            return value
    return bundle


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    del context
    bundle = inputs["research_data_boundary_bundle"]
    if not isinstance(bundle, Mapping):
        raise TypeError("research_data_boundary_bundle must be a mapping")
    raw_snapshot_id = bundle.get("snapshot_id")
    if not isinstance(raw_snapshot_id, str) or not raw_snapshot_id.strip():
        raise ValueError("research_data_boundary_bundle.snapshot_id is required")
    snapshot_id = raw_snapshot_id.strip()
    market, options, market_report, options_report = MarketViewBindingBuilder().build(
        snapshot_id=snapshot_id,
        artifacts=_artifacts(bundle),
    )
    return {
        "market_view_binding": market.model_dump(mode="json"),
        "options_view_binding": options.model_dump(mode="json"),
        "market_view_readiness_report": market_report.model_dump(mode="json"),
        "options_view_readiness_report": options_report.model_dump(mode="json"),
    }

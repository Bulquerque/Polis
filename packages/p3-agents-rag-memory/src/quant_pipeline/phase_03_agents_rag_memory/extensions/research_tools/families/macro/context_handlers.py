from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from .asset_context import MacroAssetContextHandler
from .catalog_contracts import (
    AssetMacroContextRegistrySnapshot,
    MacroSeriesReleaseCatalog,
)
from .comparison import MacroSeriesComparisonHandler
from .ports import PitMacroQueryPort
from .request_contracts import MacroToolCallContext
from .result_contracts import MacroToolResultEnvelope


class MacroContextHandlers:
    """Stable façade for comparison and governed asset-context operations."""

    def __init__(
        self,
        boundary: PitMacroQueryPort,
        catalog: MacroSeriesReleaseCatalog,
        context_registry: AssetMacroContextRegistrySnapshot,
    ) -> None:
        self._comparison = MacroSeriesComparisonHandler(boundary, catalog)
        self._asset_context = MacroAssetContextHandler(context_registry)

    async def compare_series(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        return await self._comparison.execute(arguments, context)

    async def get_asset_context(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        return await self._asset_context.execute(arguments, context)

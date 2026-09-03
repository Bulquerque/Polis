from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from .catalog_contracts import MacroSeriesReleaseCatalog
from .ports import PitMacroQueryPort
from .request_contracts import MacroToolCallContext
from .result_contracts import MacroToolResultEnvelope
from .series_search import MacroSeriesSearchHandler
from .vintage_observations import MacroVintageObservationHandler


class MacroObservationHandlers:
    """Stable façade for search and vintage-aware observation operations."""

    def __init__(
        self,
        boundary: PitMacroQueryPort,
        catalog: MacroSeriesReleaseCatalog,
    ) -> None:
        self._search = MacroSeriesSearchHandler(boundary, catalog)
        self._vintages = MacroVintageObservationHandler(boundary, catalog)

    async def search_series(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        return await self._search.execute(arguments, context)

    async def get_observations(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        return await self._vintages.get_observations(arguments, context)

    async def get_release_snapshot(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        return await self._vintages.get_release_snapshot(arguments, context)

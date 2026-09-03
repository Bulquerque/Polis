from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import JsonValue

from .catalog_contracts import AssetMacroContextRegistrySnapshot, MacroSeriesReleaseCatalog
from .context_handlers import MacroContextHandlers
from .observations import MacroObservationHandlers
from .ports import PitMacroQueryPort
from .request_contracts import MacroToolCallContext
from .result_contracts import MacroToolResultEnvelope

Handler = Callable[[Mapping[str, JsonValue], MacroToolCallContext], Awaitable[MacroToolResultEnvelope]]


@dataclass(frozen=True, slots=True)
class MacroRuntimeHandlerBundle:
    handlers: Mapping[tuple[str, str], Handler]

    async def execute(
        self,
        tool_id: str,
        operation_id: str,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        handler = self.handlers.get((tool_id, operation_id))
        if handler is None:
            raise KeyError(f"handler not registered: {tool_id}/{operation_id}")
        return await handler(arguments, context)


class MacroHandlers:
    def __init__(
        self,
        boundary: PitMacroQueryPort,
        catalog: MacroSeriesReleaseCatalog,
        context_registry: AssetMacroContextRegistrySnapshot,
    ) -> None:
        observations = MacroObservationHandlers(boundary, catalog)
        contextual = MacroContextHandlers(boundary, catalog, context_registry)
        self._handlers: dict[tuple[str, str], Handler] = {
            ("macro.observation.v1", "search_series"): observations.search_series,
            ("macro.observation.v1", "get_observations"): observations.get_observations,
            ("macro.observation.v1", "get_release_snapshot"): observations.get_release_snapshot,
            ("macro.observation.v1", "compare_series"): contextual.compare_series,
            ("macro.observation.v1", "get_asset_context"): contextual.get_asset_context,
        }

    def bundle(self) -> MacroRuntimeHandlerBundle:
        return MacroRuntimeHandlerBundle(handlers=MappingProxyType(self._handlers))

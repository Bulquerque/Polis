from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import JsonValue

from .market_handlers import MarketObservationHandlers
from .option_handlers import OptionObservationHandlers
from .ports import PitMarketQueryPort
from .request_contracts import MarketToolCallContext
from .result_contracts import MarketDerivativesToolResultEnvelope

Handler = Callable[
    [Mapping[str, JsonValue], MarketToolCallContext],
    Awaitable[MarketDerivativesToolResultEnvelope],
]


@dataclass(frozen=True, slots=True)
class MarketDerivativesRuntimeHandlerBundle:
    handlers: Mapping[tuple[str, str], Handler]

    async def execute(
        self,
        tool_id: str,
        operation_id: str,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        handler = self.handlers.get((tool_id, operation_id))
        if handler is None:
            raise KeyError(f"handler not registered: {tool_id}/{operation_id}")
        return await handler(arguments, context)


class MarketDerivativesHandlers:
    def __init__(self, boundary: PitMarketQueryPort) -> None:
        self._market = MarketObservationHandlers(boundary)
        self._options = OptionObservationHandlers(boundary)

    def bundle(self) -> MarketDerivativesRuntimeHandlerBundle:
        handlers: dict[tuple[str, str], Handler] = {
            ("market.observation.v1", "get_snapshot"): self._market.get_snapshot,
            ("market.observation.v1", "get_history"): self._market.get_history,
            ("market.observation.v1", "get_liquidity"): self._market.get_liquidity,
            ("market.observation.v1", "get_corporate_actions"): self._market.get_corporate_actions,
            ("market.observation.v1", "compare_instruments"): self._market.compare_instruments,
            ("options.observation.v1", "get_contracts"): self._options.get_contracts,
            ("options.observation.v1", "get_chain_snapshot"): self._options.get_chain_snapshot,
            ("options.observation.v1", "get_quote_history"): self._options.get_quote_history,
            ("options.observation.v1", "get_surface_diagnostics"): self._options.get_surface_diagnostics,
        }
        return MarketDerivativesRuntimeHandlerBundle(handlers=MappingProxyType(handlers))

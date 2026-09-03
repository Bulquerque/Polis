from __future__ import annotations

from .handlers import MarketDerivativesHandlers, MarketDerivativesRuntimeHandlerBundle
from .ports import PitMarketQueryPort


def create_market_derivatives_runtime_bundle(
    boundary: PitMarketQueryPort,
) -> MarketDerivativesRuntimeHandlerBundle:
    return MarketDerivativesHandlers(boundary).bundle()

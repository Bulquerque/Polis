from __future__ import annotations

from .base import SourceAdapter
from .http_adapters import (
    AlphaVantageAdapter, AlphaVantageNewsAdapter, AlpacaAdapter, B3Adapter, BrapiAdapter, BeaAdapter, BlsAdapter,
    EiaAdapter, FinnhubAdapter, FmpAdapter, FredAdapter, GenericHttpAdapter,
    GdeltAdapter, LseAdapter, MarketauxAdapter, MarketstackAdapter, SecAdapter,
)


_ADAPTER_TYPES = {
    "generic_http": GenericHttpAdapter,
    "fred": FredAdapter,
    "bls": BlsAdapter,
    "bea": BeaAdapter,
    "eia": EiaAdapter,
    "sec": SecAdapter,
    "lse": LseAdapter,
    "b3": B3Adapter,
    "alpaca": AlpacaAdapter,
    "finnhub": FinnhubAdapter,
    "fmp": FmpAdapter,
    "alpha_vantage": AlphaVantageAdapter,
    "alpha_vantage_news": AlphaVantageNewsAdapter,
    "gdelt": GdeltAdapter,
    "brapi": BrapiAdapter,
    "marketstack": MarketstackAdapter,
    "marketaux": MarketauxAdapter,
}

ALIASES = {
    "london_strategic_edge": "lse",
    "financial_modeling_prep": "fmp",
    "alpha-vantage": "alpha_vantage",
}


def normalize_adapter_id(adapter_id: str | None) -> str | None:
    if not adapter_id:
        return None
    lowered = str(adapter_id).strip().lower()
    return ALIASES.get(lowered, lowered)


def resolve_adapter(adapter_id: str | None) -> SourceAdapter | None:
    normalized = normalize_adapter_id(adapter_id)
    if not normalized:
        return None
    adapter_type = _ADAPTER_TYPES.get(normalized)
    return adapter_type() if adapter_type else None


def registered_adapter_ids() -> set[str]:
    # local_file is a built-in non-network capture path handled before adapter resolution.
    return set(_ADAPTER_TYPES) | {"local_file"}

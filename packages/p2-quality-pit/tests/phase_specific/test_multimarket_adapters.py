from __future__ import annotations

import pytest

from quant_pipeline.phase_02_quality_pit.adapters.b3_market_adapter import normalize_b3_instrument
from quant_pipeline.phase_02_quality_pit.adapters.london_strategic_edge_adapter import LondonStrategicEdgeAdapter
from quant_pipeline.phase_02_quality_pit.profiles import CANONICAL_OPTIONS_PROFILE, DAILY_MARK_RESEARCH_BR_V1, DAILY_MARK_RESEARCH_US_V1, MULTI_MARKET_BR_US_V1


def test_provider_neutral_ids_keep_same_symbol_in_separate_markets():
    br = normalize_b3_instrument({"instrument_id": "PETR4", "symbol": "PETR4"})
    us = LondonStrategicEdgeAdapter.canonical_underlying("PETR4")
    assert br["canonical_instrument_id"] == "BR:B3:EQUITY:PETR4"
    assert us == "US:NASDAQ:EQUITY:PETR4"
    assert br["canonical_instrument_id"] != us


def test_b3_option_requires_official_instrument_identity():
    with pytest.raises(ValueError, match="official instrument_id"):
        normalize_b3_instrument({"symbol": "PETR4C"})


def test_lse_option_identity_is_provider_contract_identity():
    assert LondonStrategicEdgeAdapter.canonical_option("AAPL260612C00205000") == "US:OPRA:OPTION:AAPL260612C00205000"


def test_profiles_split_core_and_extension():
    assert DAILY_MARK_RESEARCH_BR_V1["required_markets"] == ["BR"]
    assert DAILY_MARK_RESEARCH_US_V1["required_for_core_closure"] is False
    assert MULTI_MARKET_BR_US_V1["includes"] == ["DAILY_MARK_RESEARCH_BR_V1", "DAILY_MARK_RESEARCH_US_V1"]


def test_canonical_options_sources_are_lse_and_b3():
    assert CANONICAL_OPTIONS_PROFILE["allowed_option_providers"] == ["LONDON_STRATEGIC_EDGE", "B3_PUBLIC_DATA", "B3_COTAHIST"]
    assert CANONICAL_OPTIONS_PROFILE["source_priority"] == ["LONDON_STRATEGIC_EDGE", "B3_PUBLIC_DATA", "B3_COTAHIST"]

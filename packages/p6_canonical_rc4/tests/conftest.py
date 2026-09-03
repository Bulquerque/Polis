from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import canonical_sha256

UTC = timezone.utc
DECISION_TIME = datetime(2026, 1, 2, 20, 0, tzinfo=UTC)
EXPIRATION = DECISION_TIME + timedelta(days=30)


def external_artifact(name, records):
    return {
        "artifact_id": f"{name}-artifact",
        "content_sha256": canonical_sha256(records),
        "records": records,
    }


def build_inputs():
    contracts = []
    quotes = []
    call_mids = {80: 21, 90: 12, 100: 6, 110: 2.5, 120: 1}
    put_mids = {80: 1, 90: 2.5, 100: 6, 110: 12, 120: 21}
    for option_type, mids in (("CALL", call_mids), ("PUT", put_mids)):
        for strike, midpoint in mids.items():
            contract_id = f"XYZ-{option_type}-{strike}"
            contracts.append({
                "contract_id": contract_id,
                "underlying_id": "XYZ",
                "option_type": option_type,
                "strike": str(strike),
                "expiration": EXPIRATION.isoformat(),
                "exercise_style": "EUROPEAN",
                "settlement_type": "CASH",
                "multiplier": "100",
                "currency": "USD",
                "listing_exchange": "TEST",
                "first_trade_date": (DECISION_TIME - timedelta(days=100)).isoformat(),
                "last_trade_date": None,
                "contract_status": "ACTIVE",
                "source_artifact_id": "contracts-artifact",
                "source_record_id": contract_id,
            })
            quotes.append({
                "contract_id": contract_id,
                "quote_time": (DECISION_TIME - timedelta(minutes=1)).isoformat(),
                "available_at": (DECISION_TIME - timedelta(seconds=30)).isoformat(),
                "bid": str(Decimal(str(midpoint)) - Decimal("0.1")),
                "ask": str(Decimal(str(midpoint)) + Decimal("0.1")),
                "bid_size": "100",
                "ask_size": "100",
                "last": str(midpoint),
                "last_size": "1",
                "volume": "1000",
                "open_interest": "5000",
                "implied_volatility": "0.2",
                "quote_quality": "TWO_SIDED_EXECUTABLE",
                "source_id": f"quote-{contract_id}",
            })
    beliefs = [{
        "belief_state_id": "belief-xyz",
        "underlying_id": "XYZ",
        "decision_time": DECISION_TIME.isoformat(),
        "horizon_days": 30,
        "scenarios": [
            {"scenario_id": "down", "terminal_underlying_price": "80", "probability": "0.2", "path_prices": []},
            {"scenario_id": "flat", "terminal_underlying_price": "100", "probability": "0.5", "path_prices": []},
            {"scenario_id": "up", "terminal_underlying_price": "120", "probability": "0.3", "path_prices": []},
        ],
        "confidence": "0.8",
        "regime_context": "NORMAL",
        "ambiguity_set_id": None,
        "scenario_capability": "AVAILABLE",
        "ambiguity_capability": "UNAVAILABLE",
        "surface_capability": "UNAVAILABLE",
        "source_artifact_id": "belief-artifact",
    }]
    underlyings = [{
        "underlying_id": "XYZ",
        "quote_time": (DECISION_TIME - timedelta(minutes=1)).isoformat(),
        "available_at": (DECISION_TIME - timedelta(seconds=30)).isoformat(),
        "bid": "99.9",
        "ask": "100.1",
        "last": "100",
        "currency": "USD",
        "exchange": "TEST",
        "trading_status": "OPEN",
        "source_artifact_id": "underlying-artifact",
        "source_record_id": "XYZ",
    }]
    return {
        "market_belief_state": external_artifact("belief", beliefs),
        "clean_option_contract_panel": external_artifact("contracts", contracts),
        "clean_option_quotes_panel": external_artifact("quotes", quotes),
        "clean_underlying_trade_panel": external_artifact("underlyings", underlyings),
    }


def build_configuration():
    return {
        "run_id": "wave1-run",
        "cycle_id": "wave1-cycle",
        "decision_time": DECISION_TIME.isoformat(),
        "created_at": (DECISION_TIME + timedelta(seconds=1)).isoformat(),
        "available_at": (DECISION_TIME + timedelta(seconds=1)).isoformat(),
        "seed": 7,
        "strategy": {"allow_cash_secured_short_put": True},
        "risk": {"maximum_relative_spread": "1", "minimum_liquidity_score": "0"},
    }


@pytest.fixture
def inputs():
    return build_inputs()


@pytest.fixture
def configuration():
    return build_configuration()


@pytest.fixture
def copied_inputs(inputs):
    return deepcopy(inputs)

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2026-07-23T12:00:00Z",
    "as_of_date": "2026-07-23T12:00:00Z",
}


def mod(name):
    return importlib.import_module(f"quant_pipeline.phase_02_quality_pit.modules.{name}")


def quality(*source_ids, status="PASS"):
    return {
        "records": [
            {
                "source_id": source_id,
                "quality_status": status,
                "quality_score": 1.0 if status == "PASS" else 0.7,
                "error_flag": status == "BLOCK",
            }
            for source_id in source_ids
        ]
    }


def contract_row(source, option_id, strike, option_type="CALL", **extra):
    return {
        "record_domain": "OPTION_CONTRACT",
        "source_id": source,
        "option_id": option_id,
        "underlying": "AAPL",
        "expiration_date": "2026-08-21",
        "strike": strike,
        "option_type": option_type,
        "contract_size": 100,
        "available_at": "2026-07-23T10:00:00Z",
        "lineage_id": f"lin-{source}-{option_id}",
        **extra,
    }


def build_contracts(rows):
    return mod("P2_S4_M01_option_contract_parser").run_module(
        {
            "identifier_harmonized_bundle": {"records": rows},
            "clean_calendar_panel": {"records": []},
            "source_quality_panel": quality(*(sorted({r["source_id"] for r in rows}))),
        },
        CONFIG,
    )["outputs"]["clean_option_contract_panel"]


def test_contract_identity_distinguishes_strike_and_option_type():
    rows = [
        contract_row("s1", "c100", 100, "CALL"),
        contract_row("s1", "c110", 110, "CALL"),
        contract_row("s1", "p100", 100, "PUT"),
    ]
    output = build_contracts(rows)
    keys = {row["contract_key"] for row in output["records"]}
    assert len(keys) == 3


def test_contract_identity_normalizes_decimal_strike_and_reconciles_providers():
    rows = [
        contract_row("a", "AAPL_A", "100.000", "CALL"),
        contract_row("b", "AAPL_B", 100.0, "C"),
    ]
    output = build_contracts(rows)
    assert len(output["records"]) == 1
    row = output["records"][0]
    assert row["identity_mode"] == "ECONOMIC"
    assert set(row["source_ids"]) == {"a", "b"}
    assert set(row["provider_option_ids"]) == {"AAPL_A", "AAPL_B"}


def test_legacy_incomplete_contract_is_explicit_not_fabricated():
    output = build_contracts(
        [
            {
                "source_id": "s1",
                "option_id": "legacy",
                "expiration_date": "2026-08-21",
                "strike": 100,
                "available_at": "2026-07-23T10:00:00Z",
                "lineage_id": "l1",
            }
        ]
    )
    row = output["records"][0]
    assert row["option_type"] == "UNKNOWN"
    assert row["contract_size"] is None
    assert row["underlying"] == "UNKNOWN"
    assert row["identity_mode"] == "PROVIDER_FALLBACK"
    assert "OPTION_TYPE_UNKNOWN" in row["quality_reasons"]


def test_quote_never_falls_back_to_first_unrelated_contract():
    contracts = build_contracts(
        [contract_row("s1", "c100", 100), contract_row("s1", "c110", 110)]
    )
    output = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": {
                "records": [
                    {
                        "record_domain": "OPTION_QUOTE",
                        "source_id": "s1",
                        "option_id": "DOES_NOT_EXIST",
                        "date": "2026-07-23",
                        "available_at": "2026-07-23T10:30:00Z",
                        "bid": 1,
                        "ask": 1.1,
                    }
                ]
            },
            "clean_option_contract_panel": contracts,
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    assert output["records"] == []
    assert output["rejected_count"] == 1
    assert "quote_contract_not_found" in output["rejection_reasons"]


def test_quote_resolves_canonical_identity_even_when_upstream_key_is_wrong():
    contracts = build_contracts([contract_row("s1", "c100", 100)])
    quote = contract_row(
        "s1",
        "provider-quote-id",
        100,
        "CALL",
        record_domain="OPTION_QUOTE",
        contract_key="legacy-wrong-key",
        date="2026-07-23",
        as_of_date="2026-07-23T11:00:00Z",
        available_at="2026-07-23T10:30:00Z",
        bid=1.0,
        ask=1.2,
        last_price=1.1,
        volume=10,
        open_interest=100,
    )
    output = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": {"records": [quote]},
            "clean_option_contract_panel": contracts,
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    assert len(output["records"]) == 1
    row = output["records"][0]
    assert row["contract_key"] == contracts["records"][0]["contract_key"]
    assert row["source_observation_key"] == "legacy-wrong-key"
    assert row["match_mode"] == "CANONICAL_IDENTITY"


def test_crossed_quote_is_rejected_not_repaired():
    contracts = build_contracts([contract_row("s1", "c100", 100)])
    quote = contract_row(
        "s1",
        "c100",
        100,
        record_domain="OPTION_QUOTE",
        date="2026-07-23",
        available_at="2026-07-23T10:30:00Z",
        bid=1.2,
        ask=1.0,
    )
    output = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": {"records": [quote]},
            "clean_option_contract_panel": contracts,
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    assert output["records"] == []
    assert "CROSSED_MARKET" in output["rejection_reasons"]


def test_missing_bid_ask_remain_unknown_and_do_not_become_fake_cost():
    contracts = build_contracts([contract_row("s1", "c100", 100)])
    quote = contract_row(
        "s1",
        "c100",
        100,
        record_domain="OPTION_QUOTE",
        date="2026-07-23",
        as_of_date="2026-07-23T11:00:00Z",
        available_at="2026-07-23T10:30:00Z",
        last_price=1.1,
        volume=None,
        open_interest=None,
    )
    quotes = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": {"records": [quote]},
            "clean_option_contract_panel": contracts,
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    qrow = quotes["records"][0]
    assert qrow["bid"] is None and qrow["ask"] is None
    assert qrow["volume"] is None and qrow["open_interest"] is None
    assert qrow["quality_flag"] == "PASS"

    refs = mod("P2_S4_M03_cost_liquidity_reference_builder").run_module(
        {
            "clean_option_quotes_panel": quotes,
            "clean_underlying_panel": {"records": []},
            "clean_underlying_trade_panel": {"records": []},
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]
    cost = refs["clean_cost_reference_panel"]["records"][0]
    liq = refs["clean_liquidity_reference_panel"]["records"][0]
    assert cost["cost_estimate"] is None
    assert cost["cost_reliability"] == "UNAVAILABLE"
    assert "VOLUME_UNKNOWN" in liq["quality_reasons"]
    assert "OPEN_INTEREST_UNKNOWN" in liq["quality_reasons"]


def test_latest_causally_available_quote_is_selected_for_daily_grain():
    contracts = build_contracts([contract_row("s1", "c100", 100)])
    base = contract_row("s1", "c100", 100, record_domain="OPTION_QUOTE", date="2026-07-23")
    rows = [
        {**base, "available_at": "2026-07-23T10:00:00Z", "bid": 1.0, "ask": 1.1},
        {**base, "available_at": "2026-07-23T11:00:00Z", "bid": 1.2, "ask": 1.3},
    ]
    output = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": {"records": rows},
            "clean_option_contract_panel": contracts,
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    assert len(output["records"]) == 1
    assert output["records"][0]["bid"] == 1.2


def test_cost_and_liquidity_use_s3_underlying_context_without_inventing_tradeability():
    contracts = build_contracts([contract_row("s1", "c100", 100)])
    quote = contract_row(
        "s1",
        "c100",
        100,
        record_domain="OPTION_QUOTE",
        date="2026-07-23",
        as_of_date="2026-07-23T11:00:00Z",
        available_at="2026-07-23T10:30:00Z",
        bid=1.0,
        ask=1.2,
        volume=10,
        open_interest=100,
    )
    quotes = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": {"records": [quote]},
            "clean_option_contract_panel": contracts,
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    refs = mod("P2_S4_M03_cost_liquidity_reference_builder").run_module(
        {
            "clean_option_quotes_panel": quotes,
            "clean_underlying_panel": {"records": [{"underlying": "AAPL", "date": "2026-07-23", "close": 200}]},
            "clean_underlying_trade_panel": {
                "records": [
                    {
                        "underlying": "AAPL",
                        "date": "2026-07-23",
                        "tradability_flag": False,
                        "liquidity_score": None,
                    }
                ]
            },
            "source_quality_panel": quality("s1"),
        },
        CONFIG,
    )["outputs"]
    cost = refs["clean_cost_reference_panel"]["records"][0]
    liq = refs["clean_liquidity_reference_panel"]["records"][0]
    assert cost["cost_estimate"] == pytest.approx(0.2)
    assert cost["cost_reliability"] == "DEGRADED"
    assert "UNDERLYING_NON_TRADABLE" in cost["quality_reasons"]
    assert liq["underlying_tradability"] is False
    assert liq["liquidity_reliability"] == "DEGRADED"


def test_liquidity_is_deterministic_and_zero_is_not_missing():
    quote = {
        "source_id": "s1",
        "contract_key": "k1",
        "underlying": "AAPL",
        "date": "2026-07-23",
        "bid": 1.0,
        "ask": 1.0,
        "volume": 0,
        "open_interest": 0,
        "available_at": "2026-07-23T10:00:00Z",
        "as_of_date": "2026-07-23T11:00:00Z",
        "lineage_id": "l1",
    }
    inputs = {
        "clean_option_quotes_panel": {"records": [quote]},
        "clean_underlying_panel": {"records": []},
        "clean_underlying_trade_panel": {"records": []},
        "source_quality_panel": quality("s1"),
    }
    module = mod("P2_S4_M03_cost_liquidity_reference_builder")
    first = module.run_module(inputs, CONFIG)["outputs"]["clean_liquidity_reference_panel"]["records"][0]
    second = module.run_module(inputs, CONFIG)["outputs"]["clean_liquidity_reference_panel"]["records"][0]
    assert first["liquidity_score"] == second["liquidity_score"]
    assert "VOLUME_UNKNOWN" not in first["quality_reasons"]
    assert "OPEN_INTEREST_UNKNOWN" not in first["quality_reasons"]

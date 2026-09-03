from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2026-07-23T00:00:00Z",
    "as_of_date": "2026-07-23T00:00:00Z",
}


def mod(name: str):
    return importlib.import_module(f"quant_pipeline.phase_02_quality_pit.modules.{name}")


def quality(status="PASS", score=1.0):
    return {
        "records": [
            {
                "source_id": "s1",
                "quality_status": status,
                "quality_score": score,
                "error_flag": status == "BLOCK",
            }
        ]
    }


def test_s3_does_not_fabricate_other_domains_from_underlying():
    underlying = {
        "records": [
            {
                "source_id": "s1",
                "underlying": "PETR4",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 31.5,
            }
        ]
    }
    inputs = {"identifier_harmonized_bundle": underlying, "source_quality_panel": quality()}
    macro = mod("P2_S3_M01_macro_panel_cleaner").run_module(inputs, CONFIG)["outputs"]
    benchmark = mod("P2_S3_M02_benchmark_panel_cleaner").run_module(inputs, CONFIG)["outputs"]
    calendar = mod("P2_S3_M03_calendar_panel_builder").run_module(inputs, CONFIG)["outputs"]
    actions = mod("P2_S3_M04_corporate_actions_cleaner").run_module(
        {**inputs, "clean_calendar_panel": calendar["clean_calendar_panel"]}, CONFIG
    )["outputs"]

    assert macro["clean_macro_br_panel"]["records"] == []
    assert macro["clean_macro_us_panel"]["records"] == []
    assert benchmark["clean_benchmark_panel"]["records"] == []
    assert calendar["clean_calendar_panel"]["records"] == []
    assert actions["clean_corporate_actions_panel"]["records"] == []


def test_calendar_parses_textual_tristate_flags_without_truthiness_bug():
    rows = {"records": [
        {"record_domain": "CALENDAR", "source_id": "s1", "calendar_id": "B3", "date": "2026-01-19", "is_trading_day": "false"},
        {"record_domain": "CALENDAR", "source_id": "s1", "calendar_id": "NYSE", "date": "2026-01-19", "is_trading_day": "0"},
        {"record_domain": "CALENDAR", "source_id": "s1", "calendar_id": "LSE", "date": "2026-01-19", "is_trading_day": None},
    ]}
    result = mod("P2_S3_M03_calendar_panel_builder").run_module(
        {"identifier_harmonized_bundle": rows, "source_quality_panel": quality()}, CONFIG
    )
    values = {row["calendar_id"]: row["is_trading_day"] for row in result["outputs"]["clean_calendar_panel"]["records"]}
    assert values == {"B3": False, "NYSE": False, "LSE": None}

    rows["records"][2]["is_trading_day"] = "unknown"
    with pytest.raises(Exception, match="INVALID_TRADING_FLAG"):
        mod("P2_S3_M03_calendar_panel_builder").run_module(
            {"identifier_harmonized_bundle": rows, "source_quality_panel": quality()}, CONFIG
        )


def test_calendar_supports_multiple_markets_on_same_date():
    rows = {
        "records": [
            {
                "record_domain": "CALENDAR",
                "source_id": "s1",
                "calendar_id": "B3",
                "date": "2026-01-19",
                "is_trading_day": True,
            },
            {
                "record_domain": "CALENDAR",
                "source_id": "s1",
                "calendar_id": "NYSE",
                "date": "2026-01-19",
                "is_trading_day": False,
                "holiday_code": "MLK_DAY",
            },
        ]
    }
    output = mod("P2_S3_M03_calendar_panel_builder").run_module(
        {"identifier_harmonized_bundle": rows, "source_quality_panel": quality()}, CONFIG
    )["outputs"]["clean_calendar_panel"]
    assert len(output["records"]) == 2
    assert {(r["calendar_id"], r["is_trading_day"]) for r in output["records"]} == {
        ("B3", True),
        ("NYSE", False),
    }


def test_future_effective_corporate_action_is_valid_but_not_applied_early():
    bundle = {
        "records": [
            {
                "record_domain": "CORPORATE_ACTION",
                "source_id": "s1",
                "underlying": "PETR4",
                "action_type": "SPLIT",
                "available_at": "2026-05-01T12:00:00Z",
                "effective_date": "2026-06-01",
                "adjustment_factor": 0.5,
            },
            {
                "record_domain": "UNDERLYING",
                "source_id": "s1",
                "underlying": "PETR4",
                "date": "2026-05-15",
                "available_at": "2026-05-15T21:00:00Z",
                "close": 40,
                "price_adjustment_policy": "RAW",
            },
        ]
    }
    empty_calendar = {"records": []}
    actions = mod("P2_S3_M04_corporate_actions_cleaner").run_module(
        {
            "identifier_harmonized_bundle": bundle,
            "source_quality_panel": quality(),
            "clean_calendar_panel": empty_calendar,
        },
        CONFIG,
    )["outputs"]["clean_corporate_actions_panel"]
    assert actions["records"][0]["effective_date"] == "2026-06-01"

    underlying = mod("P2_S3_M05_underlying_panel_cleaner").run_module(
        {
            "identifier_harmonized_bundle": bundle,
            "source_quality_panel": quality(),
            "clean_calendar_panel": empty_calendar,
            "clean_corporate_actions_panel": actions,
        },
        CONFIG,
    )["outputs"]["clean_underlying_panel"]
    row = underlying["records"][0]
    assert row["adjustment_factor"] == 1.0
    assert "NO_APPLICABLE_ACTION" in row["quality_reasons"]


def test_already_adjusted_provider_is_not_adjusted_again():
    bundle = {
        "records": [
            {
                "record_domain": "UNDERLYING",
                "source_id": "s1",
                "underlying": "PETR4",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 30,
                "price_adjustment_policy": "SPLIT_ADJUSTED",
            }
        ]
    }
    output = mod("P2_S3_M05_underlying_panel_cleaner").run_module(
        {
            "identifier_harmonized_bundle": bundle,
            "source_quality_panel": quality(),
            "clean_calendar_panel": {"records": []},
            "clean_corporate_actions_panel": {"records": []},
        },
        CONFIG,
    )["outputs"]["clean_underlying_panel"]
    row = output["records"][0]
    assert row["adjustment_factor"] == 1.0
    assert "PROVIDER_ALREADY_ADJUSTED" in row["quality_reasons"]


def test_unknown_calendar_is_conservative_and_does_not_fake_quotes_or_costs():
    underlying_bundle = {
        "records": [
            {
                "record_domain": "UNDERLYING",
                "source_id": "s1",
                "underlying": "PETR4",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 31.5,
            }
        ]
    }
    clean_underlying = mod("P2_S3_M05_underlying_panel_cleaner").run_module(
        {
            "identifier_harmonized_bundle": underlying_bundle,
            "source_quality_panel": quality(),
            "clean_calendar_panel": {"records": []},
            "clean_corporate_actions_panel": {"records": []},
        },
        CONFIG,
    )["outputs"]["clean_underlying_panel"]
    trade = mod("P2_S3_M06_underlying_trade_panel_builder").run_module(
        {
            "clean_underlying_panel": clean_underlying,
            "clean_calendar_panel": {"records": []},
            "source_quality_panel": quality(),
        },
        CONFIG,
    )["outputs"]["clean_underlying_trade_panel"]
    row = trade["records"][0]
    assert row["tradability_flag"] is False
    assert row["bid"] is None
    assert row["ask"] is None
    assert row["cost_estimate"] is None
    assert row["liquidity_score"] is None
    assert "MARKET_CLOSED_OR_UNKNOWN" in row["tradability_reasons"]


def test_explicit_open_calendar_enables_tradability_without_fabricating_bid_ask():
    bundle = {
        "records": [
            {
                "record_domain": "UNDERLYING",
                "source_id": "s1",
                "underlying": "PETR4",
                "calendar_id": "B3",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 31.5,
            },
            {
                "record_domain": "CALENDAR",
                "source_id": "s1",
                "calendar_id": "B3",
                "date": "2026-07-22",
                "is_trading_day": True,
            },
        ]
    }
    calendar = mod("P2_S3_M03_calendar_panel_builder").run_module(
        {"identifier_harmonized_bundle": bundle, "source_quality_panel": quality()}, CONFIG
    )["outputs"]["clean_calendar_panel"]
    underlying = mod("P2_S3_M05_underlying_panel_cleaner").run_module(
        {
            "identifier_harmonized_bundle": bundle,
            "source_quality_panel": quality(),
            "clean_calendar_panel": calendar,
            "clean_corporate_actions_panel": {"records": []},
        },
        CONFIG,
    )["outputs"]["clean_underlying_panel"]
    trade = mod("P2_S3_M06_underlying_trade_panel_builder").run_module(
        {
            "clean_underlying_panel": underlying,
            "clean_calendar_panel": calendar,
            "source_quality_panel": quality(),
        },
        CONFIG,
    )["outputs"]["clean_underlying_trade_panel"]
    row = trade["records"][0]
    assert row["tradability_flag"] is True
    assert row["bid"] is None and row["ask"] is None
    assert row["calendar_aligned"] is True


def test_conflicting_duplicate_underlying_date_is_rejected():
    bundle = {
        "records": [
            {
                "record_domain": "UNDERLYING",
                "source_id": "s1",
                "underlying": "PETR4",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 31.5,
            },
            {
                "record_domain": "UNDERLYING",
                "source_id": "s2",
                "underlying": "PETR4",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 32.0,
            },
        ]
    }
    with pytest.raises(Exception, match="underlying_date_unique"):
        mod("P2_S3_M05_underlying_panel_cleaner").run_module(
            {
                "identifier_harmonized_bundle": bundle,
                "source_quality_panel": {"records": []},
                "clean_calendar_panel": {"records": []},
                "clean_corporate_actions_panel": {"records": []},
            },
            CONFIG,
        )


def test_blocked_source_is_rejected():
    bundle = {
        "records": [
            {
                "record_domain": "UNDERLYING",
                "source_id": "s1",
                "underlying": "PETR4",
                "date": "2026-07-22",
                "available_at": "2026-07-22T21:00:00Z",
                "close": 31.5,
            }
        ]
    }
    with pytest.raises(Exception, match="source_quality_blocked"):
        mod("P2_S3_M05_underlying_panel_cleaner").run_module(
            {
                "identifier_harmonized_bundle": bundle,
                "source_quality_panel": quality("BLOCK", 0),
                "clean_calendar_panel": {"records": []},
                "clean_corporate_actions_panel": {"records": []},
            },
            CONFIG,
        )

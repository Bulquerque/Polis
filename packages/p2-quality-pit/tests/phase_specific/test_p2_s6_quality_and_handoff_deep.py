from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

M01 = importlib.import_module(
    "quant_pipeline.phase_02_quality_pit.modules.P2_S6_M01_quality_report_phase2_builder"
)
M02 = importlib.import_module(
    "quant_pipeline.phase_02_quality_pit.modules.P2_S6_M02_multi_phase_handoff_packager"
)

CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2024-06-01T00:00:00Z",
    "as_of_date": "2024-06-01T23:59:59Z",
}


def artifact(name: str, rows: list[dict]) -> dict:
    return {
        "artifact_id": f"{name}-a1",
        "created_at": CONFIG["created_at"],
        "lineage_id": f"lineage-{name}",
        "pipeline_version": CONFIG["pipeline_version"],
        "records": rows,
    }


def base_inputs() -> dict:
    quality = artifact(
        "source_quality_panel",
        [
            {
                "source_id": "s1",
                "source_name": "Source 1",
                "source_type": "api",
                "quality_score": 0.95,
                "readability_status": "readable",
                "error_flag": False,
                "warning_flag": False,
                "declared_available_at": "2024-05-31T10:00:00Z",
                "lineage_id": "l-source",
                "pipeline_version": CONFIG["pipeline_version"],
            }
        ],
    )
    context = artifact(
        "clean_context_source_panel",
        [
            {
                "source_id": "s1",
                "source_name": "Source 1",
                "source_type": "api",
                "available_at": "2024-05-31T10:00:00Z",
                "quality_score": 0.95,
                "quality_status": "known",
                "lineage_id": "l-context",
            }
        ],
    )
    documents = artifact(
        "clean_document_panel",
        [
            {
                "document_id": "doc-1",
                "source_id": "s1",
                "source_name": "Source 1",
                "document_type": "news",
                "document_title": "News",
                "document_text_or_path": "text",
                "reference_date": "2024-05-31",
                "available_at": "2024-05-31T10:00:00Z",
                "ingested_at": "2024-05-31T10:00:01Z",
                "source_quality_score": 0.95,
                "language": "en",
                "cleaning_status": "clean",
                "lineage_id": "l-doc",
                "pipeline_version": CONFIG["pipeline_version"],
            }
        ],
    )
    events = artifact(
        "clean_event_reference_panel",
        [
            {
                "event_id": "event-1",
                "event_type": "document_publication",
                "source_id": "s1",
                "reference_date": "2024-05-31",
                "available_at": "2024-05-31T10:00:00Z",
                "lineage_id": "l-event",
                "pipeline_version": CONFIG["pipeline_version"],
            }
        ],
    )
    underlying = artifact(
        "clean_underlying_panel",
        [
            {
                "date": "2024-05-31",
                "as_of_date": "2024-06-01T23:59:59Z",
                "available_at": "2024-05-31T21:00:00Z",
                "underlying": "PETR4",
                "open": 39.0,
                "high": 41.0,
                "low": 38.0,
                "close": 40.0,
                "volume": 1000,
                "financial_volume": 40000,
                "adjustment_factor": 1.0,
                "is_trading_day": True,
                "source_id": "s1",
                "lineage_id": "l-underlying",
                "quality_flag": "PASS",
                "pipeline_version": CONFIG["pipeline_version"],
            }
        ],
    )
    underlying_trade = artifact(
        "clean_underlying_trade_panel",
        [
            {
                "date": "2024-05-31",
                "as_of_date": "2024-06-01T23:59:59Z",
                "available_at": "2024-05-31T21:00:00Z",
                "underlying": "PETR4",
                "reference_price_t": 40.0,
                "bid": 39.99,
                "ask": 40.01,
                "volume": 1000,
                "financial_volume": 40000,
                "tradability_flag": True,
                "cost_estimate": 0.02,
                "liquidity_score": 1.0,
                "source_id": "s1",
                "lineage_id": "l-underlying-trade",
                "pipeline_version": CONFIG["pipeline_version"],
                "artifact_id": "trade-row-1",
                "created_at": CONFIG["created_at"],
            }
        ],
    )
    calendar = artifact(
        "clean_calendar_panel",
        [
            {
                "date": "2024-05-31",
                "is_trading_day": True,
                "available_at": "2024-05-30T00:00:00Z",
                "lineage_id": "l-calendar-row",
            }
        ],
    )
    contracts = artifact(
        "clean_option_contract_panel",
        [
            {
                "option_id": "OPT1",
                "expiration_date": "2024-06-28",
                "contract_key": "PETR4|2024-06-28|C|40",
                "underlying": "PETR4",
                "option_type": "call",
                "strike": 40.0,
                "contract_size": 100,
                "first_seen_date": "2024-05-01",
                "last_seen_date": "2024-05-31",
                "expiration_calendar_date": "2024-06-28",
                "source_id": "s1",
                "lineage_id": "l-contract",
                "pipeline_version": CONFIG["pipeline_version"],
            }
        ],
    )
    quotes = artifact(
        "clean_option_quotes_panel",
        [
            {
                "date": "2024-05-31",
                "as_of_date": "2024-06-01T23:59:59Z",
                "available_at": "2024-05-31T20:00:00Z",
                "underlying": "PETR4",
                "option_id": "OPT1",
                "expiration_date": "2024-06-28",
                "contract_key": "PETR4|2024-06-28|C|40",
                "option_type": "call",
                "strike": 40.0,
                "last_price": 1.5,
                "bid": 1.45,
                "ask": 1.55,
                "volume": 100,
                "financial_volume": 15000,
                "open_interest": 500,
                "source_id": "s1",
                "lineage_id": "l-quote",
                "quality_flag": "PASS",
                "pipeline_version": CONFIG["pipeline_version"],
            }
        ],
    )
    return {
        "source_quality_panel": quality,
        "clean_context_source_panel": context,
        "clean_document_panel": documents,
        "clean_event_reference_panel": events,
        "clean_underlying_panel": underlying,
        "clean_underlying_trade_panel": underlying_trade,
        "clean_macro_br_panel": artifact("clean_macro_br_panel", [{"series_id": "SELIC", "available_at": "2024-05-31T10:00:00Z"}]),
        "clean_macro_us_panel": artifact("clean_macro_us_panel", [{"series_id": "FEDFUNDS", "available_at": "2024-05-31T10:00:00Z"}]),
        "clean_benchmark_panel": artifact("clean_benchmark_panel", [{"benchmark_id": "IBOV", "date": "2024-05-31", "available_at": "2024-05-31T21:00:00Z"}]),
        "clean_calendar_panel": calendar,
        "clean_corporate_actions_panel": artifact("clean_corporate_actions_panel", []),
        "clean_option_contract_panel": contracts,
        "clean_option_quotes_panel": quotes,
        "clean_cost_reference_panel": artifact("clean_cost_reference_panel", [{"contract_key": "PETR4|2024-06-28|C|40", "cost_estimate": 0.10}]),
        "clean_liquidity_reference_panel": artifact("clean_liquidity_reference_panel", [{"contract_key": "PETR4|2024-06-28|C|40", "liquidity_score": 0.9}]),
    }


def test_quality_report_is_real_and_accepts_legitimate_empty_optional_panels():
    result = M01.run_module(base_inputs(), CONFIG)["outputs"]["quality_report_phase_2"]
    assert result["all_official_panels_covered"] is True
    assert result["panel_counts"]["clean_corporate_actions_panel"] == 0
    assert result["status"] in {"PASS", "WARN"}
    assert result["metrics"]["blocking_issue_count"] == 0
    assert "panel_results" in result
    assert "target_readiness" in result


def test_nested_forbidden_field_blocks_quality():
    inputs = base_inputs()
    inputs["clean_document_panel"]["records"][0]["metadata"] = {"prediction": 0.8}
    report = M01.run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    assert report["status"] == "BLOCK"
    assert any(issue["code"] == "P2Q_FORBIDDEN_FIELD" for issue in report["blocking_issues"])


def test_future_available_at_blocks_quality():
    inputs = base_inputs()
    inputs["clean_underlying_panel"]["records"][0]["available_at"] = "2024-06-02T00:00:00Z"
    report = M01.run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    assert report["status"] == "BLOCK"
    assert any(issue["code"] == "P2Q_FUTURE_DATA" for issue in report["blocking_issues"])


def test_orphan_option_quote_blocks_quality():
    inputs = base_inputs()
    inputs["clean_option_quotes_panel"]["records"][0]["contract_key"] = "UNKNOWN"
    report = M01.run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    assert report["status"] == "BLOCK"
    assert any(issue["code"] == "P2Q_ORPHAN_OPTION_QUOTE" for issue in report["blocking_issues"])


def test_calendar_tradability_conflict_blocks_quality():
    inputs = base_inputs()
    inputs["clean_calendar_panel"]["records"][0]["is_trading_day"] = False
    report = M01.run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    assert report["status"] == "BLOCK"
    assert any(issue["code"] == "P2Q_CALENDAR_TRADABILITY_CONFLICT" for issue in report["blocking_issues"])


def test_handoff_gate_rejects_block_and_preserves_legacy_surface():
    inputs = base_inputs()
    report = M01.run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    handoffs = M02.run_module({**inputs, "quality_report_phase_2": report}, CONFIG)["outputs"]

    assert handoffs["phase3_handoff_manifest"]["artifact_ids"]
    assert handoffs["phase3_handoff_manifest"]["target_artifact_ids"]
    assert handoffs["phase4_handoff_manifest"]["target_phase"] == "phase_04_feature_base"
    assert handoffs["phase6_handoff_manifest"]["target_phase"] == "phase_06_candidate_generation"
    assert "clean_document_panel-a1" in handoffs["phase3_handoff_manifest"]["target_artifact_ids"]
    assert "clean_underlying_panel-a1" in handoffs["phase4_handoff_manifest"]["target_artifact_ids"]
    assert "clean_option_contract_panel-a1" in handoffs["phase6_handoff_manifest"]["target_artifact_ids"]
    assert "records" not in handoffs["phase3_handoff_manifest"]

    blocked = dict(report)
    blocked["status"] = "BLOCK"
    blocked["artifact_id"] = "quality-blocked"
    with pytest.raises(Exception, match="BLOCK"):
        M02.run_module({**inputs, "quality_report_phase_2": blocked}, CONFIG)


def test_handoff_ids_are_deterministic_and_hash_sensitive():
    inputs = base_inputs()
    report = M01.run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    first = M02.run_module({**inputs, "quality_report_phase_2": report}, CONFIG)["outputs"]
    second = M02.run_module({**inputs, "quality_report_phase_2": report}, CONFIG)["outputs"]
    assert first["phase3_handoff_manifest"]["handoff_id"] == second["phase3_handoff_manifest"]["handoff_id"]

    changed_inputs = base_inputs()
    changed_inputs["clean_document_panel"]["records"][0]["document_title"] = "Changed"
    changed_report = M01.run_module(changed_inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    third = M02.run_module({**changed_inputs, "quality_report_phase_2": changed_report}, CONFIG)["outputs"]
    assert first["phase3_handoff_manifest"]["handoff_id"] != third["phase3_handoff_manifest"]["handoff_id"]


def test_legacy_quality_report_without_status_remains_drop_in_compatible():
    inputs = base_inputs()
    legacy_report = artifact("quality_report_phase_2", [{"source_id": "s1"}])
    outputs = M02.run_module({**inputs, "quality_report_phase_2": legacy_report}, CONFIG)["outputs"]
    assert outputs["phase3_handoff_manifest"]["quality_status"] == "LEGACY_UNVERIFIED"

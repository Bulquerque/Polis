import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
CONFIG = {"pipeline_version": "V14.1-RC4.1", "created_at": "2024-01-01T00:00:00Z", "as_of_date": "2024-12-31"}


def mod(name):
    return importlib.import_module(f"quant_pipeline.phase_02_quality_pit.modules.{name}")


def handoff(hash_value="h1"):
    return {"records": [{"source_id": "s1", "source_name": "Source 1", "source_type": "api", "file_hash": hash_value, "readability_status": "readable", "declared_available_at": "2024-01-01T00:00:00Z", "available_at": "2024-01-01T00:00:00Z", "lineage_id": "l1"}]}


def test_p2_s1_validates_presence_hashes_and_quality_panel():
    bundle_inputs = {"handoff_manifest_to_phase_2": handoff(), "source_registry": {"records": [{"source_id": "s1"}]}, "raw_file_inventory": {"records": [{"source_id": "s1", "file_hash": "h1"}]}, "source_snapshot_registry": {"records": [{"source_id": "s1", "file_hash": "h1"}]}, "raw_readability_report": {"records": [{"source_id": "s1"}]}, "raw_schema_hint_report": {"records": [{"source_id": "s1"}]}, "ingestion_error_report": {"records": [{"source_id": "s1", "error_flag": False}]}}
    validated = mod("P2_S1_M01_phase1_handoff_validator").run_module(bundle_inputs, CONFIG)["outputs"]["validated_phase1_handoff_bundle"]
    assert validated["hashes_match"] is True, "hashes_match; all_phase1_outputs_present"
    read = mod("P2_S1_M02_raw_artifact_reader").run_module({"validated_phase1_handoff_bundle": validated}, CONFIG)["outputs"]["raw_artifact_read_bundle"]
    quality = mod("P2_S1_M03_source_quality_panel_builder").run_module({"validated_phase1_handoff_bundle": validated, "raw_readability_report": bundle_inputs["raw_readability_report"], "ingestion_error_report": bundle_inputs["ingestion_error_report"]}, CONFIG)["outputs"]["source_quality_panel"]
    assert read["lineage_preserved"] and quality["quality_score"] == 1.0, "lineage_preserved; readability_status_ok; source_quality_score_present; critical_source_flags_present"
    with pytest.raises(Exception, match="hashes_match"):
        mod("P2_S1_M01_phase1_handoff_validator").run_module({**bundle_inputs, "source_snapshot_registry": {"records": [{"source_id": "s1", "file_hash": "other"}]}}, CONFIG)


def test_p2_s2_normalizes_pit_and_rejects_future_or_synthetic_instruments():
    raw = {"records": [{"source_id": "s1", "underlying": "PETR4", "available_at": "2024-01-01T00:00:00Z", "lineage_id": "l1"}]}
    normalized = mod("P2_S2_M01_temporal_availability_normalizer").run_module({"raw_artifact_read_bundle": raw, "source_quality_panel": {"records": [{"source_id": "s1"}]}}, CONFIG)["outputs"]["pit_normalized_raw_bundle"]
    harmonized = mod("P2_S2_M02_identifier_key_harmonizer").run_module({"pit_normalized_raw_bundle": normalized}, CONFIG)["outputs"]["identifier_harmonized_bundle"]
    assert harmonized["contract_key_deterministic"] and harmonized["underlying"] == "PETR4", "contract_key_deterministic; no_future_availability; no_synthetic_instrument"
    with pytest.raises(Exception, match="no_future"):
        mod("P2_S2_M01_temporal_availability_normalizer").run_module({"raw_artifact_read_bundle": {"records": [{"source_id": "s1", "available_at": "2025-01-01T00:00:00Z"}]}, "source_quality_panel": {}}, CONFIG)
    with pytest.raises(Exception, match="synthetic"):
        mod("P2_S2_M02_identifier_key_harmonizer").run_module({"pit_normalized_raw_bundle": {"records": [{"source_id": "s1", "underlying": "synthetic-PETR4", "available_at": "2024-01-01"}]}}, CONFIG)


def test_p2_s3_panels_enforce_unique_dates_and_nonnegative_prices():
    base = {"records": [{"source_id": "s1", "underlying": "PETR4", "date": "2024-01-01", "available_at": "2024-01-01T00:00:00Z", "close": 10, "lineage_id": "l1"}]}
    quality = {"records": [{"source_id": "s1"}]}
    macro = mod("P2_S3_M01_macro_panel_cleaner").run_module({"identifier_harmonized_bundle": base, "source_quality_panel": quality}, CONFIG)
    benchmark = mod("P2_S3_M02_benchmark_panel_cleaner").run_module({"identifier_harmonized_bundle": base, "source_quality_panel": quality}, CONFIG)
    calendar = mod("P2_S3_M03_calendar_panel_builder").run_module({"identifier_harmonized_bundle": base, "source_quality_panel": quality}, CONFIG)
    actions = mod("P2_S3_M04_corporate_actions_cleaner").run_module({"identifier_harmonized_bundle": base, "source_quality_panel": quality, "clean_calendar_panel": calendar["outputs"]["clean_calendar_panel"]}, CONFIG)
    underlying = mod("P2_S3_M05_underlying_panel_cleaner").run_module({"identifier_harmonized_bundle": base, "source_quality_panel": quality, "clean_calendar_panel": calendar["outputs"]["clean_calendar_panel"], "clean_corporate_actions_panel": actions["outputs"]["clean_corporate_actions_panel"]}, CONFIG)
    trade = mod("P2_S3_M06_underlying_trade_panel_builder").run_module({"clean_underlying_panel": underlying["outputs"]["clean_underlying_panel"], "clean_calendar_panel": calendar["outputs"]["clean_calendar_panel"], "source_quality_panel": quality}, CONFIG)
    assert macro["outputs"]["clean_macro_br_panel"]["no_target_creation"] and benchmark["outputs"]["clean_benchmark_panel"]["benchmark_key_unique"], "macro_dates_pit; no_prediction; benchmark_key_unique; calendar_dates_unique; adjustment_factor_not_future; underlying_date_unique; corporate_actions_applied_pit"
    assert trade["outputs"]["clean_underlying_trade_panel"]["calendar_aligned"], "no_candidate_creation"
    with pytest.raises(Exception, match="price_non_negative"):
        mod("P2_S3_M05_underlying_panel_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "date": "2024-01-01", "available_at": "2024-01-01", "close": -1}]}, "source_quality_panel": quality, "clean_calendar_panel": calendar["outputs"]["clean_calendar_panel"], "clean_corporate_actions_panel": actions["outputs"]["clean_corporate_actions_panel"]}, CONFIG)


def test_p2_s4_option_contract_quotes_and_references():
    raw = {"records": [{"source_id": "s1", "option_id": "opt1", "underlying": "PETR4", "expiration_date": "2024-12-31", "strike": 30, "available_at": "2024-01-01T00:00:00Z", "lineage_id": "l1"}]}
    quality = {"records": [{"source_id": "s1"}]}
    calendar = {"artifact_id": "cal-1", "records": [{"source_id": "s1", "date": "2024-01-01"}]}
    contracts = mod("P2_S4_M01_option_contract_parser").run_module({"identifier_harmonized_bundle": raw, "clean_calendar_panel": calendar, "source_quality_panel": quality}, CONFIG)["outputs"]["clean_option_contract_panel"]
    quotes = mod("P2_S4_M02_option_quote_cleaner").run_module({"identifier_harmonized_bundle": raw, "clean_option_contract_panel": contracts, "source_quality_panel": quality}, CONFIG)["outputs"]["clean_option_quotes_panel"]
    refs = mod("P2_S4_M03_cost_liquidity_reference_builder").run_module({"clean_option_quotes_panel": quotes, "clean_underlying_panel": raw, "clean_underlying_trade_panel": raw, "source_quality_panel": quality}, CONFIG)
    assert contracts["contract_key_present"] and quotes["quote_has_contract_key"] and refs["outputs"]["clean_cost_reference_panel"]["cost_reference_present"], "option_id_present; expiration_date_present; strike_present; no_score; no_trade_decision"


def test_p2_s5_and_s6_produce_quality_and_explicit_handoffs():
    raw = {"records": [{"source_id": "s1", "document_type": "document", "available_at": "2024-01-01T00:00:00Z", "lineage_id": "l1"}]}
    quality = {"artifact_id": "quality-1", "records": [{"source_id": "s1"}]}
    cleaned = mod("P2_S5_M01_context_document_event_cleaner").run_module({"identifier_harmonized_bundle": raw, "source_quality_panel": quality}, CONFIG)["outputs"]
    assert "trade_signal" not in cleaned["clean_document_panel"], "no_trade_signal"
    inputs = {"source_quality_panel": quality, **cleaned}
    for name in ("clean_underlying_panel", "clean_underlying_trade_panel", "clean_macro_br_panel", "clean_macro_us_panel", "clean_benchmark_panel", "clean_calendar_panel", "clean_corporate_actions_panel", "clean_option_contract_panel", "clean_option_quotes_panel", "clean_cost_reference_panel", "clean_liquidity_reference_panel"):
        inputs[name] = {"artifact_id": name, "records": [{"source_id": "s1"}]}
    report = mod("P2_S6_M01_quality_report_phase2_builder").run_module(inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    handoffs = mod("P2_S6_M02_multi_phase_handoff_packager").run_module({**inputs, "quality_report_phase_2": report}, CONFIG)["outputs"]
    assert report["all_official_panels_covered"] and handoffs["phase3_handoff_manifest"]["no_hidden_bundle"], "quality_flags_summarized; handoff_manifest_references_existing_artifacts"


def test_P2_S1_M01_dedicated_handoff_oracle():
    inputs = {"handoff_manifest_to_phase_2": handoff(), "source_registry": {}, "raw_file_inventory": {}, "source_snapshot_registry": {"records": [{"source_id": "s1", "file_hash": "h1"}]}, "raw_readability_report": {}, "raw_schema_hint_report": {}, "ingestion_error_report": {}}
    result = mod("P2_S1_M01_phase1_handoff_validator").run_module(inputs, CONFIG)
    assert result["outputs"]["validated_phase1_handoff_bundle"]["hashes_match"]


def test_P2_S1_M02_dedicated_reader_oracle():
    result = mod("P2_S1_M02_raw_artifact_reader").run_module({"validated_phase1_handoff_bundle": handoff()}, CONFIG)
    assert result["outputs"]["raw_artifact_read_bundle"]["lineage_preserved"]


def test_P2_S1_M03_dedicated_quality_oracle():
    result = mod("P2_S1_M03_source_quality_panel_builder").run_module({"validated_phase1_handoff_bundle": handoff(), "raw_readability_report": {}, "ingestion_error_report": {"records": [{"source_id": "s1", "error_flag": False}]}}, CONFIG)
    assert result["outputs"]["source_quality_panel"]["quality_score"] == 1.0


def test_P2_S2_M01_dedicated_pit_oracle():
    result = mod("P2_S2_M01_temporal_availability_normalizer").run_module({"raw_artifact_read_bundle": {"records": [{"source_id": "s1", "available_at": "2024-01-01T00:00:00Z"}]}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["pit_normalized_raw_bundle"]["available_at_required"]


def test_P2_S2_M02_dedicated_key_oracle():
    result = mod("P2_S2_M02_identifier_key_harmonizer").run_module({"pit_normalized_raw_bundle": {"records": [{"source_id": "s1", "underlying": "PETR4", "available_at": "2024-01-01"}]}}, CONFIG)
    assert result["outputs"]["identifier_harmonized_bundle"]["contract_key_deterministic"]


def test_P2_S3_M01_dedicated_macro_oracle():
    result = mod("P2_S3_M01_macro_panel_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "available_at": "2024-01-01"}]}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_macro_br_panel"]["no_target_creation"]


def test_P2_S3_M02_dedicated_benchmark_oracle():
    result = mod("P2_S3_M02_benchmark_panel_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "date": "2024-01-01"}]}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_benchmark_panel"]["benchmark_key_unique"]


def test_P2_S3_M03_dedicated_calendar_oracle():
    result = mod("P2_S3_M03_calendar_panel_builder").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "date": "2024-01-01"}]}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_calendar_panel"]["trading_day_flag_present"]


def test_P2_S3_M04_dedicated_actions_oracle():
    result = mod("P2_S3_M04_corporate_actions_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "available_at": "2024-01-01"}]}, "source_quality_panel": {}, "clean_calendar_panel": {}}, CONFIG)
    assert result["outputs"]["clean_corporate_actions_panel"]["corporate_action_available_at_present"]


def test_P2_S3_M05_dedicated_underlying_oracle():
    result = mod("P2_S3_M05_underlying_panel_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "available_at": "2024-01-01", "close": 1}]}, "source_quality_panel": {}, "clean_calendar_panel": {}, "clean_corporate_actions_panel": {}}, CONFIG)
    assert result["outputs"]["clean_underlying_panel"]["price_non_negative"]


def test_P2_S3_M06_dedicated_trade_oracle():
    result = mod("P2_S3_M06_underlying_trade_panel_builder").run_module({"clean_underlying_panel": {"records": [{"source_id": "s1", "close": 1}]}, "clean_calendar_panel": {}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_underlying_trade_panel"]["tradable_price_present"]


def test_P2_S4_M01_dedicated_contract_oracle():
    result = mod("P2_S4_M01_option_contract_parser").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "option_id": "o1", "expiration_date": "2024-12-31", "strike": 1}]}, "clean_calendar_panel": {}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_option_contract_panel"]["contract_key_present"]


def test_P2_S4_M02_dedicated_quote_oracle():
    contracts = {"records": [{"contract_key": "k1"}]}
    result = mod("P2_S4_M02_option_quote_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "contract_key": "k1"}]}, "clean_option_contract_panel": contracts, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_option_quotes_panel"]["quote_has_contract_key"]


def test_P2_S4_M03_dedicated_reference_oracle():
    result = mod("P2_S4_M03_cost_liquidity_reference_builder").run_module({"clean_option_quotes_panel": {"records": [{"source_id": "s1", "bid": 1, "ask": 2, "volume": 3, "open_interest": 4}]}, "clean_underlying_panel": {}, "clean_underlying_trade_panel": {}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_liquidity_reference_panel"]["liquidity_reference_present"]


def test_P2_S5_M01_dedicated_context_oracle():
    result = mod("P2_S5_M01_context_document_event_cleaner").run_module({"identifier_harmonized_bundle": {"records": [{"source_id": "s1", "document_type": "document", "available_at": "2024-01-01"}]}, "source_quality_panel": {}}, CONFIG)
    assert result["outputs"]["clean_document_panel"]["document_available_at_present"]


def test_P2_S6_M01_dedicated_quality_report_oracle():
    names = ["source_quality_panel", "clean_context_source_panel", "clean_document_panel", "clean_event_reference_panel", "clean_underlying_panel", "clean_underlying_trade_panel", "clean_macro_br_panel", "clean_macro_us_panel", "clean_benchmark_panel", "clean_calendar_panel", "clean_corporate_actions_panel", "clean_option_contract_panel", "clean_option_quotes_panel", "clean_cost_reference_panel", "clean_liquidity_reference_panel"]
    inputs = {name: {"artifact_id": name, "records": [{"source_id": "s1"}]} for name in names}
    result = mod("P2_S6_M01_quality_report_phase2_builder").run_module(inputs, CONFIG)
    assert result["outputs"]["quality_report_phase_2"]["all_official_panels_covered"]


def test_P2_S6_M02_dedicated_handoff_oracle():
    names = ["clean_context_source_panel", "clean_document_panel", "clean_event_reference_panel", "source_quality_panel", "quality_report_phase_2", "clean_underlying_panel", "clean_underlying_trade_panel", "clean_macro_br_panel", "clean_macro_us_panel", "clean_benchmark_panel", "clean_calendar_panel", "clean_corporate_actions_panel", "clean_option_quotes_panel", "clean_option_contract_panel", "clean_cost_reference_panel", "clean_liquidity_reference_panel"]
    inputs = {name: {"artifact_id": name, "records": [{"source_id": "s1"}]} for name in names}
    result = mod("P2_S6_M02_multi_phase_handoff_packager").run_module(inputs, CONFIG)
    assert result["outputs"]["phase3_handoff_manifest"]["no_hidden_bundle"]


@pytest.mark.parametrize("module_name", [
    "P2_S1_M01_phase1_handoff_validator", "P2_S1_M02_raw_artifact_reader", "P2_S1_M03_source_quality_panel_builder",
    "P2_S2_M01_temporal_availability_normalizer", "P2_S2_M02_identifier_key_harmonizer", "P2_S3_M01_macro_panel_cleaner",
    "P2_S3_M02_benchmark_panel_cleaner", "P2_S3_M03_calendar_panel_builder", "P2_S3_M04_corporate_actions_cleaner",
    "P2_S3_M05_underlying_panel_cleaner", "P2_S3_M06_underlying_trade_panel_builder", "P2_S4_M01_option_contract_parser",
    "P2_S4_M02_option_quote_cleaner", "P2_S4_M03_cost_liquidity_reference_builder", "P2_S5_M01_context_document_event_cleaner",
    "P2_S6_M01_quality_report_phase2_builder", "P2_S6_M02_multi_phase_handoff_packager",
], ids=lambda value: value.split("_", 3)[0] + "_" + value.split("_", 3)[1] + "_" + value.split("_", 3)[2])
def test_P2_strict_negative_domain_oracle(module_name):
    module = mod(module_name)
    with pytest.raises(Exception):
        module.run_module({}, CONFIG)

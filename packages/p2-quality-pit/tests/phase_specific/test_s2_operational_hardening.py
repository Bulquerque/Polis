from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2026-07-23T12:50:00Z",
}


def mod(name: str):
    return importlib.import_module(f"quant_pipeline.phase_02_quality_pit.modules.{name}")


def run_s2(rows: list[dict], *, quality: dict | None = None, config: dict | None = None):
    cfg = {**CONFIG, **(config or {})}
    normalized = mod("P2_S2_M01_temporal_availability_normalizer").run_module(
        {
            "raw_artifact_read_bundle": {"records": rows},
            "source_quality_panel": quality or {},
        },
        cfg,
    )["outputs"]["pit_normalized_raw_bundle"]
    harmonized = mod("P2_S2_M02_identifier_key_harmonizer").run_module(
        {"pit_normalized_raw_bundle": normalized},
        cfg,
    )["outputs"]["identifier_harmonized_bundle"]
    return normalized, harmonized


def test_s2_normalizes_timezone_and_enforces_real_cutoff():
    row = {
        "source_id": "s1",
        "underlying": "PETR4",
        "close": 10,
        "available_at": "2024-01-01T10:00:00-03:00",
    }
    normalized, _ = run_s2(
        [row],
        config={"as_of_date": "2024-01-01T13:00:00Z", "strict_temporal_validation": True},
    )
    assert normalized["records"][0]["available_at"] == "2024-01-01T13:00:00Z"
    assert normalized["records"][0]["timezone"] == "UTC"

    with pytest.raises(Exception, match="no_future_availability"):
        run_s2(
            [row],
            config={"as_of_date": "2024-01-01T12:59:59Z", "strict_temporal_validation": True},
        )


def test_s2_keeps_reference_date_distinct_from_availability():
    row = {
        "source_id": "fred-cpi",
        "series_id": "CPIAUCSL",
        "value": 300,
        "source_reference_date": "2024-01-01",
        "declared_available_at": "2024-02-08T13:30:00Z",
    }
    normalized, harmonized = run_s2(
        [row],
        config={"as_of_date": "2024-02-08T13:30:00Z", "strict_temporal_validation": True},
    )
    output = normalized["records"][0]
    assert output["reference_date"] == "2024-01-01"
    assert output["available_at"] == "2024-02-08T13:30:00Z"
    assert harmonized["records"][0]["record_domain"] == "MACRO"

    with pytest.raises(Exception, match="no_future_availability"):
        run_s2(
            [row],
            config={"as_of_date": "2024-02-01T00:00:00Z", "strict_temporal_validation": True},
        )


def test_s2_strict_mode_rejects_naive_timestamp_without_timezone():
    row = {"source_id": "s1", "underlying": "PETR4", "close": 10, "available_at": "2024-01-01T10:00:00"}
    with pytest.raises(Exception, match="UNKNOWN_TIMEZONE"):
        run_s2([row], config={"strict_temporal_validation": True})


def test_s2_date_only_availability_is_conservative_in_compatibility_mode():
    normalized, _ = run_s2(
        [{"source_id": "s1", "underlying": "PETR4", "close": 10, "available_at": "2024-01-01"}],
        config={"as_of_date": "2024-01-01"},
    )
    row = normalized["records"][0]
    assert row["available_at"].startswith("2024-01-01T23:59:59.999999")
    assert row["temporal_precision"] == "DATE"
    assert row["timezone_assumed"] is True


def test_s2_uses_source_quality_without_inventing_missing_quality():
    quality = {
        "records": [{
            "source_id": "s1",
            "quality_score": 0.8,
            "quality_status": "WARN",
            "critical": False,
        }]
    }
    normalized, _ = run_s2(
        [{"source_id": "s1", "available_at": "2024-01-01T00:00:00Z"}],
        quality=quality,
    )
    row = normalized["records"][0]
    assert row["source_quality_score"] == 0.8
    assert row["source_quality_status"] == "WARN"

    normalized_missing, _ = run_s2(
        [{"source_id": "unknown", "available_at": "2024-01-01T00:00:00Z"}],
        quality=quality,
    )
    assert "source_quality_score" not in normalized_missing["records"][0]

    with pytest.raises(Exception, match="SOURCE_QUALITY_MISSING"):
        run_s2(
            [{"source_id": "unknown", "available_at": "2024-01-01T00:00:00Z"}],
            quality=quality,
            config={"strict_source_quality": True},
        )


def test_same_option_multiple_quotes_share_contract_key_but_not_observation_key():
    rows = [
        {
            "source_id": "opt-provider",
            "option_id": "PETR4C30-20240920",
            "underlying": "PETR4",
            "expiration_date": "2024-09-20",
            "option_type": "CALL",
            "strike": "30.0",
            "bid": 1.0,
            "ask": 1.1,
            "available_at": "2024-06-01T10:00:00Z",
        },
        {
            "source_id": "opt-provider",
            "option_id": "PETR4C30-20240920",
            "underlying": "PETR4",
            "expiration_date": "2024-09-20",
            "option_type": "C",
            "strike": "30.000",
            "bid": 1.1,
            "ask": 1.2,
            "available_at": "2024-06-01T11:00:00Z",
        },
    ]
    _, harmonized = run_s2(rows)
    first, second = harmonized["records"]
    assert first["record_domain"] == second["record_domain"] == "OPTION_QUOTE"
    assert first["contract_key"] == second["contract_key"]
    assert first["canonical_contract_key"] == second["canonical_contract_key"]
    assert first["observation_key"] != second["observation_key"]
    assert first["strike_normalized"] == second["strike_normalized"] == "30"


def test_option_public_contract_key_remains_compatible_with_current_s4():
    rows = [{
        "source_id": "opt-provider",
        "option_id": "OPT-1",
        "underlying": "PETR4",
        "expiration_date": "2024-12-31",
        "option_type": "call",
        "strike": 30,
        "bid": 1,
        "ask": 2,
        "available_at": "2024-06-01T10:00:00Z",
    }]
    _, harmonized = run_s2(rows)
    public_key = harmonized["records"][0]["contract_key"]

    contracts = mod("P2_S4_M01_option_contract_parser").run_module(
        {
            "identifier_harmonized_bundle": harmonized,
            "clean_calendar_panel": {},
            "source_quality_panel": {},
        },
        CONFIG,
    )["outputs"]["clean_option_contract_panel"]
    assert contracts["records"][0]["contract_key"] == public_key

    quotes = mod("P2_S4_M02_option_quote_cleaner").run_module(
        {
            "identifier_harmonized_bundle": harmonized,
            "clean_option_contract_panel": contracts,
            "source_quality_panel": {},
        },
        CONFIG,
    )["outputs"]["clean_option_quotes_panel"]
    assert quotes["quote_has_contract_key"] is True


def test_s2_does_not_turn_source_id_into_underlying_for_non_instrument_record():
    _, harmonized = run_s2([
        {
            "source_id": "context-provider",
            "document_type": "document",
            "document_id": "doc-1",
            "available_at": "2024-01-01T00:00:00Z",
        }
    ])
    row = harmonized["records"][0]
    assert row["record_domain"] == "DOCUMENT"
    assert "underlying" not in row
    assert row["identity_key_type"] == "RECORD"


def test_s2_unknown_domain_survives_without_false_classification():
    _, harmonized = run_s2([
        {"source_id": "mystery", "foo": "bar", "available_at": "2024-01-01T00:00:00Z"}
    ])
    row = harmonized["records"][0]
    assert row["record_domain"] == "UNKNOWN"
    assert harmonized["unknown_domain_count"] == 1


def test_s2_rejects_legacy_option_key_collision_between_different_canonical_contracts():
    rows = [
        {
            "source_id": "opt-provider",
            "option_id": "BROKEN-ID",
            "underlying": "PETR4",
            "expiration_date": "2024-09-20",
            "option_type": "C",
            "strike": 30,
            "bid": 1,
            "available_at": "2024-06-01T10:00:00Z",
        },
        {
            "source_id": "opt-provider",
            "option_id": "BROKEN-ID",
            "underlying": "PETR4",
            "expiration_date": "2024-09-20",
            "option_type": "C",
            "strike": 31,
            "bid": 1,
            "available_at": "2024-06-01T11:00:00Z",
        },
    ]
    with pytest.raises(Exception, match="LEGACY_CONTRACT_KEY_COLLISION"):
        run_s2(rows)


def test_s1_physical_provenance_flows_into_s2_observation_keys(tmp_path: Path):
    path = tmp_path / "quotes.csv"
    path.write_text(
        "option_id,underlying,expiration_date,option_type,strike,bid,ask,available_at\n"
        "OPT-1,PETR4,2024-12-31,C,30,1.0,1.1,2024-06-01T10:00:00Z\n"
        "OPT-1,PETR4,2024-12-31,C,30,1.1,1.2,2024-06-01T11:00:00Z\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptor = {
        "handoff_artifact_id": "handoff-1",
        "ingestion_run_id": "run-1",
        "source_id": "opt-provider",
        "source_name": "Option Provider",
        "source_type": "file",
        "raw_artifact_id": "raw-options-1",
        "raw_artifact_path": str(path),
        "file_hash": digest,
        "file_size_bytes": path.stat().st_size,
        "ingested_at": "2024-06-01T12:00:00Z",
        "declared_available_at": "2024-06-01T12:00:00Z",
        "readability_status": "readable",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": "lineage-1",
    }
    p1_inputs = {
        "handoff_manifest_to_phase_2": {"records": [descriptor]},
        "source_registry": {"records": [{"source_id": "opt-provider"}]},
        "raw_file_inventory": {"records": [descriptor]},
        "source_snapshot_registry": {"records": [descriptor]},
        "raw_readability_report": {"records": [{"source_id": "opt-provider", "readability_status": "readable"}]},
        "raw_schema_hint_report": {},
        "ingestion_error_report": {"records": [{"source_id": "opt-provider", "error_flag": False}]},
    }
    cfg = {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True}
    validated = mod("P2_S1_M01_phase1_handoff_validator").run_module(p1_inputs, cfg)["outputs"]["validated_phase1_handoff_bundle"]
    raw = mod("P2_S1_M02_raw_artifact_reader").run_module(
        {"validated_phase1_handoff_bundle": validated}, cfg
    )["outputs"]["raw_artifact_read_bundle"]
    quality = mod("P2_S1_M03_source_quality_panel_builder").run_module(
        {
            "validated_phase1_handoff_bundle": validated,
            "raw_readability_report": p1_inputs["raw_readability_report"],
            "ingestion_error_report": p1_inputs["ingestion_error_report"],
        },
        cfg,
    )["outputs"]["source_quality_panel"]

    normalized = mod("P2_S2_M01_temporal_availability_normalizer").run_module(
        {"raw_artifact_read_bundle": raw, "source_quality_panel": quality}, cfg
    )["outputs"]["pit_normalized_raw_bundle"]
    harmonized = mod("P2_S2_M02_identifier_key_harmonizer").run_module(
        {"pit_normalized_raw_bundle": normalized}, cfg
    )["outputs"]["identifier_harmonized_bundle"]

    first, second = harmonized["records"]
    assert first["observation_key_mode"] == second["observation_key_mode"] == "PHYSICAL_PROVENANCE"
    assert first["observation_key"] != second["observation_key"]
    assert first["contract_key"] == second["contract_key"]
    assert first["_provenance"]["physical_hash_verified"] is True


def test_s2_outputs_remain_structurally_accepted_by_s3_and_s5_consumers():
    quality = {"records": [{"source_id": "s1", "quality_score": 1.0, "quality_status": "PASS"}]}

    _, macro_bundle = run_s2([{
        "source_id": "s1", "series_id": "IPCA", "value": 1.0, "region": "BR",
        "available_at": "2024-01-01T00:00:00Z",
    }], quality=quality)
    macro = mod("P2_S3_M01_macro_panel_cleaner").run_module(
        {"identifier_harmonized_bundle": macro_bundle, "source_quality_panel": quality}, CONFIG
    )
    assert macro["outputs"]["clean_macro_br_panel"]["records"]

    _, benchmark_bundle = run_s2([{
        "source_id": "s1", "benchmark_id": "IBOV", "date": "2024-01-01",
        "available_at": "2024-01-01T00:00:00Z",
    }], quality=quality)
    benchmark = mod("P2_S3_M02_benchmark_panel_cleaner").run_module(
        {"identifier_harmonized_bundle": benchmark_bundle, "source_quality_panel": quality}, CONFIG
    )
    assert benchmark["outputs"]["clean_benchmark_panel"]["records"]

    _, calendar_bundle = run_s2([{
        "source_id": "s1", "date": "2024-01-01", "is_trading_day": True,
        "available_at": "2024-01-01T00:00:00Z",
    }], quality=quality)
    calendar = mod("P2_S3_M03_calendar_panel_builder").run_module(
        {"identifier_harmonized_bundle": calendar_bundle, "source_quality_panel": quality}, CONFIG
    )["outputs"]["clean_calendar_panel"]
    assert calendar["records"]

    _, action_bundle = run_s2([{
        "source_id": "s1", "action_type": "split", "effective_date": "2024-01-01",
        "adjustment_factor": 2.0, "available_at": "2024-01-01T23:59:59.999999Z",
    }], quality=quality)
    actions = mod("P2_S3_M04_corporate_actions_cleaner").run_module(
        {
            "identifier_harmonized_bundle": action_bundle,
            "source_quality_panel": quality,
            "clean_calendar_panel": calendar,
        }, CONFIG
    )
    assert actions["outputs"]["clean_corporate_actions_panel"]["records"]

    _, underlying_bundle = run_s2([{
        "source_id": "s1", "underlying": "PETR4", "date": "2024-01-01", "close": 10,
        "available_at": "2024-01-01T23:59:59.999999Z",
    }], quality=quality)
    underlying = mod("P2_S3_M05_underlying_panel_cleaner").run_module(
        {
            "identifier_harmonized_bundle": underlying_bundle,
            "source_quality_panel": quality,
            "clean_calendar_panel": calendar,
            "clean_corporate_actions_panel": actions["outputs"]["clean_corporate_actions_panel"],
        }, CONFIG
    )
    assert underlying["outputs"]["clean_underlying_panel"]["records"][0]["underlying"] == "PETR4"

    _, document_bundle = run_s2([{
        "source_id": "s1", "document_type": "document", "document_id": "doc-1",
        "document_title": "Doc", "document_text_or_path": "text",
        "available_at": "2024-01-01T00:00:00Z",
    }], quality=quality)
    context = mod("P2_S5_M01_context_document_event_cleaner").run_module(
        {"identifier_harmonized_bundle": document_bundle, "source_quality_panel": quality}, CONFIG
    )
    assert context["outputs"]["clean_document_panel"]["records"]


def test_s2_rejects_retrieved_before_available():
    from quant_pipeline.phase_02_quality_pit.modules.P2_S2_M01_temporal_availability_normalizer import run_module
    with pytest.raises(Exception, match="RETRIEVED_BEFORE_AVAILABLE"):
        run_module(
            {
                "raw_artifact_read_bundle": {"records": [{
                    "source_id": "s1",
                    "available_at": "2026-01-02T00:00:00Z",
                    "retrieved_at": "2026-01-01T00:00:00Z",
                }]},
                "source_quality_panel": {"records": [{"source_id": "s1", "quality_status": "PASS"}]},
            },
            {**CONFIG, "strict_temporal_validation": True},
        )

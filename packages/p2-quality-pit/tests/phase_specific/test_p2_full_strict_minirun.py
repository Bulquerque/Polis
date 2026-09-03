from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quant_pipeline.phase_02_quality_pit.runner import run_phase
from quant_pipeline.phase_02_quality_pit.profiles import strict_production_config


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_p2_strict_physical_minirun_keeps_daily_cutoff_causal(tmp_path: Path):
    raw_path = tmp_path / "p2_full.jsonl"
    rows = [
        {
            "record_domain": "UNDERLYING",
            "source_id": "source-1",
            "underlying": "PETR4",
            "market": "B3",
            "exchange": "B3",
            "asset_class": "EQUITY",
            "currency": "BRL",
            "calendar_id": "B3",
            "date": "2026-07-22",
            "available_at": "2026-07-22T21:00:00Z",
            "open": 30.0,
            "high": 32.0,
            "low": 29.5,
            "close": 31.5,
            "volume": 1_000_000,
            "financial_volume": 31_500_000,
            "price_adjustment_policy": "RAW",
            "lineage_id": "l-under",
        },
        {
            "record_domain": "CALENDAR",
            "source_id": "source-1",
            "calendar_id": "B3",
            "market": "B3",
            "exchange": "B3",
            "date": "2026-07-22",
            "available_at": "2026-07-01T00:00:00Z",
            "is_trading_day": True,
            "lineage_id": "l-cal",
        },
        {
            "record_domain": "CORPORATE_ACTION",
            "source_id": "source-1",
            "underlying": "PETR4",
            "action_type": "SPLIT",
            "available_at": "2026-07-01T12:00:00Z",
            "effective_date": "2026-08-01",
            "adjustment_factor": 0.5,
            "lineage_id": "l-ca",
        },
        {"record_domain": "MACRO", "source_id": "source-1", "series_id": "SELIC", "country": "BR", "region": "BR", "reference_date": "2026-07-01", "available_at": "2026-07-01T12:00:00Z", "value": 15.0, "unit": "pct", "frequency": "monthly", "lineage_id": "l-macro-br"},
        {"record_domain": "MACRO", "source_id": "source-1", "series_id": "FEDFUNDS", "country": "US", "region": "US", "reference_date": "2026-07-01", "available_at": "2026-07-01T12:00:00Z", "value": 4.5, "unit": "pct", "frequency": "monthly", "lineage_id": "l-macro-us"},
        {"record_domain": "BENCHMARK", "source_id": "source-1", "benchmark_id": "IBOV", "date": "2026-07-22", "available_at": "2026-07-22T21:00:00Z", "value": 130000.0, "currency": "BRL", "lineage_id": "l-bench"},
        {"record_domain": "OPTION_CONTRACT", "source_id": "source-1", "option_id": "PETR4C320", "underlying": "PETR4", "market": "B3", "exchange": "B3", "expiration_date": "2026-08-21", "strike": 32.0, "option_type": "CALL", "contract_size": 100, "available_at": "2026-07-22T10:00:00Z", "lineage_id": "l-opt-contract"},
        {"record_domain": "OPTION_QUOTE", "source_id": "source-1", "option_id": "PETR4C320", "underlying": "PETR4", "market": "B3", "exchange": "B3", "expiration_date": "2026-08-21", "strike": 32.0, "option_type": "CALL", "date": "2026-07-22", "available_at": "2026-07-22T20:59:00Z", "as_of_date": "2026-07-22T21:00:00Z", "bid": 1.1, "ask": 1.3, "last_price": 1.2, "volume": 1000, "open_interest": 5000, "lineage_id": "l-opt-quote"},
        {"record_domain": "CONTEXT", "source_id": "source-1", "source_name": "Integrated Source", "source_type": "market_and_context", "available_at": "2026-07-22T09:00:00Z", "lineage_id": "l-context"},
        {"record_domain": "DOCUMENT", "source_id": "source-1", "source_name": "Integrated Source", "source_type": "news", "document_id": "doc-1", "document_type": "news", "document_title": "PETR4 update", "document_text_or_path": "Petrobras operational update.", "reference_date": "2026-07-22", "available_at": "2026-07-22T10:00:00Z", "ingested_at": "2026-07-22T10:01:00Z", "language": "pt-BR", "lineage_id": "l-doc"},
        {"record_domain": "EVENT", "source_id": "source-1", "source_name": "Integrated Source", "source_type": "news", "event_id": "event-1", "event_type": "earnings_event", "event_name": "PETR4 earnings", "reference_date": "2026-07-22", "available_at": "2026-07-22T11:00:00Z", "lineage_id": "l-event"},
    ]
    raw_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    digest = _sha256(raw_path)
    size = raw_path.stat().st_size
    handoff = {
        "handoff_artifact_id": "handoff-1",
        "ingestion_run_id": "run-1",
        "source_id": "source-1",
        "source_name": "Integrated Source",
        "source_type": "file",
        "source_category": "mixed",
        "raw_artifact_id": "raw-1",
        "raw_artifact_path": str(raw_path),
        "file_hash": digest,
        "file_size_bytes": size,
        "ingested_at": "2026-07-23T11:00:00Z",
        "source_reference_date": "2026-07-22",
        "declared_available_at": "2026-07-23T10:59:00Z",
        "readability_status": "readable",
        "schema_hint_id": "hint-1",
        "error_flag": False,
        "warning_flag": False,
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": "lineage-1",
        "format": "jsonl",
    }
    inputs = {
        "handoff_manifest_to_phase_2": {"records": [handoff]},
        "source_registry": {"records": [{"source_id": "source-1", "artifact_id": "registry-1"}]},
        "raw_file_inventory": {"records": [{"source_id": "source-1", "raw_artifact_id": "raw-1", "raw_artifact_path": str(raw_path), "file_hash": digest, "file_size_bytes": size, "format": "jsonl"}]},
        "source_snapshot_registry": {"records": [{**handoff, "artifact_id": "snapshot-1", "created_at": "2026-07-23T11:00:00Z"}]},
        "raw_readability_report": {"records": [{"source_id": "source-1", "raw_artifact_id": "raw-1", "readability_status": "readable"}]},
        "raw_schema_hint_report": {"records": [{"schema_hint_id": "hint-1"}]},
        "ingestion_error_report": {"records": [{"source_id": "source-1", "ingestion_run_id": "run-1", "error_flag": False, "is_blocking": False, "error_severity": "none", "error_code": "NO_ERROR", "error_message": "none"}]},
    }
    config = strict_production_config({
        "pipeline_version": "V14.1-RC4.1",
        "created_at": "2026-07-23T13:45:00Z",
        "as_of_date": "2026-07-23T23:59:59Z",
        "artifact_root": str(tmp_path),
        "allowed_roots": [str(tmp_path)],
        "expected_domains": ["market", "options", "context"],
    })

    result = run_phase(inputs, config)

    assert len(result["module_results"]) == 17
    assert len(result["phase_outputs"]) == 20
    quality = result["phase_outputs"]["quality_report_phase_2"]
    assert quality["status"] in {"PASS", "WARN"}
    assert quality["target_readiness"]["phase_03_agents_rag_memory"]["status"] in {"PASS", "WARN"}
    assert quality["target_readiness"]["phase_04_feature_base"]["status"] in {"PASS", "WARN"}
    assert quality["target_readiness"]["phase_06_candidate_generation"]["status"] in {"PASS", "WARN"}
    assert not any(issue["code"] == "P2Q_FUTURE_DATA" for issue in quality["blocking_issues"])
    assert result["phase_outputs"]["clean_underlying_panel"]["records"][0]["as_of_date"] == "2026-07-22T21:00:00Z"

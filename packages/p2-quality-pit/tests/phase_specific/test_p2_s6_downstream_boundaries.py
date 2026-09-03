from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
P2_ROOT = ROOT / "phase_02_extracted" / "phase_02_quality_pit_agent_package_RC4_1"
P3_ROOT = ROOT / "phase_03_extracted" / "phase_03_agents_rag_memory_agent_package_RC4_1"
P4_ROOT = ROOT / "phase_04_extracted" / "phase_04_feature_base_agent_package_RC4_1"
P6_ROOT = ROOT / "phase_06_extracted" / "phase_06_candidate_generation_agent_package_RC4_1"
for root in (P2_ROOT, P3_ROOT, P4_ROOT, P6_ROOT):
    sys.path.insert(0, str(root / "src"))

M01 = importlib.import_module(
    "quant_pipeline.phase_02_quality_pit.modules.P2_S6_M01_quality_report_phase2_builder"
)
M02 = importlib.import_module(
    "quant_pipeline.phase_02_quality_pit.modules.P2_S6_M02_multi_phase_handoff_packager"
)
P3 = importlib.import_module(
    "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M01_phase2_handoff_contract_validator"
)
P4 = importlib.import_module(
    "quant_pipeline.phase_04_feature_base.modules.P4_S1_M01_phase2_feature_intake_validator"
)
P6_OPTIONS = importlib.import_module(
    "quant_pipeline.phase_06_candidate_generation.modules.P6_S1_M02_option_market_input_loader"
)
P6_UNDERLYING = importlib.import_module(
    "quant_pipeline.phase_06_candidate_generation.modules.P6_S1_M03_underlying_market_input_loader"
)

CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2024-06-01T00:00:00Z",
    "as_of_date": "2024-06-01T23:59:59Z",
}


def artifact(name: str, rows: list[dict]) -> dict:
    return {
        "artifact_id": f"{name}-1",
        "created_at": CONFIG["created_at"],
        "lineage_id": f"lineage-{name}",
        "pipeline_version": CONFIG["pipeline_version"],
        "records": rows,
    }


def inputs() -> dict:
    source_quality = artifact("source_quality_panel", [{
        "source_id": "s1", "source_name": "Source 1", "source_type": "api",
        "quality_score": 0.9, "readability_status": "readable",
        "error_flag": False, "warning_flag": False,
        "declared_available_at": "2024-05-31T10:00:00Z", "lineage_id": "lineage-s1",
    }])
    context = artifact("clean_context_source_panel", [{"source_id": "s1", "available_at": "2024-05-31T10:00:00Z"}])
    documents = artifact("clean_document_panel", [{
        "document_id": "d1", "source_id": "s1", "source_name": "Source 1",
        "document_type": "news", "document_title": "Document 1",
        "document_text_or_path": "Document body", "reference_date": "2024-05-31",
        "available_at": "2024-05-31T10:00:00Z", "ingested_at": "2024-05-31T10:00:01Z",
        "source_quality_score": 0.9, "language": "en", "cleaning_status": "CLEAN",
        "lineage_id": "lineage-d1",
    }])
    events = artifact("clean_event_reference_panel", [{"event_id": "e1", "source_id": "s1", "available_at": "2024-05-31T10:00:00Z"}])
    underlying = artifact("clean_underlying_panel", [{"underlying": "PETR4", "date": "2024-05-31", "available_at": "2024-05-31T20:00:00Z"}])
    trade = artifact("clean_underlying_trade_panel", [{"underlying": "PETR4", "date": "2024-05-31", "available_at": "2024-05-31T20:00:00Z"}])
    calendar = artifact("clean_calendar_panel", [{"date": "2024-05-31", "is_trading_day": True}])
    contract = artifact("clean_option_contract_panel", [{"contract_key": "k1", "option_id": "o1"}])
    quote = artifact("clean_option_quotes_panel", [{"contract_key": "k1", "date": "2024-05-31", "available_at": "2024-05-31T20:00:00Z"}])
    return {
        "source_quality_panel": source_quality,
        "clean_context_source_panel": context,
        "clean_document_panel": documents,
        "clean_event_reference_panel": events,
        "clean_underlying_panel": underlying,
        "clean_underlying_trade_panel": trade,
        "clean_macro_br_panel": artifact("clean_macro_br_panel", [{"available_at": "2024-05-31T10:00:00Z"}]),
        "clean_macro_us_panel": artifact("clean_macro_us_panel", [{"available_at": "2024-05-31T10:00:00Z"}]),
        "clean_benchmark_panel": artifact("clean_benchmark_panel", [{"available_at": "2024-05-31T20:00:00Z"}]),
        "clean_calendar_panel": calendar,
        "clean_corporate_actions_panel": artifact("clean_corporate_actions_panel", []),
        "clean_option_contract_panel": contract,
        "clean_option_quotes_panel": quote,
        "clean_cost_reference_panel": artifact("clean_cost_reference_panel", [{"contract_key": "k1"}]),
        "clean_liquidity_reference_panel": artifact("clean_liquidity_reference_panel", [{"contract_key": "k1"}]),
    }


def test_s6_outputs_are_directly_accepted_by_p3_p4_and_p6():
    phase2_inputs = inputs()
    report = M01.run_module(phase2_inputs, CONFIG)["outputs"]["quality_report_phase_2"]
    handoffs = M02.run_module(
        {**phase2_inputs, "quality_report_phase_2": report}, CONFIG
    )["outputs"]

    p3_result = P3.run_module(
        {
            "clean_context_source_panel": phase2_inputs["clean_context_source_panel"],
            "clean_document_panel": phase2_inputs["clean_document_panel"],
            "clean_event_reference_panel": phase2_inputs["clean_event_reference_panel"],
            "source_quality_panel": phase2_inputs["source_quality_panel"],
            "context_handoff_manifest": handoffs["context_handoff_manifest"],
            "phase3_handoff_manifest": handoffs["phase3_handoff_manifest"],
        },
        CONFIG,
    )
    assert p3_result["outputs"]["validated_phase2_handoff"]["validation_status"] == "READY"

    p4_result = P4.run_module(
        {
            "clean_underlying_panel": phase2_inputs["clean_underlying_panel"],
            "clean_macro_br_panel": phase2_inputs["clean_macro_br_panel"],
            "clean_macro_us_panel": phase2_inputs["clean_macro_us_panel"],
            "clean_benchmark_panel": phase2_inputs["clean_benchmark_panel"],
            "clean_calendar_panel": phase2_inputs["clean_calendar_panel"],
            "clean_corporate_actions_panel": phase2_inputs["clean_corporate_actions_panel"],
            "quality_report_phase_2": report,
            "phase4_handoff_manifest": handoffs["phase4_handoff_manifest"],
        },
        CONFIG,
    )
    assert p4_result["outputs"]["validated_phase2_feature_inputs"]["available_at_preserved"]

    p6_options = P6_OPTIONS.run_module(
        {
            "clean_option_quotes_panel": phase2_inputs["clean_option_quotes_panel"],
            "clean_option_contract_panel": phase2_inputs["clean_option_contract_panel"],
            "clean_calendar_panel": phase2_inputs["clean_calendar_panel"],
            "clean_cost_reference_panel": phase2_inputs["clean_cost_reference_panel"],
            "clean_liquidity_reference_panel": phase2_inputs["clean_liquidity_reference_panel"],
            "phase6_handoff_manifest": handoffs["phase6_handoff_manifest"],
        },
        CONFIG,
    )
    assert p6_options["outputs"]["validated_option_market_inputs"]["phase6_manifest_valid"]

    p6_underlying = P6_UNDERLYING.run_module(
        {
            "clean_underlying_trade_panel": phase2_inputs["clean_underlying_trade_panel"],
            "clean_calendar_panel": phase2_inputs["clean_calendar_panel"],
            "clean_cost_reference_panel": phase2_inputs["clean_cost_reference_panel"],
            "clean_liquidity_reference_panel": phase2_inputs["clean_liquidity_reference_panel"],
            "phase6_handoff_manifest": handoffs["phase6_handoff_manifest"],
        },
        CONFIG,
    )
    assert p6_underlying["outputs"]["validated_underlying_market_inputs"]["phase6_manifest_valid"]

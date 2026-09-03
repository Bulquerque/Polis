from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from typing import Any

from .support import build_m01, build_m02, build_m03, build_m04, load_yaml
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s33 import (
    build_entity_resolution_boundary,
    build_phase1_custody_boundary,
    build_phase2_view_boundary,
    build_research_data_boundary_bundle,
    build_temporal_firewall,
)

DECISION_TIME = "2024-01-15T12:00:00Z"


def digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def panel(name: str, rows: list[dict[str, Any]], *, source: str | None = None) -> dict[str, Any]:
    enriched = []
    for index, row in enumerate(rows):
        item = {
            "record_id": f"{name}-{index}",
            "available_at": "2024-01-10T12:00:00Z",
            "lineage_id": f"lineage-{name}",
            **row,
        }
        if source and "source_id" not in item:
            item["source_id"] = source
        enriched.append(item)
    return {
        "artifact_id": f"artifact-{name}",
        "schema_version": "v14.1-rc4.1",
        "lineage_id": f"lineage-{name}",
        "content_hash": digest(name),
        "records": enriched,
    }


@lru_cache(maxsize=1)
def s32_outputs_cached() -> dict[str, Any]:
    m01 = build_m01()
    m02 = build_m02(m01)
    m03 = build_m03(m01)
    m04 = build_m04(m01, m02, m03)
    return {**m01, **m02, **m03, **m04}


def s32_outputs() -> dict[str, Any]:
    return deepcopy(s32_outputs_cached())


def p2_inputs() -> dict[str, Any]:
    inputs = {
        "quality_report_phase_2": {
            "artifact_id": "quality-p2",
            "status": "PASS",
            "created_at": "2024-01-11T00:00:00Z",
            "lineage_id": "lineage-quality-p2",
            "pipeline_version": "V14.1-RC4.1",
        },
        "clean_context_source_panel": panel("clean_context_source_panel", [{"context_id": "ctx-1"}], source="fred"),
        "clean_document_panel": panel("clean_document_panel", [{"document_id": "doc-1", "entity_id": "PETROBRAS", "company_name": "Petrobras", "ticker": "PETR4"}], source="sec"),
        "clean_event_reference_panel": panel("clean_event_reference_panel", [{"event_id": "event-1", "entity_id": "PETROBRAS", "entity_name": "Petrobras"}], source="sec"),
        "source_quality_panel": panel("source_quality_panel", [{"source_id": "fred", "quality_score": 0.95}], source="fred"),
        "clean_underlying_panel": panel("clean_underlying_panel", [{"date": "2024-01-10", "underlying": "PETR4", "entity_id": "PETROBRAS", "instrument_id": "BRPETRACNPR6", "ticker": "PETR4", "venue": "B3", "close": 38.5}], source="b3"),
        "clean_underlying_trade_panel": panel("clean_underlying_trade_panel", [{"trade_id": "trade-1", "underlying": "PETR4", "price": 38.5}], source="b3"),
        "clean_benchmark_panel": panel("clean_benchmark_panel", [{"benchmark_id": "IBOV", "date": "2024-01-10", "close": 130000}], source="b3"),
        "clean_calendar_panel": panel("clean_calendar_panel", [{"calendar_id": "B3", "date": "2024-01-10", "is_business_day": True}], source="b3"),
        "clean_corporate_actions_panel": panel("clean_corporate_actions_panel", [{"action_id": "div-1", "underlying": "PETR4", "entity_id": "PETROBRAS", "announcement_date": "2024-01-05", "action_type": "DIVIDEND"}], source="b3"),
        "clean_macro_br_panel": panel("clean_macro_br_panel", [{"series_id": "BR_SELIC", "reference_date": "2024-01-01", "value": 11.75}], source="fred"),
        "clean_macro_us_panel": panel("clean_macro_us_panel", [{"series_id": "US_CPI", "reference_date": "2023-12-01", "value": 3.4}], source="fred"),
        "clean_option_contract_panel": panel("clean_option_contract_panel", [{"contract_id": "PETRA400", "underlying": "PETR4", "underlying_instrument_id": "BRPETRACNPR6", "instrument_id": "PETRA400", "ticker": "PETRA400", "venue": "B3", "expiration_date": "2024-02-16", "instrument_type": "OPTION_CONTRACT"}], source="b3"),
        "clean_option_quotes_panel": panel("clean_option_quotes_panel", [{"contract_id": "PETRA400", "bid": 1.0, "ask": 1.2}], source="b3"),
        "clean_cost_reference_panel": panel("clean_cost_reference_panel", [{"cost_id": "cost-b3", "underlying": "PETR4", "fee_bps": 2.0}], source="b3"),
        "clean_liquidity_reference_panel": panel("clean_liquidity_reference_panel", [{"underlying": "PETR4", "turnover": 1000000}], source="b3"),
    }
    phase3_names = ["clean_context_source_panel", "clean_document_panel", "clean_event_reference_panel", "source_quality_panel"]
    phase4_names = ["clean_underlying_panel", "clean_macro_br_panel", "clean_macro_us_panel", "clean_benchmark_panel", "clean_calendar_panel", "clean_corporate_actions_panel"]
    phase6_names = ["clean_option_quotes_panel", "clean_option_contract_panel", "clean_underlying_trade_panel", "clean_calendar_panel", "clean_cost_reference_panel", "clean_liquidity_reference_panel"]
    def handoff(target: str, names: list[str]) -> dict[str, Any]:
        return {
            "handoff_id": f"handoff-{target}",
            "target_phase": target,
            "artifact_refs": [
                {
                    "artifact_name": name,
                    "artifact_id": inputs[name]["artifact_id"],
                    "schema_version": inputs[name]["schema_version"],
                    "content_hash": inputs[name]["content_hash"],
                    "lineage_id": inputs[name]["lineage_id"],
                }
                for name in names
            ],
        }
    inputs["phase3_handoff_manifest"] = handoff("phase_03_agents_rag_memory", phase3_names)
    inputs["phase4_handoff_manifest"] = handoff("phase_04_feature_base", phase4_names)
    inputs["phase6_handoff_manifest"] = handoff("phase_06_candidate_generation", phase6_names)
    return inputs


def p1_inputs() -> dict[str, Any]:
    sources = ("sec", "fred", "b3")
    snapshots = []
    inventory = []
    readability = []
    schema_hints = []
    for source in sources:
        raw_id = f"raw-{source}"
        file_hash = digest(raw_id)
        snapshots.append({
            "source_id": source,
            "ingestion_run_id": "ingestion-2024-01-10",
            "raw_artifact_id": raw_id,
            "raw_artifact_path": f"raw/{source}/snapshot.json",
            "file_hash": file_hash,
            "file_size_bytes": 128,
            "ingested_at": "2024-01-10T10:00:00Z",
            "declared_available_at": "2024-01-10T09:00:00Z",
            "readability_status": "READABLE",
        })
        inventory.append({"raw_artifact_id": raw_id, "file_hash": file_hash, "file_size_bytes": 128})
        readability.append({"raw_artifact_id": raw_id, "readability_status": "READABLE"})
        schema_hints.append({"raw_artifact_id": raw_id, "schema_fingerprint": digest(f"schema-{source}")})
    return {
        "handoff_manifest_to_phase_2": {"artifact_ids": [f"raw-{source}" for source in sources]},
        "source_registry": {"records": [{"source_id": source} for source in sources]},
        "raw_file_inventory": {"records": inventory},
        "source_snapshot_registry": {"records": snapshots},
        "raw_readability_report": {"records": readability},
        "raw_schema_hint_report": {"records": schema_hints},
        "ingestion_error_report": {"records": []},
    }


def build_s33_m01(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = {**p2_inputs(), **s32_outputs()}
    if overrides:
        inputs.update(overrides)
    return build_phase2_view_boundary(inputs)


def build_s33_m02(m01: dict[str, Any] | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    m01 = m01 or build_s33_m01()
    inputs = {**p1_inputs(), **p2_inputs(), **m01}
    if overrides:
        inputs.update(overrides)
    return build_phase1_custody_boundary(inputs)


def build_s33_m03(
    m01: dict[str, Any] | None = None,
    m02: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m01 = m01 or build_s33_m01()
    m02 = m02 or build_s33_m02(m01)
    inputs = {
        **s32_outputs(), **m01, **m02,
        "phase3_run_snapshot": {"snapshot_id": "p3-snapshot", "decision_time": DECISION_TIME, "execution_mode": "BACKTEST", "content_hash": digest("p3-snapshot")},
        "evaluation_window_config": {"decision_time": DECISION_TIME},
        "pit_data_view_policy_config": load_yaml("config/research_tools/PIT_DATA_VIEW_POLICY.yaml"),
        "calendar_timezone_policy_config": load_yaml("config/research_tools/CALENDAR_TIMEZONE_POLICY.yaml"),
        "vintage_policy_config": load_yaml("config/research_tools/VINTAGE_POLICY_REGISTRY.yaml"),
    }
    if overrides:
        inputs.update(overrides)
    return build_temporal_firewall(inputs)


def build_s33_m04(
    m01: dict[str, Any] | None = None,
    m03: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m01 = m01 or build_s33_m01()
    m03 = m03 or build_s33_m03(m01)
    inputs = {
        **p2_inputs(), **m01, **m03,
        "entity_underlying_map_config": load_yaml("config/research_tools/ENTITY_UNDERLYING_MAP.yaml"),
    }
    if overrides:
        inputs.update(overrides)
    return build_entity_resolution_boundary(inputs)


def build_s33_m05(
    m01: dict[str, Any] | None = None,
    m02: dict[str, Any] | None = None,
    m03: dict[str, Any] | None = None,
    m04: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m01 = m01 or build_s33_m01()
    m02 = m02 or build_s33_m02(m01)
    m03 = m03 or build_s33_m03(m01, m02)
    m04 = m04 or build_s33_m04(m01, m03)
    return build_research_data_boundary_bundle({**s32_outputs(), **m01, **m02, **m03, **m04})

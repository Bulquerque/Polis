from __future__ import annotations

from datetime import datetime, timezone

from ..s6_handoff import (
    TARGET_ARTIFACTS,
    assert_no_hidden_bundle,
    build_target_payload,
    handoff_identity,
    lineage_for_target,
    validate_materialized_artifacts,
    validate_quality_gate,
)
from ._p2_semantic_helpers import meta, require_inputs


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = [
        "clean_context_source_panel",
        "clean_document_panel",
        "clean_event_reference_panel",
        "source_quality_panel",
        "quality_report_phase_2",
        "clean_underlying_panel",
        "clean_underlying_trade_panel",
        "clean_macro_br_panel",
        "clean_macro_us_panel",
        "clean_benchmark_panel",
        "clean_calendar_panel",
        "clean_corporate_actions_panel",
        "clean_option_quotes_panel",
        "clean_option_contract_panel",
        "clean_cost_reference_panel",
        "clean_liquidity_reference_panel",
    ]
    require_inputs(inputs, required)
    artifacts = validate_materialized_artifacts(inputs, required)
    quality_status, target_readiness = validate_quality_gate(
        artifacts["quality_report_phase_2"], config
    )

    legacy_artifact_ids = [artifacts[name]["artifact_id"] for name in required]
    pipeline_version = str(config.get("pipeline_version", "V14.1-RC4.1"))
    created_at = str(
        config.get("created_at")
        or artifacts["quality_report_phase_2"].get("created_at")
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    target_statuses = {
        target: str(target_readiness.get(target, {}).get("status") or quality_status).upper()
        for target in TARGET_ARTIFACTS
    }
    payloads = {
        target: build_target_payload(target, artifacts, target_statuses[target])
        for target in TARGET_ARTIFACTS
    }

    def phase_manifest(target: str) -> dict:
        payload = payloads[target]
        digest = handoff_identity(payload, pipeline_version)
        manifest = {
            "handoff_id": f"handoff-{target}-{digest[:20]}",
            "created_at": created_at,
            "target_phase": target,
            # Compatibility surface: preserve the historical all-artifact list.
            "artifact_ids": legacy_artifact_ids,
            # New precise routing metadata, additive and safe for old consumers.
            "target_artifact_ids": payload["target_artifact_ids"],
            "artifact_refs": payload["artifact_refs"],
            "lineage_id": lineage_for_target(payload),
            "pipeline_version": pipeline_version,
            "quality_status": target_statuses[target],
            "target_readiness": target_readiness.get(target, {}),
            "no_hidden_bundle": True,
        }
        assert_no_hidden_bundle(manifest)
        return manifest

    context_payload = payloads["phase_03_agents_rag_memory"]
    context_manifest = {
        **meta("context-handoff", context_payload, config),
        "artifact_ids": legacy_artifact_ids,
        "target_artifact_ids": context_payload["target_artifact_ids"],
        "artifact_refs": context_payload["artifact_refs"],
        "target_phase": "phase_03_agents_rag_memory",
        "quality_status": target_statuses["phase_03_agents_rag_memory"],
        "target_readiness": target_readiness.get("phase_03_agents_rag_memory", {}),
        "no_hidden_bundle": True,
    }
    assert_no_hidden_bundle(context_manifest)

    outputs = {
        "context_handoff_manifest": context_manifest,
        "phase3_handoff_manifest": phase_manifest("phase_03_agents_rag_memory"),
        "phase4_handoff_manifest": phase_manifest("phase_04_feature_base"),
        "phase6_handoff_manifest": phase_manifest("phase_06_candidate_generation"),
    }

    return {
        "module_id": "P2.S6.M02",
        "module_name": "multi_phase_handoff_packager",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S6",
        "contract": "P2_S6_M02_multi_phase_handoff_packager.yaml",
        "required_inputs": required,
        "outputs": outputs,
    }

"""Fail-closed empty-valid runtime closure when S2 has no eligible candidates."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import build_canonical_artifact, digest

MODULE_ID = "P7.EMPTY_VALID_CLOSURE"
EMPTY_ARTIFACTS = (
    "ranked_strategy_candidate_panel",
    "ranking_tie_report",
    "ranking_group_summary_panel",
    "strategy_thesis_card_panel",
    "ranking_trace_panel",
    "ranked_strategy_execution_context_snapshot",
    "abstained_candidate_panel",
    "final_blocked_candidate_panel",
)


def build_empty_runtime_outputs(
    foundation_outputs: Mapping[str, Any], publication_config: Mapping[str, Any]
) -> dict[str, Any]:
    context = _context(foundation_outputs, publication_config)
    outputs = {
        name: _artifact(name, [], context)
        for name in EMPTY_ARTIFACTS
    }
    audit_record = {
        "run_id": context["run_id"], "cycle_id": context["cycle_id"],
        "decision_time": context["decision_time"], "received_count": 0,
        "ranked_count": 0, "abstained_count": 0, "blocked_count": 0,
        "candidate_conservation_pass": True, "group_count": 0, "tie_count": 0,
        "policy_versions": {"empty_valid": "2.3.0"}, "model_versions": [],
        "input_artifact_hashes": {}, "output_artifact_hashes": {},
        "lineage_id": context["lineage_id"], "runtime_status": "SKIPPED_NO_ELIGIBLE_CANDIDATES",
    }
    outputs["ranking_audit_report"] = _artifact("ranking_audit_report", [audit_record], context)
    projection_record = {
        "status": "EMPTY_VALID", "reason_code": "P7_NO_ELIGIBLE_CANDIDATES",
        "ranked_candidate_count": 0, "production_promotion_allowed": False,
    }
    outputs["compatibility_projection_report"] = _artifact(
        "compatibility_projection_report", [projection_record], context
    )
    outputs["phase8_strategy_ranking_handoff_manifest"] = _phase8_manifest(outputs, context)
    return outputs


def _context(
    foundation_outputs: Mapping[str, Any], publication_config: Mapping[str, Any]
) -> dict[str, str]:
    groups = foundation_outputs["candidate_comparison_group_panel"]
    runtime = publication_config["runtime"]
    return {
        "run_id": str(runtime["run_id"]), "cycle_id": str(groups["cycle_id"]),
        "decision_time": str(groups["decision_time"]), "available_at": str(groups["available_at"]),
        "created_at": str(runtime["run_timestamp"]), "lineage_id": str(groups["lineage_id"]),
    }


def _artifact(name: str, records: list[dict[str, Any]], context: Mapping[str, str]) -> dict[str, Any]:
    return build_canonical_artifact(
        name=name, records=records, module_id=MODULE_ID,
        run_id=context["run_id"], cycle_id=context["cycle_id"],
        decision_time=context["decision_time"], available_at=context["available_at"],
        created_at=context["created_at"], lineage_id=context["lineage_id"], schema_version="2.3.0",
    )


def _phase8_manifest(outputs: Mapping[str, Any], context: Mapping[str, str]) -> dict[str, Any]:
    names = (
        "ranked_strategy_candidate_panel", "ranking_audit_report",
        "ranked_strategy_execution_context_snapshot", "abstained_candidate_panel",
        "final_blocked_candidate_panel",
    )
    references = [{
        "artifact_name": name, "artifact_id": outputs[name]["artifact_id"],
        "content_sha256": outputs[name]["content_sha256"],
        "schema_version": outputs[name]["schema_version"], "record_count": outputs[name]["record_count"],
    } for name in names]
    record = {
        "contract_id": "p7_to_p8_strategy_ranking_handoff",
        "contract_version": "2.3.0", "candidate_count": 0,
        "artifact_references": references, "empty_valid": True,
        "candidate_conservation_sha256": digest({"ranked": [], "abstained": [], "blocked": []}),
        "production_promotion_allowed": False,
    }
    return _artifact("phase8_strategy_ranking_handoff_manifest", [record], context)

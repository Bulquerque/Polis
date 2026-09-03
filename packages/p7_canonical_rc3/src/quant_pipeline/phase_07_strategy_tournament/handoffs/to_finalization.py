"""Normalize S6 runtime outputs for S7-S8 finalization."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import P7ContractError
from .common import artifact_records, candidate_index, parse_timestamp
from .finalization_scores import blocked_records, build_scoring_records, decomposition_records
from .finalization_sources import build_strategy_records, p6_artifact_map

HANDOFF_MODULE_ID = "P7.HANDOFF.LEARNING_TO_FINALIZATION"


def _load_bundle(
    learning: Mapping[str, Any], foundation: Mapping[str, Any], tournament: Mapping[str, Any]
) -> dict[str, Any]:
    bundle = {
        "score_rows": artifact_records(learning["hybrid_candidate_score_panel"], "hybrid_candidate_score_panel"),
        "confidence_rows": artifact_records(learning["ltr_score_confidence_panel"], "ltr_score_confidence_panel"),
        "group_rows": artifact_records(foundation["candidate_comparison_group_panel"], "candidate_comparison_group_panel"),
        "eligible_rows": artifact_records(foundation["eligible_strategy_candidate_panel"], "eligible_strategy_candidate_panel"),
        "blocked_rows": artifact_records(foundation["eligibility_blocked_candidate_panel"], "eligibility_blocked_candidate_panel"),
        "pareto_rows": artifact_records(tournament["pareto_candidate_panel"], "pareto_candidate_panel"),
    }
    bundle["groups"] = candidate_index(bundle["group_rows"], "candidate_comparison_group_panel")
    bundle["eligible"] = candidate_index(bundle["eligible_rows"], "eligible_strategy_candidate_panel")
    bundle["pareto"] = candidate_index(bundle["pareto_rows"], "pareto_candidate_panel")
    score_ids = set(candidate_index(bundle["score_rows"], "hybrid_candidate_score_panel"))
    if score_ids != set(bundle["eligible"]):
        raise P7ContractError(
            "P7_HANDOFF_CANDIDATE_SET_MISMATCH", "learning scores and eligible candidate sets differ"
        )
    # Eligibility-blocked candidates never entered scoring. They remain conserved in
    # the foundation outputs and must not be misrepresented as post-score safety blocks.
    bundle["upstream_blocked_rows"] = list(bundle["blocked_rows"])
    bundle["blocked_rows"] = [
        row for row in bundle["blocked_rows"] if str(row.get("candidate_id")) in score_ids
    ]
    return bundle


def _context(foundation: Mapping[str, Any], learning: Mapping[str, Any], created_at: str) -> dict[str, Any]:
    from ..finalization.boundary.config import RuntimeConfig

    anchor = foundation["candidate_comparison_group_panel"]
    return {
        "decision_time": parse_timestamp(anchor["decision_time"], "decision_time"),
        "available_at": parse_timestamp(learning["hybrid_candidate_score_panel"]["available_at"], "available_at"),
        "cycle_id": str(anchor["cycle_id"]), "lineage_id": str(anchor["lineage_id"]),
        "runtime": RuntimeConfig(
            trace_id="trace-p7-runtime", run_id=str(anchor["run_id"]),
            run_timestamp=parse_timestamp(created_at, "created_at"),
        ),
    }


def _artifact_builder(context: Mapping[str, Any]):
    from ..finalization.artifacts import build_artifact

    def build(name: str, records: Any) -> dict[str, Any]:
        return build_artifact(
            artifact_name=name, schema_version="2.2.0", producer_module_id=HANDOFF_MODULE_ID,
            run_id=context["runtime"].run_id, cycle_id=context["cycle_id"],
            decision_time=context["decision_time"], available_at=context["available_at"],
            created_at=context["runtime"].run_timestamp, lineage_id=context["lineage_id"], records=records,
        ).model_dump(mode="json")
    return build


def _build_outputs(
    bundle: Mapping[str, Any], learning: Mapping[str, Any], foundation: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    hybrid, confidence, groups = build_scoring_records(
        bundle["score_rows"], bundle["confidence_rows"], bundle["eligible"], bundle["groups"],
        cycle_id=context["cycle_id"], decision_time=context["decision_time"],
    )
    strategies = build_strategy_records(
        bundle["score_rows"], bundle["eligible"], bundle["groups"], bundle["pareto"],
        p6_artifact_map(foundation), cycle_id=context["cycle_id"], decision_time=context["decision_time"],
    )
    build = _artifact_builder(context)
    return {
        "hybrid_candidate_score_panel": build("hybrid_candidate_score_panel", hybrid),
        "candidate_score_confidence_panel": build("candidate_score_confidence_panel", confidence),
        "comparison_group_panel": build("comparison_group_panel", groups),
        "validated_strategy_candidate_reference_panel": build("validated_strategy_candidate_reference_panel", strategies),
        "pre_final_blocked_candidate_panel": build(
            "pre_final_blocked_candidate_panel",
            blocked_records(bundle["blocked_rows"], cycle_id=context["cycle_id"], decision_time=context["decision_time"]),
        ),
        "score_decomposition_panel": build(
            "score_decomposition_panel",
            decomposition_records(learning, cycle_id=context["cycle_id"], decision_time=context["decision_time"]),
        ),
    }


def _publish_manifest(outputs: dict[str, Any], context: Mapping[str, Any]) -> None:
    from ..finalization.boundary.base import ArtifactReference, HandoffManifestRecord

    references = tuple(ArtifactReference(
        artifact_name=name, artifact_id=value["artifact_id"], content_sha256=value["content_sha256"],
        schema_version=value["schema_version"], record_count=value["record_count"],
    ) for name, value in sorted(outputs.items()))
    manifest = HandoffManifestRecord(
        contract_id="p7-learning-to-finalization-v2.2", contract_version="2.2.0",
        producer="LEARNING", consumer="FINALIZATION", artifact_references=references,
        policy_versions={"hybrid": "v2.2"},
        candidate_count=outputs["validated_strategy_candidate_reference_panel"]["record_count"],
        forbidden_fields_scanned=True,
    )
    outputs["hybrid_scoring_handoff_manifest"] = _artifact_builder(context)(
        "hybrid_scoring_handoff_manifest", (manifest,)
    )


def prepare_finalization_inputs(
    learning: Mapping[str, Any], foundation: Mapping[str, Any], tournament_bundle: Mapping[str, Any],
    *, created_at: str,
) -> dict[str, Any]:
    """Build the S7 input bundle without reconstructing P6 economics."""
    bundle = _load_bundle(learning, foundation, tournament_bundle)
    context = _context(foundation, learning, created_at)
    outputs = _build_outputs(bundle, learning, foundation, context)
    _publish_manifest(outputs, context)
    return outputs

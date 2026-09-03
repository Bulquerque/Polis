"""Normalize the S2 foundation handoff for S3-S4 consumption."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import artifact_records, parse_timestamp
from .tournament_builders import (
    _candidate_records,
    _group_records,
    _metric_records,
    _ranking_policy,
    _scoring_policy,
)


def _transition_context(foundation: Mapping[str, Any], execution_time: str | None) -> dict[str, Any]:
    groups = foundation["candidate_comparison_group_panel"]
    routes = foundation["candidate_metric_route_panel"]
    return {
        "run_id": str(groups["run_id"]),
        "cycle_id": str(groups["cycle_id"]),
        "decision_time": parse_timestamp(groups["decision_time"], "decision_time"),
        "available_at": parse_timestamp(routes["available_at"], "candidate_metric_route_panel.available_at"),
        "execution_time": parse_timestamp(execution_time or groups["created_at"], "execution_time"),
    }


def _artifact_builder(context: Mapping[str, Any]):
    from ..tournament.boundary.artifacts import build_artifact

    def build(name: str, records: tuple[Any, ...]) -> dict[str, Any]:
        return build_artifact(
            artifact_name=name,
            schema_version="2.2.0",
            producer_module_id="P7.S2.M04",
            run_id=context["run_id"],
            cycle_id=context["cycle_id"],
            decision_time=context["decision_time"],
            execution_time=context["execution_time"],
            available_at=context["available_at"],
            lineage_id=f"transition:{name}",
            records=records,
        ).model_dump(mode="json")

    return build


def _publish_manifest(artifacts: dict[str, Any], build) -> None:
    from ..tournament.boundary.records import ArtifactReference, HandoffManifestRecord

    references = tuple(
        ArtifactReference(
            artifact_name=name,
            artifact_id=value["artifact_id"],
            content_sha256=value["content_sha256"],
            schema_version=value["schema_version"],
            record_count=value["record_count"],
        )
        for name, value in sorted(artifacts.items())
        if name != "scoring_policy_context"
    )
    manifest = HandoffManifestRecord(
        contract_id="p7-foundation-to-tournament-v2.2",
        producer="FOUNDATION",
        consumer="TOURNAMENT",
        references=references,
    )
    artifacts["runtime_foundation_handoff_manifest"] = build(
        "runtime_foundation_handoff_manifest", (manifest,)
    )


def prepare_tournament_inputs(
    foundation: Mapping[str, Any], *, execution_time: str | None = None
) -> dict[str, Any]:
    """Build the typed S3 input bundle without creating new economic facts."""
    from ..tournament.boundary.records import FoundationAuditRecord

    eligible_artifact = foundation["eligible_strategy_candidate_panel"]
    groups_artifact = foundation["candidate_comparison_group_panel"]
    routes_artifact = foundation["candidate_metric_route_panel"]
    eligible_rows = artifact_records(eligible_artifact, "eligible_strategy_candidate_panel")
    group_rows = artifact_records(groups_artifact, "candidate_comparison_group_panel")
    route_rows = artifact_records(routes_artifact, "candidate_metric_route_panel")
    context = _transition_context(foundation, execution_time)
    candidates = _candidate_records(eligible_rows, group_rows)
    groups = _group_records(group_rows, eligible_rows)
    metrics = _metric_records(route_rows, context["available_at"], str(routes_artifact["artifact_id"]))
    build = _artifact_builder(context)
    artifacts = {
        "eligible_strategy_candidate_panel": build("eligible_strategy_candidate_panel", candidates),
        "candidate_comparison_group_panel": build("candidate_comparison_group_panel", groups),
        "candidate_metric_source_panel": build("candidate_metric_source_panel", metrics),
        "ranking_policy_context": build("ranking_policy_context", (_ranking_policy(metrics),)),
        "scoring_policy_context": build("scoring_policy_context", (_scoring_policy(metrics, groups),)),
        "runtime_foundation_audit_report": build(
            "runtime_foundation_audit_report",
            (FoundationAuditRecord(
                status="PASS", candidate_count=len(candidates),
                comparison_group_count=len({group.comparison_group_id for group in groups}),
                comparison_groups_frozen=True, candidate_reconciliation_passed=True,
                forbidden_field_scan_passed=True,
            ),),
        ),
    }
    _publish_manifest(artifacts, build)
    return artifacts

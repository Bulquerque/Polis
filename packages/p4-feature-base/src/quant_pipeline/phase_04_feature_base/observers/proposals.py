from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.canonical import deterministic_id
from .output import build_s3_artifact


def _proposal_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    records = value.get("records", [])
    if not isinstance(records, list):
        return []
    return [dict(record) for record in records if isinstance(record, Mapping)]


def review_proposals(
    value: Any,
    context: ExecutionContext,
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify N+1 proposals without resolving or promoting referenced content."""
    seen_manifests: set[str] = set()
    reviews: list[dict[str, Any]] = []
    for proposal in _proposal_records(value):
        manifest_id = str(proposal.get("source_manifest_id", ""))
        if not manifest_id or proposal.get("status") != "PENDING_REVIEW":
            decision, reason = "REJECT", "PROPOSAL_INVALID"
        elif manifest_id in seen_manifests:
            decision, reason = "DUPLICATE", "SOURCE_MANIFEST_ALREADY_REVIEWED"
        else:
            decision, reason = "DEFER", "REFERENCE_ONLY_PROPOSAL_REQUIRES_CONTENT_RESOLUTION"
        seen_manifests.add(manifest_id)
        reviews.append(
            {
                "review_id": deterministic_id("observer-change-review", proposal, 24),
                "proposal_id": str(proposal.get("proposal_id", "")),
                "source_manifest_id": manifest_id,
                "source_cycle_id": str(proposal.get("source_cycle_id", "")),
                "target_cycle_id": str(proposal.get("target_cycle_id", context.cycle_id)),
                "decision": decision,
                "reason_code": reason,
                "reviewed_at": context.created_at.isoformat().replace("+00:00", "Z"),
                "lineage_id": deterministic_id("lineage-observer-change-review", proposal, 24),
            }
        )
    return build_s3_artifact(
        name="observer_change_review_registry",
        module_id="P4.S3.M01",
        context=context,
        records=reviews,
        schema=schema,
        extra={"review_mode": "REFERENCE_ONLY_NO_AUTOMATIC_PROMOTION"},
    )


def budget_decisions(
    review_registry: Mapping[str, Any],
    context: ExecutionContext,
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Close the N+1 flow with explicit non-promoting budget decisions."""
    records: list[dict[str, Any]] = []
    for review in _proposal_records(review_registry):
        decision = str(review.get("decision", "REJECT"))
        if decision == "DEFER":
            budget_status = "DEFER"
            reason = "CONTENT_NOT_MATERIALIZED_FOR_BUDGET_REVIEW"
        elif decision == "DUPLICATE":
            budget_status = "DUPLICATE"
            reason = str(review.get("reason_code", "DUPLICATE"))
        else:
            budget_status = "REJECT"
            reason = str(review.get("reason_code", "REJECTED_BY_REVIEW"))
        records.append(
            {
                "decision_id": deterministic_id("observer-change-budget-decision", review, 24),
                "proposal_id": str(review.get("proposal_id", "")),
                "review_id": str(review.get("review_id", "")),
                "decision": budget_status,
                "reason_code": reason,
                "automatic_promotion": False,
                "target_cycle_id": str(review.get("target_cycle_id", context.cycle_id)),
                "lineage_id": deterministic_id("lineage-observer-change-decision", review, 24),
            }
        )
    return build_s3_artifact(
        name="observer_change_decision_registry",
        module_id="P4.S3.M05",
        context=context,
        records=records,
        schema=schema,
        extra={"same_cycle_application_forbidden": True},
    )

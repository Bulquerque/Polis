"""Pure validators for promoted patches and matured belief feedback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .canonical import (
    format_utc,
    parse_aware_datetime,
    parse_cycle_id,
    require_fields,
    stable_sha256,
    version_satisfies,
)
from .errors import S3ContractError

_PATCH_REQUIRED = (
    "patch_id",
    "change_type",
    "change_target",
    "promotion_status",
    "source_cycle_id",
    "promoted_at",
    "effective_cycle_id",
    "target_version_range",
    "payload_hash",
    "lineage_id",
)

_FEEDBACK_REQUIRED = (
    "feedback_id",
    "commitment_id",
    "commit_hash",
    "expected_commit_hash",
    "person_id",
    "proposition_id",
    "horizon",
    "source_cycle_id",
    "matures_at",
    "outcome_available_at",
    "experience_available_from_cycle",
    "original_belief_ref",
    "outcome_ref",
    "evaluation_summary",
    "lineage_id",
)


def normalize_promoted_patch(
    patch: dict[str, Any],
    *,
    policy: dict[str, Any],
    current_cycle: int,
    as_of: datetime,
) -> dict[str, Any]:
    """Validate promotion, temporal scope, compatibility and payload integrity."""

    require_fields(patch, _PATCH_REQUIRED, location="patch")
    if policy["promoted_status_required"] and patch["promotion_status"] != "PROMOTED":
        raise S3ContractError("P3_S3_M01_UNPROMOTED_PATCH", "patch is not PROMOTED")
    if patch["change_type"] not in set(policy["allowed_change_types"]):
        raise S3ContractError(
            "P3_S3_M01_CHANGE_TYPE_FORBIDDEN",
            f"change type {patch['change_type']} forbidden",
        )

    source_cycle = parse_cycle_id(patch["source_cycle_id"], field="patch.source_cycle_id")
    effective_cycle = parse_cycle_id(
        patch["effective_cycle_id"], field="patch.effective_cycle_id"
    )
    if source_cycle >= current_cycle:
        raise S3ContractError(
            "P3_S3_M01_SAME_OR_FUTURE_CYCLE_PATCH",
            "source cycle must be before current",
        )
    if effective_cycle != current_cycle:
        raise S3ContractError(
            "P3_S3_M01_EFFECTIVE_CYCLE_MISMATCH",
            "patch must activate exactly in current cycle",
        )

    promoted_at = parse_aware_datetime(patch["promoted_at"], field="patch.promoted_at")
    if promoted_at > as_of:
        raise S3ContractError("P3_S3_M01_FUTURE_PATCH", "promoted_at after as_of")

    current_version = policy["target_versions"].get(str(patch["change_target"]))
    if current_version is None:
        raise S3ContractError(
            "P3_S3_M01_TARGET_NOT_FOUND", f"unknown target {patch['change_target']}"
        )
    if not version_satisfies(str(current_version), str(patch["target_version_range"])):
        raise S3ContractError(
            "P3_S3_M01_VERSION_INCOMPATIBLE",
            f"{current_version} not in {patch['target_version_range']}",
        )

    payload = patch.get("payload")
    if payload is not None and stable_sha256(payload) != patch["payload_hash"]:
        raise S3ContractError(
            "P3_S3_M01_PAYLOAD_HASH_MISMATCH", "payload hash mismatch"
        )

    return {
        "patch_id": str(patch["patch_id"]),
        "proposal_id": patch.get("proposal_id"),
        "source_experiment_id": patch.get("source_experiment_id"),
        "source_cycle_id": source_cycle,
        "change_type": str(patch["change_type"]),
        "change_target": str(patch["change_target"]),
        "target_version_range": str(patch["target_version_range"]),
        "target_current_version": str(current_version),
        "promotion_status": "PROMOTED",
        "promoted_at": format_utc(promoted_at),
        "effective_cycle_id": effective_cycle,
        "payload_ref": patch.get("payload_ref"),
        "payload_hash": str(patch["payload_hash"]),
        "lineage_id": str(patch["lineage_id"]),
    }


def _validate_feedback_scope(
    item: dict[str, Any], reference: dict[str, Any], *, reference_name: str
) -> None:
    for field in ("person_id", "proposition_id", "horizon"):
        observed = reference.get(field)
        if observed not in (None, item[field]):
            raise S3ContractError(
                f"P3_S3_M02_{field.upper()}_SCOPE_MISMATCH",
                f"{item['feedback_id']} in {reference_name}",
            )


def normalize_matured_feedback_item(
    item: dict[str, Any],
    *,
    current_cycle: int,
    as_of: datetime,
) -> dict[str, Any]:
    """Validate one commitment-linked feedback item and return canonical fields."""

    require_fields(item, _FEEDBACK_REQUIRED, location="feedback_item")
    feedback_id = str(item["feedback_id"])
    if item["commit_hash"] != item["expected_commit_hash"]:
        raise S3ContractError(
            "P3_S3_M02_COMMIT_HASH_MISMATCH", str(item["commitment_id"])
        )

    source_cycle = parse_cycle_id(
        item["source_cycle_id"], field="feedback.source_cycle_id"
    )
    available_cycle = parse_cycle_id(
        item["experience_available_from_cycle"],
        field="feedback.experience_available_from_cycle",
    )
    if source_cycle >= current_cycle:
        raise S3ContractError(
            "P3_S3_M02_SAME_OR_FUTURE_CYCLE_FEEDBACK",
            "source cycle must precede current",
        )
    if available_cycle > current_cycle:
        raise S3ContractError(
            "P3_S3_M02_FEEDBACK_NOT_AVAILABLE_YET",
            "experience available in future cycle",
        )

    matures_at = parse_aware_datetime(item["matures_at"], field="feedback.matures_at")
    outcome_available_at = parse_aware_datetime(
        item["outcome_available_at"], field="feedback.outcome_available_at"
    )
    if matures_at > as_of:
        raise S3ContractError("P3_S3_M02_OUTCOME_NOT_MATURED", feedback_id)
    if outcome_available_at > as_of:
        raise S3ContractError("P3_S3_M02_FUTURE_OUTCOME", feedback_id)
    if outcome_available_at < matures_at:
        raise S3ContractError("P3_S3_M02_OUTCOME_BEFORE_MATURITY", feedback_id)

    original = item["original_belief_ref"]
    outcome = item["outcome_ref"]
    if not isinstance(original, dict) or not isinstance(outcome, dict):
        raise S3ContractError("P3_S3_M02_REFERENCE_INVALID", feedback_id)
    _validate_feedback_scope(item, original, reference_name="original_belief_ref")
    _validate_feedback_scope(item, outcome, reference_name="outcome_ref")

    return {
        "feedback_id": feedback_id,
        "commitment_id": str(item["commitment_id"]),
        "commit_hash": str(item["commit_hash"]),
        "person_id": str(item["person_id"]),
        "proposition_id": str(item["proposition_id"]),
        "horizon": str(item["horizon"]),
        "source_cycle_id": source_cycle,
        "matures_at": format_utc(matures_at),
        "outcome_available_at": format_utc(outcome_available_at),
        "experience_available_from_cycle": available_cycle,
        "original_belief_ref": dict(original),
        "outcome_ref": dict(outcome),
        "evaluation_summary": dict(item["evaluation_summary"]),
        "lineage_id": str(item["lineage_id"]),
    }

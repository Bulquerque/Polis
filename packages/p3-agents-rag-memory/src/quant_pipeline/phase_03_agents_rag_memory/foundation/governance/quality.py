from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .canonical import extract_records, require_no_forbidden_fields, stable_sha256
from .errors import Issue, S1ContractError
from .handoff import _log_event, _require_inputs
from .models import QualityDecision, S1Settings, ValidationStatus
from .schema_registry import SchemaRegistry


def _quality_decision(row: dict[str, Any], policy: dict[str, Any]) -> tuple[QualityDecision, list[str]]:
    status = str(row.get("quality_status") or "").strip().upper()
    readability = str(row.get("readability_status") or "").strip().lower()
    error_flag = bool(row.get("error_flag"))
    warning_flag = bool(row.get("warning_flag"))
    reasons = [str(reason) for reason in row.get("quality_reasons", []) if reason]

    invalid_statuses = {str(value).strip().upper() for value in policy.get("invalid_statuses", [])}
    invalid_statuses.update({"BLOCK", "INVALID", "CORRUPT", "UNTRACEABLE"})
    if error_flag or status in invalid_statuses or readability in {
        "unreadable",
        "failed",
        "fail",
        "error",
        "block",
    }:
        return QualityDecision.REJECTED_INVALID, sorted(set(reasons + ["INVALID_SOURCE"]))
    if warning_flag or status in {"WARN", "DEGRADED"} or readability in {
        "warning",
        "warn",
        "partial",
        "degraded",
        "unknown",
    }:
        return QualityDecision.ACCEPTED_WITH_WARNING, sorted(
            set(reasons + ["QUALITY_WARNING_PROPAGATED"])
        )
    return QualityDecision.ACCEPTED, sorted(set(reasons))


def apply_source_quality_policy(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    registry: SchemaRegistry | None = None,
) -> dict[str, Any]:
    """Apply P2 source-quality decisions without recomputing quality scores."""

    settings = S1Settings.from_mapping(config)
    registry = registry or SchemaRegistry()
    _log_event("module_started", module_id="P3.S1.M02")
    required = (
        "validated_phase2_handoff",
        "source_quality_panel",
        "source_quality_policy_config",
    )
    _require_inputs(inputs, required)
    immutable_copy = deepcopy(inputs)

    handoff = inputs["validated_phase2_handoff"]
    registry.validate_internal("validated_phase2_handoff", handoff)
    quality_panel = registry.validate_external(
        "source_quality_panel", inputs["source_quality_panel"]
    )
    policy = inputs["source_quality_policy_config"]
    if not isinstance(policy, dict):
        raise S1ContractError(
            "P3_S1_M02_POLICY_INVALID",
            "source_quality_policy_config must be a mapping",
        )
    if bool(policy.get("recompute_quality", False)):
        raise S1ContractError(
            "P3_S1_M02_QUALITY_RECOMPUTATION_FORBIDDEN",
            "P3.S1.M02 must not recompute quality",
        )

    quality_records = extract_records(quality_panel, "source_quality_panel")
    by_source: dict[str, dict[str, Any]] = {}
    for row in quality_records:
        source_id = str(row["source_id"])
        if source_id in by_source and settings.block_on_duplicate_quality_source:
            raise S1ContractError(
                "P3_S1_M02_DUPLICATE_SOURCE_QUALITY",
                f"Duplicate quality record for source_id={source_id}",
            )
        by_source[source_id] = row

    decisions: list[dict[str, Any]] = []
    issues: list[Issue] = []
    for indexed in handoff["record_index"]:
        source_id = indexed.get("source_id")
        if source_id is None or source_id not in by_source:
            decision = QualityDecision.REJECTED_UNTRACEABLE
            reasons = ["SOURCE_QUALITY_REFERENCE_MISSING"]
            quality_row = None
            issues.append(
                Issue(
                    code="P3_S1_M02_QUALITY_REFERENCE_MISSING",
                    severity="WARNING",
                    message="Record rejected because no source-quality record is available",
                    artifact_name=str(indexed["artifact_name"]),
                    record_id=str(indexed["record_id"]),
                    field="source_id",
                )
            )
        else:
            quality_row = by_source[str(source_id)]
            decision, reasons = _quality_decision(quality_row, policy)

        decisions.append(
            {
                "artifact_name": str(indexed["artifact_name"]),
                "record_id": str(indexed["record_id"]),
                "source_id": source_id,
                "decision": decision.value,
                "quality_score": None if quality_row is None else quality_row["quality_score"],
                "quality_status": None
                if quality_row is None
                else quality_row.get("quality_status"),
                "readability_status": None
                if quality_row is None
                else quality_row["readability_status"],
                "error_flag": None if quality_row is None else quality_row["error_flag"],
                "warning_flag": None if quality_row is None else quality_row["warning_flag"],
                "reason_codes": reasons,
            }
        )

    decision_counts = Counter(row["decision"] for row in decisions)
    accepted = decision_counts[QualityDecision.ACCEPTED.value]
    accepted_warning = decision_counts[QualityDecision.ACCEPTED_WITH_WARNING.value]
    rejected = (
        decision_counts[QualityDecision.REJECTED_INVALID.value]
        + decision_counts[QualityDecision.REJECTED_UNTRACEABLE.value]
    )
    accepted_total = accepted + accepted_warning
    if settings.block_if_no_accepted_records and decisions and accepted_total == 0:
        raise S1ContractError(
            "P3_S1_M02_NO_USABLE_CONTEXT",
            "Source-quality policy rejected every indexed context record",
            issues=issues,
        )

    if inputs != immutable_copy:
        raise S1ContractError(
            "P3_S1_INPUT_MUTATION_DETECTED",
            "P3.S1.M02 mutated an input artifact",
        )

    policy_snapshot = {
        "invalid_statuses": sorted(
            str(value) for value in policy.get("invalid_statuses", [])
        ),
        "low_quality_action": str(policy.get("low_quality_action", "propagate_flag")),
        "usable_with_warning_action": str(
            policy.get("usable_with_warning_action", "allow_with_quality_metadata")
        ),
        "recompute_quality": False,
    }
    artifacts = [
        ref
        for ref in handoff["artifacts"]
        if ref["artifact_name"]
        in {
            "clean_context_source_panel",
            "clean_document_panel",
            "clean_event_reference_panel",
            "source_quality_panel",
        }
    ]
    status = (
        ValidationStatus.DEGRADED
        if rejected or issues or accepted_warning
        else ValidationStatus.READY
    )
    output: dict[str, Any] = {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p3.s1.validated_context_inputs.v2",
        "validation_status": status.value,
        "source_handoff_id": str(handoff["handoff_id"]),
        "source_artifacts": artifacts,
        "quality_policy": {
            "policy_id": "p3.s1.source_quality_policy.v1",
            "policy_hash": stable_sha256(policy_snapshot),
            **policy_snapshot,
        },
        "quality_decisions": sorted(
            decisions,
            key=lambda row: (row["artifact_name"], row["record_id"]),
        ),
        "summary": {
            "total": len(decisions),
            "accepted": accepted,
            "accepted_with_warning": accepted_warning,
            "rejected": rejected,
            "rejected_invalid": decision_counts[
                QualityDecision.REJECTED_INVALID.value
            ],
            "rejected_untraceable": decision_counts[
                QualityDecision.REJECTED_UNTRACEABLE.value
            ],
        },
        "issues": [issue.to_dict() for issue in issues],
        "lineage_id": f"lineage-p3-s1-quality-{stable_sha256(decisions)[:20]}",
    }
    output["content_hash"] = stable_sha256(output)
    registry.validate_internal("validated_context_inputs", output)
    require_no_forbidden_fields(output, "validated_context_inputs")
    _log_event(
        "module_succeeded",
        module_id="P3.S1.M02",
        validation_status=status.value,
        input_record_count=len(decisions),
        accepted_count=accepted_total,
        rejected_count=rejected,
        warning_count=len(issues) + accepted_warning,
    )
    return output

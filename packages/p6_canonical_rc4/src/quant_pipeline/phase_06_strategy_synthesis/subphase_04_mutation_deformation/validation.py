"""Mutation trace and complexity validation."""

from __future__ import annotations

from ..domain.identity import canonical_leg_payload
from ..domain.models import (
    MutationApplication,
    RejectionRecord,
    StrategyCandidate,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import canonical_sha256, stable_id


def validate_mutation_traces(
    candidates: tuple[StrategyCandidate, ...],
    applications: tuple[MutationApplication, ...],
) -> tuple[MutationApplication, ...]:
    candidate_ids = {item.candidate_id for item in candidates}
    output = []
    for application in applications:
        valid = (
            application.child_candidate_id in candidate_ids
            and application.parent_candidate_id
            != application.child_candidate_id
        )
        output.append(
            application.model_copy(
                update={
                    "valid": valid,
                    "reason_code": (
                        None
                        if valid
                        else "P6_MUTATION_TRACE_INVALID"
                    ),
                }
            )
        )
    return tuple(output)


def complexity_gate(
    candidates: tuple[StrategyCandidate, ...],
    applications: tuple[MutationApplication, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[StrategyCandidate, ...],
    tuple[RejectionRecord, ...],
]:
    application_by_child = {
        item.child_candidate_id: item
        for item in applications
    }
    accepted = []
    rejected = []
    fingerprints: set[str] = set()
    for candidate in candidates:
        reasons = _complexity_reasons(
            candidate,
            fingerprints,
            configuration,
        )
        if reasons:
            application = application_by_child.get(
                candidate.candidate_id
            )
            rejected.append(
                RejectionRecord(
                    rejection_id=stable_id(
                        "rejection",
                        candidate.candidate_id,
                        reasons,
                    ),
                    candidate_id=candidate.candidate_id,
                    template_id=candidate.origin_template_id,
                    stage="P6.S4.M04",
                    reason_code=reasons[0],
                    details={
                        "reasons": list(reasons),
                        "mutation_id": (
                            None
                            if application is None
                            else application.mutation_id
                        ),
                    },
                )
            )
            continue
        fingerprint = canonical_sha256(
            canonical_leg_payload(candidate.legs)
        )
        fingerprints.add(fingerprint)
        accepted.append(candidate)
    return tuple(accepted), tuple(rejected)


def _complexity_reasons(
    candidate: StrategyCandidate,
    fingerprints: set[str],
    configuration: Phase6RunConfiguration,
) -> list[str]:
    reasons = []
    if len(candidate.legs) > configuration.budgets.max_legs:
        reasons.append("P6_COMPLEXITY_BUDGET_EXCEEDED")
    expirations = {
        leg.expiration
        for leg in candidate.legs
        if leg.expiration is not None
    }
    if len(expirations) > configuration.budgets.max_expirations:
        reasons.append("P6_COMPLEXITY_BUDGET_EXCEEDED")
    if any(
        leg.quantity > configuration.budgets.max_quantity
        for leg in candidate.legs
    ):
        reasons.append("P6_COMPLEXITY_BUDGET_EXCEEDED")
    fingerprint = canonical_sha256(
        canonical_leg_payload(candidate.legs)
    )
    if fingerprint in fingerprints:
        reasons.append("P6_EQUIVALENT_CANDIDATE")
    return reasons

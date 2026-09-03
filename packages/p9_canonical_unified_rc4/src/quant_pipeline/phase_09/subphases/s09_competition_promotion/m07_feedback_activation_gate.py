from __future__ import annotations

from collections import defaultdict

from .enums import FeedbackEffectType, FeedbackValidationState, ModuleStatus
from .models.common import CycleRef, ModuleDiagnostics, ModuleResult, build_module_result
from .models.feedback import (
    FeedbackActivationGateOutput,
    FeedbackActivationLedgerEntry,
    FeedbackCandidateManifest,
    FeedbackPackage,
    FeedbackPolicyRegistry,
    FeedbackValidationDecision,
    TargetCapabilitySnapshot,
    ValidatedNextCycleFeedbackManifest,
)

MODULE_ID = "P9.S9.M07"


def _major(version: str) -> int:
    first = version.split(".", 1)[0]
    try:
        return int(first)
    except ValueError as error:
        raise ValueError(f"invalid semantic version: {version!r}") from error


def validate_feedback_for_future_activation(
    *,
    candidate_manifest: FeedbackCandidateManifest,
    registry: FeedbackPolicyRegistry,
    target_capabilities: tuple[TargetCapabilitySnapshot, ...],
    previous_activation_ledger: tuple[FeedbackActivationLedgerEntry, ...],
    current_cycle: CycleRef,
) -> ModuleResult[FeedbackActivationGateOutput]:
    """Validate future-cycle feedback compatibility without activating target policies."""

    capability_map = {
        (capability.target_phase, capability.target_policy_id): capability
        for capability in target_capabilities
    }
    prior_ids = {entry.feedback_id for entry in previous_activation_ledger}
    preliminary: dict[str, FeedbackValidationDecision] = {}
    packages_by_id = {
        package.feedback_id: package for package in candidate_manifest.feedback_packages
    }

    for package in candidate_manifest.feedback_packages:
        target = registry.resolve(package.target_phase, package.target_policy_id)
        reason_codes: list[str] = []
        state: FeedbackValidationState
        requires_p0 = package.effect_type in {
            FeedbackEffectType.DEPRECATION_CANDIDATE,
            FeedbackEffectType.ELIGIBILITY_REVIEW,
            FeedbackEffectType.POLICY_BOUND_CHANGE,
        }
        if package.feedback_id in prior_ids:
            state = FeedbackValidationState.REJECTED_DUPLICATE
            reason_codes.append("P9_FEEDBACK_DUPLICATE")
        elif package.target_cycle.ordinal <= current_cycle.ordinal:
            state = FeedbackValidationState.REJECTED_SAME_CYCLE
            reason_codes.append("P9_FEEDBACK_SAME_CYCLE_REJECTED")
        elif package.expires_after_cycle.ordinal < current_cycle.ordinal:
            state = FeedbackValidationState.REJECTED_EXPIRED
            reason_codes.append("P9_FEEDBACK_EXPIRED")
        elif target is None:
            state = FeedbackValidationState.REJECTED_TARGET_MISSING
            reason_codes.append("P9_FEEDBACK_TARGET_MISSING")
        else:
            capability = capability_map.get((package.target_phase, package.target_policy_id))
            if capability is None or not capability.available:
                state = FeedbackValidationState.RESERVED_CAPABILITY_UNAVAILABLE
                reason_codes.append("P9_FEEDBACK_TARGET_CAPABILITY_UNAVAILABLE")
            elif _major(package.target_policy_version) != capability.accepted_contract_major:
                state = FeedbackValidationState.REJECTED_SCHEMA_INCOMPATIBLE
                reason_codes.append("P9_FEEDBACK_SCHEMA_MAJOR_MISMATCH")
            elif package.target_policy_version != target.target_policy_version:
                state = FeedbackValidationState.REJECTED_SCHEMA_INCOMPATIBLE
                reason_codes.append("P9_FEEDBACK_POLICY_VERSION_MISMATCH")
            elif requires_p0:
                state = FeedbackValidationState.VALIDATED_PENDING_P0
            else:
                state = FeedbackValidationState.VALIDATED_FOR_FUTURE_CYCLE
        preliminary[package.feedback_id] = FeedbackValidationDecision(
            feedback_id=package.feedback_id,
            state=state,
            reason_codes=tuple(reason_codes),
            requires_p0_authorization=requires_p0,
        )

    atomic_groups: dict[str, list[str]] = defaultdict(list)
    for package in candidate_manifest.feedback_packages:
        if package.atomic_group_id is not None:
            atomic_groups[package.atomic_group_id].append(package.feedback_id)
    for group_ids in atomic_groups.values():
        group_states = {preliminary[feedback_id].state for feedback_id in group_ids}
        acceptable = {
            FeedbackValidationState.VALIDATED_PENDING_P0,
            FeedbackValidationState.VALIDATED_FOR_FUTURE_CYCLE,
        }
        if not group_states.issubset(acceptable):
            for feedback_id in group_ids:
                original = preliminary[feedback_id]
                if original.state in acceptable:
                    preliminary[feedback_id] = FeedbackValidationDecision(
                        feedback_id=feedback_id,
                        state=FeedbackValidationState.REJECTED_SCHEMA_INCOMPATIBLE,
                        reason_codes=("P9_FEEDBACK_ATOMIC_GROUP_REJECTED",),
                        requires_p0_authorization=original.requires_p0_authorization,
                    )

    accepted: list[FeedbackPackage] = []
    rejected: list[FeedbackPackage] = []
    reserved: list[FeedbackPackage] = []
    for feedback_id in sorted(packages_by_id):
        package = packages_by_id[feedback_id]
        state = preliminary[feedback_id].state
        if state in {
            FeedbackValidationState.VALIDATED_PENDING_P0,
            FeedbackValidationState.VALIDATED_FOR_FUTURE_CYCLE,
        }:
            accepted.append(package)
        elif state == FeedbackValidationState.RESERVED_CAPABILITY_UNAVAILABLE:
            reserved.append(package)
        else:
            rejected.append(package)

    manifest = ValidatedNextCycleFeedbackManifest(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        reserved=tuple(reserved),
        decisions=tuple(preliminary[feedback_id] for feedback_id in sorted(preliminary)),
    )
    output = FeedbackActivationGateOutput(
        manifest=manifest,
        pending_p0_count=sum(
            decision.state == FeedbackValidationState.VALIDATED_PENDING_P0
            for decision in manifest.decisions
        ),
        future_validated_count=sum(
            decision.state == FeedbackValidationState.VALIDATED_FOR_FUTURE_CYCLE
            for decision in manifest.decisions
        ),
        rejected_count=len(rejected),
        reserved_count=len(reserved),
    )
    status = ModuleStatus.SUCCESS if not rejected else ModuleStatus.LIMITED
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("candidate_count", len(candidate_manifest.feedback_packages)),
                ("accepted_count", len(accepted)),
                ("rejected_count", len(rejected)),
                ("reserved_count", len(reserved)),
            ),
            trace=("feedback packages validated for future activation; no target policy changed",),
        ),
    )

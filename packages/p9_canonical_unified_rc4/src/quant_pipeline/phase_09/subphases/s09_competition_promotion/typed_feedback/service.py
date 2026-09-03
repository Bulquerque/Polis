from __future__ import annotations

from ..enums import EvidenceQuality, FeedbackBuildState, FeedbackEffectType, FeedbackPhase
from ..hashing import sha256_hex
from ..models.common import CycleRef
from ..models.feedback import (
    FeedbackBuildPolicy,
    FeedbackCandidateManifest,
    FeedbackEffectivenessRecord,
    FeedbackPackage,
    FeedbackPolicyRegistry,
    RootCauseEvidence,
)
from .common_validation import bounds_are_compatible
from .p5_forecast_builder import build_p5_feedback
from .p6_synthesis_builder import build_p6_feedback
from .p7_ranking_builder import build_p7_feedback
from .p8_portfolio_execution_builder import build_p8_feedback


def build_typed_feedback_candidates(
    *,
    root_causes: tuple[RootCauseEvidence, ...],
    registry: FeedbackPolicyRegistry,
    previous_effectiveness: tuple[FeedbackEffectivenessRecord, ...],
    source_cycle: CycleRef,
    target_cycle: CycleRef,
    policy: FeedbackBuildPolicy | None = None,
) -> FeedbackCandidateManifest:
    policy = policy or FeedbackBuildPolicy()
    previous = {
        (record.target_phase, record.target_policy_id): record
        for record in previous_effectiveness
    }
    built: list[FeedbackPackage] = []
    rejected: list[str] = []
    warnings: list[str] = []
    expiry = CycleRef(
        cycle_id=f"{target_cycle.cycle_id}+{policy.expiry_after_cycles}",
        ordinal=target_cycle.ordinal + policy.expiry_after_cycles,
    )

    builders = {
        FeedbackPhase.P5: build_p5_feedback,
        FeedbackPhase.P6: build_p6_feedback,
        FeedbackPhase.P7: build_p7_feedback,
        FeedbackPhase.P8: build_p8_feedback,
    }
    for cause in sorted(root_causes, key=lambda item: item.root_cause_id):
        target = registry.resolve(cause.target_phase, cause.target_policy_id)
        if target is None:
            rejected.append(cause.root_cause_id)
            warnings.append(f"{cause.root_cause_id}: target policy is not registered")
            continue
        if cause.feedback_type not in target.allowed_feedback_types:
            rejected.append(cause.root_cause_id)
            warnings.append(f"{cause.root_cause_id}: feedback type is not allowed for target")
            continue
        if cause.confidence < policy.minimum_confidence:
            rejected.append(cause.root_cause_id)
            warnings.append(f"{cause.root_cause_id}: confidence below feedback policy")
            continue
        if cause.economic_materiality < policy.minimum_economic_materiality:
            rejected.append(cause.root_cause_id)
            warnings.append(f"{cause.root_cause_id}: economic materiality below policy")
            continue
        if (
            cause.evidence_quality == EvidenceQuality.MODEL_BASED_COUNTERFACTUAL
            and cause.effect_type != FeedbackEffectType.RESEARCH_REQUEST
        ):
            rejected.append(cause.root_cause_id)
            warnings.append(
                f"{cause.root_cause_id}: model-based counterfactual only supports research requests"
            )
            continue
        effectiveness = previous.get((cause.target_phase, cause.target_policy_id))
        if effectiveness is not None and effectiveness.regressive:
            if cause.effect_type != FeedbackEffectType.RESEARCH_REQUEST:
                rejected.append(cause.root_cause_id)
                warnings.append(
                    f"{cause.root_cause_id}: previous feedback was regressive; "
                    "only research request allowed"
                )
                continue
        if not bounds_are_compatible(cause, target):
            rejected.append(cause.root_cause_id)
            warnings.append(f"{cause.root_cause_id}: proposed bounds exceed target registry")
            continue
        feedback_id = f"fb-{cause.target_phase.value.lower()}-{sha256_hex(cause)[:16]}"
        package = builders[cause.target_phase](
            feedback_id=feedback_id,
            cause=cause,
            source_cycle=source_cycle,
            target_cycle=target_cycle,
            expires_after_cycle=expiry,
            target_policy_version=target.target_policy_version,
        )
        built.append(package)

    state = (
        FeedbackBuildState.FEEDBACK_CANDIDATE_BUILT
        if built
        else FeedbackBuildState.NO_ACTIONABLE_FEEDBACK
    )
    return FeedbackCandidateManifest(
        build_state=state,
        feedback_packages=tuple(built),
        rejected_root_cause_ids=tuple(rejected),
        warnings=tuple(warnings),
    )

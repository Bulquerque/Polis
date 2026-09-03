from __future__ import annotations

from .enums import FeedbackBuildState, ModuleStatus
from .models.common import CycleRef, ModuleDiagnostics, ModuleResult, build_module_result
from .models.feedback import (
    FeedbackBuildPolicy,
    FeedbackCandidateManifest,
    FeedbackEffectivenessRecord,
    FeedbackPolicyRegistry,
    RootCauseEvidence,
)
from .typed_feedback import build_typed_feedback_candidates

MODULE_ID = "P9.S9.M06"


def build_typed_feedback(
    *,
    root_causes: tuple[RootCauseEvidence, ...],
    registry: FeedbackPolicyRegistry,
    previous_effectiveness: tuple[FeedbackEffectivenessRecord, ...],
    source_cycle: CycleRef,
    target_cycle: CycleRef,
    policy: FeedbackBuildPolicy | None = None,
) -> ModuleResult[FeedbackCandidateManifest]:
    """Build phase-local bounded feedback packages without changing current-cycle policies."""

    manifest = build_typed_feedback_candidates(
        root_causes=root_causes,
        registry=registry,
        previous_effectiveness=previous_effectiveness,
        source_cycle=source_cycle,
        target_cycle=target_cycle,
        policy=policy,
    )
    status = (
        ModuleStatus.SUCCESS
        if manifest.build_state == FeedbackBuildState.FEEDBACK_CANDIDATE_BUILT
        else ModuleStatus.LIMITED
    )
    reason_codes = (
        ()
        if manifest.feedback_packages
        else ("P9_FEEDBACK_NO_ACTIONABLE_EVIDENCE",)
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=manifest,
        reason_codes=reason_codes,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("root_cause_count", len(root_causes)),
                ("feedback_package_count", len(manifest.feedback_packages)),
                ("rejected_root_cause_count", len(manifest.rejected_root_cause_ids)),
            ),
            trace=("four typed phase-specific feedback builders evaluated",),
            warnings=manifest.warnings,
        ),
    )

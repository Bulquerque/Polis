from __future__ import annotations

from ..models.common import CycleRef
from ..models.feedback import P9P6SynthesisFeedback, RootCauseEvidence


def build_p6_feedback(
    *,
    feedback_id: str,
    cause: RootCauseEvidence,
    source_cycle: CycleRef,
    target_cycle: CycleRef,
    expires_after_cycle: CycleRef,
    target_policy_version: str,
) -> P9P6SynthesisFeedback:
    return P9P6SynthesisFeedback(
        feedback_id=feedback_id,
        source_cycle=source_cycle,
        target_cycle=target_cycle,
        target_policy_id=cause.target_policy_id,
        target_policy_version=target_policy_version,
        feedback_type=cause.feedback_type,
        effect_type=cause.effect_type,
        evidence_refs=cause.evidence_refs,
        confidence=cause.confidence,
        economic_materiality=cause.economic_materiality,
        numeric_change_bounds=cause.numeric_change_bounds,
        categorical_change_bounds=cause.categorical_change_bounds,
        expires_after_cycle=expires_after_cycle,
        atomic_group_id=cause.atomic_group_id,
    )

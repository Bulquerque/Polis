from __future__ import annotations

from datetime import datetime

from pydantic import model_validator

from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import S9ExecutionEnvelope

from .common import ArtifactReference, CycleRef, Sha256Hex, UtcTimestampedModel
from .effectiveness import FeedbackEffectivenessInputBundle
from .memory import (
    ResearchClaimCandidate,
    ResearchMemorySnapshot,
    ResearchMemoryUpdatePolicy,
    ResearchNormalizationPolicy,
)
from .release import (
    BuildEnvironment,
    ConsumerReceiptReference,
    SubphaseReceiptReference,
    TestSummary,
)


class S10InputBundle(UtcTimestampedModel):
    s9_execution_envelope: S9ExecutionEnvelope
    research_claim_candidates: tuple[ResearchClaimCandidate, ...]
    normalization_policy: ResearchNormalizationPolicy
    previous_memory_snapshot: ResearchMemorySnapshot | None = None
    memory_update_policy: ResearchMemoryUpdatePolicy
    feedback_effectiveness_input: FeedbackEffectivenessInputBundle
    upstream_subphase_receipts: tuple[SubphaseReceiptReference, ...]
    consumer_receipts: tuple[ConsumerReceiptReference, ...]
    build_environment: BuildEnvironment
    test_summary: TestSummary
    source_tree_sha256: Sha256Hex
    s9_wheel_sha256: Sha256Hex
    s10_wheel_sha256: Sha256Hex
    test_report_ref: ArtifactReference
    source_tree_ref: ArtifactReference
    s9_wheel_ref: ArtifactReference
    s10_wheel_ref: ArtifactReference
    source_cycle: CycleRef
    created_at: datetime

    @model_validator(mode="after")
    def validate_cycle_alignment(self) -> "S10InputBundle":
        if self.source_cycle != self.feedback_effectiveness_input.evaluation_cycle:
            raise ValueError("source cycle and feedback evaluation cycle must match")
        if self.s9_execution_envelope.payload.created_at > self.created_at:
            raise ValueError("S10 cannot be created before the S9 execution bundle")
        return self

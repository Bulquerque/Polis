from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import EvidenceQuality

from ..enums import (
    CausalStatus,
    MemoryUpdateState,
    OutcomeMaturity,
    P3ContextCategory,
    P3ContextState,
    ResearchItemState,
    ResearchItemType,
)
from ..hashing import sha256_hex
from .common import (
    CycleRef,
    EvidenceReference,
    LongText,
    MemoryItemId,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcTimestampedModel,
)


class ResearchScope(StrictModel):
    phases: tuple[NonEmptyStr, ...] = ()
    policy_ids: tuple[NonEmptyStr, ...] = ()
    regimes: tuple[NonEmptyStr, ...] = ()
    asset_families: tuple[NonEmptyStr, ...] = ()


class ResearchClaimCandidate(StrictModel):
    candidate_id: NonEmptyStr
    semantic_key: NonEmptyStr
    claim: LongText
    abstract_claim: LongText
    scope: ResearchScope
    item_type_hint: ResearchItemType | None = None
    outcome_maturity: OutcomeMaturity
    causal_status: CausalStatus
    evidence_for: tuple[EvidenceReference, ...]
    evidence_against: tuple[EvidenceReference, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    materiality: float = Field(ge=0.0)
    validity_start: CycleRef
    expires_after_cycle: CycleRef | None = None
    source_cycles: tuple[CycleRef, ...]
    supersedes_semantic_keys: tuple[NonEmptyStr, ...] = ()
    contradicts_semantic_keys: tuple[NonEmptyStr, ...] = ()
    contains_future_outcome_identifiers: bool = False
    contains_private_leaderboard_data: bool = False
    contains_promoted_parameters: bool = False
    contains_direct_patch_instruction: bool = False
    contains_asset_specific_future_return: bool = False

    @model_validator(mode="after")
    def validate_candidate(self) -> "ResearchClaimCandidate":
        if not self.evidence_for and not self.evidence_against:
            raise ValueError("research claims require evidence for or against")
        if not self.source_cycles:
            raise ValueError("research claims require source cycles")
        if self.expires_after_cycle is not None:
            if self.expires_after_cycle.ordinal < self.validity_start.ordinal:
                raise ValueError("research claim cannot expire before validity start")
        if self.semantic_key in self.supersedes_semantic_keys:
            raise ValueError("research claim cannot supersede itself")
        if self.semantic_key in self.contradicts_semantic_keys:
            raise ValueError("research claim cannot contradict itself")
        return self


class ResearchNormalizationPolicy(StrictModel):
    policy_id: NonEmptyStr
    supported_lesson_confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    conditional_lesson_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    plausible_hypothesis_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    rejected_hypothesis_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    minimum_materiality: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ResearchNormalizationPolicy":
        if self.supported_lesson_confidence < self.conditional_lesson_confidence:
            raise ValueError("supported lesson threshold must be at least conditional threshold")
        if self.conditional_lesson_confidence < self.plausible_hypothesis_confidence:
            raise ValueError("conditional threshold must be at least hypothesis threshold")
        return self


class ResearchMemoryItem(StrictModel):
    item_id: MemoryItemId
    semantic_key: NonEmptyStr
    item_type: ResearchItemType
    state: ResearchItemState
    claim: LongText
    abstract_claim: LongText
    scope: ResearchScope
    causal_status: CausalStatus
    evidence_for: tuple[EvidenceReference, ...]
    evidence_against: tuple[EvidenceReference, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    materiality: float = Field(ge=0.0)
    validity_start: CycleRef
    expires_after_cycle: CycleRef | None = None
    source_cycles: tuple[CycleRef, ...]
    supersedes_item_ids: tuple[MemoryItemId, ...] = ()
    contradicts_item_ids: tuple[MemoryItemId, ...] = ()
    export_blocked: bool = False
    export_block_reasons: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_memory_item(self) -> "ResearchMemoryItem":
        if not self.evidence_for and not self.evidence_against:
            raise ValueError("memory items require evidence")
        if self.export_blocked and not self.export_block_reasons:
            raise ValueError("blocked exports require reason codes")
        if self.item_id in self.supersedes_item_ids or self.item_id in self.contradicts_item_ids:
            raise ValueError("memory item cannot reference itself")
        return self


class MaturedLessonPanel(StrictModel):
    items: tuple[ResearchMemoryItem, ...]


class ResearchHypothesisPanel(StrictModel):
    items: tuple[ResearchMemoryItem, ...]


class NegativeResearchMemoryPanel(StrictModel):
    items: tuple[ResearchMemoryItem, ...]


class NormalizedResearchMemoryBundle(StrictModel):
    policy_id: NonEmptyStr
    matured_lessons: MaturedLessonPanel
    research_hypotheses: ResearchHypothesisPanel
    negative_memory: NegativeResearchMemoryPanel
    skipped_candidate_ids: tuple[NonEmptyStr, ...] = ()
    merged_candidate_ids: tuple[NonEmptyStr, ...] = ()
    warnings: tuple[LongText, ...] = ()

    @model_validator(mode="after")
    def validate_unique_items(self) -> "NormalizedResearchMemoryBundle":
        items = (
            self.matured_lessons.items
            + self.research_hypotheses.items
            + self.negative_memory.items
        )
        ids = [item.item_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("normalized memory item IDs must be unique")
        return self


class ResearchMemorySnapshot(StrictModel):
    memory_id: NonEmptyStr
    generation: int = Field(ge=0)
    previous_snapshot_sha256: Sha256Hex | None = None
    items: tuple[ResearchMemoryItem, ...] = ()
    snapshot_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_snapshot_hash(self) -> "ResearchMemorySnapshot":
        payload = {
            "memory_id": self.memory_id,
            "generation": self.generation,
            "previous_snapshot_sha256": self.previous_snapshot_sha256,
            "items": self.items,
        }
        if self.snapshot_sha256 != sha256_hex(payload):
            raise ValueError("research memory snapshot hash mismatch")
        return self


class ResearchMemoryUpdatePolicy(StrictModel):
    policy_id: NonEmptyStr
    maximum_active_items: int = Field(default=10000, ge=1)
    p3_schema_version: NonEmptyStr = "1.0.0"
    maximum_p3_items: int = Field(default=64, ge=0)
    forbidden_text_fragments: tuple[NonEmptyStr, ...] = (
        "private leaderboard",
        "future return",
        "direct code patch",
        "promoted parameter",
    )


class SystemResearchMemoryUpdate(StrictModel):
    state: MemoryUpdateState
    previous_snapshot_sha256: Sha256Hex | None
    memory_snapshot: ResearchMemorySnapshot
    added_item_ids: tuple[MemoryItemId, ...] = ()
    superseded_item_ids: tuple[MemoryItemId, ...] = ()
    unchanged_item_ids: tuple[MemoryItemId, ...] = ()
    warnings: tuple[LongText, ...] = ()


class P3ResearchContextItem(StrictModel):
    context_item_id: NonEmptyStr
    category: P3ContextCategory
    abstract_claim: LongText
    uncertainty: LongText
    research_question: LongText
    scope: ResearchScope
    source_memory_item_id: MemoryItemId
    evidence_quality: EvidenceQuality
    world_memory_write_allowed: bool = False

    @model_validator(mode="after")
    def enforce_context_only(self) -> "P3ResearchContextItem":
        if self.world_memory_write_allowed:
            raise ValueError("P3 research context cannot authorize world-memory writes")
        return self


class P3ResearchContextHandoff(StrictModel):
    contract_name: NonEmptyStr = "P9_RESEARCH_CONTEXT_HANDOFF_V1"
    contract_version: NonEmptyStr = "1.0.0"
    destination: NonEmptyStr = "P3_RESEARCH_CONTEXT_ONLY"
    state: P3ContextState
    context_items: tuple[P3ResearchContextItem, ...]
    blocked_memory_item_ids: tuple[MemoryItemId, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    world_memory_write_allowed: bool = False

    @model_validator(mode="after")
    def validate_handoff(self) -> "P3ResearchContextHandoff":
        if self.destination != "P3_RESEARCH_CONTEXT_ONLY":
            raise ValueError("P3 handoff destination must be research context only")
        if self.world_memory_write_allowed:
            raise ValueError("P3 handoff cannot write to world memory")
        if self.state == P3ContextState.P3_CONTEXT_READY and not self.context_items:
            raise ValueError("ready P3 context requires items")
        return self


class P3ContextHandoffManifest(UtcTimestampedModel):
    manifest_id: NonEmptyStr
    source_memory_snapshot_sha256: Sha256Hex
    handoff_sha256: Sha256Hex
    contract_name: NonEmptyStr
    contract_version: NonEmptyStr
    context_item_ids: tuple[NonEmptyStr, ...]
    blocked_memory_item_ids: tuple[MemoryItemId, ...]
    created_at: datetime


class MemoryAndP3HandoffOutput(StrictModel):
    memory_update: SystemResearchMemoryUpdate
    p3_handoff: P3ResearchContextHandoff
    p3_manifest: P3ContextHandoffManifest

"""Canonical outputs of P8.S1 modules."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel
from .common import ArtifactConsumptionReceipt, ArtifactReference, ModuleReceipt
from .enums import (
    CandidateTerminalState,
    EvidenceResolutionStatus,
    NoActionReason,
    ReceiptStatus,
    RuntimeMode,
)
from .p5 import P5BeliefEvidenceBundleV1
from .p6 import P6CandidateEconomicPackageV1
from .p7 import P7RankingHandoffV1
from .p9 import PromotedFeedback
from .state import CurrentPortfolioAndAccountState


class CompatibilityDecision(StrictModel):
    contract_mode: Literal["FULL_NATIVE", "COMPATIBILITY_ADAPTER"]
    adapter_id: NonEmptyStr | None = None


class ValidatedP7HandoffBundle(StrictModel):
    handoff: P7RankingHandoffV1
    compatibility: CompatibilityDecision
    declared_artifact_refs: tuple[ArtifactReference, ...]
    artifact_receipts: tuple[ArtifactConsumptionReceipt, ...]


class CandidateTerminalRecord(StrictModel):
    candidate_id: NonEmptyStr
    canonical_candidate_id: NonEmptyStr | None = None
    terminal_state: CandidateTerminalState
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    comparison_group_id: NonEmptyStr | None = None
    rank: int | None = Field(default=None, ge=1, strict=True)
    p6_economic_package_ref: ArtifactReference | None = None


class CandidateConservationProof(StrictModel):
    received_count: int = Field(ge=0, strict=True)
    ranked_count: int = Field(ge=0, strict=True)
    eligibility_blocked_count: int = Field(ge=0, strict=True)
    safety_blocked_count: int = Field(ge=0, strict=True)
    abstained_count: int = Field(ge=0, strict=True)
    received_ids_hash: SHA256Str
    terminal_ids_hash: SHA256Str
    equation_valid: bool


class CandidateTerminalStateLedger(StrictModel):
    records: tuple[CandidateTerminalRecord, ...]
    proof: CandidateConservationProof


class ResolvedArtifactReceipt(StrictModel):
    reference: ArtifactReference
    status: EvidenceResolutionStatus
    resolved_size_bytes: int | None = Field(default=None, ge=0, strict=True)
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class ResolvedCandidateEvidence(StrictModel):
    candidate_id: NonEmptyStr
    status: EvidenceResolutionStatus
    p6_package: P6CandidateEconomicPackageV1 | None = None
    p5_belief_bundle: P5BeliefEvidenceBundleV1 | None = None
    reference_receipts: tuple[ResolvedArtifactReceipt, ...] = Field(default_factory=tuple)


class ResolvedCandidateEvidenceIndex(StrictModel):
    candidates: tuple[ResolvedCandidateEvidence, ...]
    handoff_artifact_receipts: tuple[ResolvedArtifactReceipt, ...] = Field(default_factory=tuple)
    full_lineage_resolution: bool


class FeedbackItemReceipt(StrictModel):
    feedback_id: NonEmptyStr
    status: ReceiptStatus
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class PromotedPortfolioFeedbackContext(StrictModel):
    current_cycle_id: NonEmptyStr
    current_cycle_sequence: int = Field(ge=0, strict=True)
    applied_feedback: tuple[PromotedFeedback, ...] = Field(default_factory=tuple)
    item_receipts: tuple[FeedbackItemReceipt, ...] = Field(default_factory=tuple)


class CandidateConsumptionRecord(StrictModel):
    candidate_id: NonEmptyStr
    status: ReceiptStatus
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class Phase7ConsumptionReceipt(StrictModel):
    handoff_id: NonEmptyStr
    candidate_receipts: tuple[CandidateConsumptionRecord, ...]
    handoff_hash: SHA256Str


class NoActionState(StrictModel):
    reason: NoActionReason
    preserved_portfolio_state_hash: SHA256Str
    candidate_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class P8DecisionSnapshot(StrictModel):
    snapshot_id: NonEmptyStr
    contract_version: Literal["P8_DECISION_SNAPSHOT_V1"]
    schema_version: Literal["1.0.0"]
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: AwareDatetime
    market_cutoff_at: AwareDatetime
    runtime_mode: RuntimeMode
    phase7_handoff_hash: SHA256Str
    candidate_ledger_hash: SHA256Str
    resolved_evidence_hash: SHA256Str
    feedback_context_hash: SHA256Str
    portfolio_state_hash: SHA256Str
    market_snapshot_ref: ArtifactReference
    received_candidate_ids: tuple[NonEmptyStr, ...]
    ranked_candidate_ids: tuple[NonEmptyStr, ...]
    terminal_candidate_ids: tuple[NonEmptyStr, ...]
    actionable_ranked_candidate_ids: tuple[NonEmptyStr, ...]
    no_action: NoActionState | None = None
    content_sha256: SHA256Str


class M01Result(StrictModel):
    bundle: ValidatedP7HandoffBundle
    receipt: ModuleReceipt


class M02Result(StrictModel):
    ledger: CandidateTerminalStateLedger
    receipt: ModuleReceipt


class M03Result(StrictModel):
    evidence_index: ResolvedCandidateEvidenceIndex
    receipt: ModuleReceipt


class M04Result(StrictModel):
    feedback_context: PromotedPortfolioFeedbackContext
    receipt: ModuleReceipt


class M05Result(StrictModel):
    current_state: CurrentPortfolioAndAccountState
    receipt: ModuleReceipt


class M06Result(StrictModel):
    snapshot: P8DecisionSnapshot
    phase7_consumption_receipt: Phase7ConsumptionReceipt
    receipt: ModuleReceipt

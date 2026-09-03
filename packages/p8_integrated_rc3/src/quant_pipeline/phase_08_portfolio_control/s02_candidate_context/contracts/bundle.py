
"""Input boundary and downstream bundle contracts for P8.S2."""

from __future__ import annotations

from typing import Literal

from quant_pipeline.phase_08_contracts.base import NonEmptyStr, SHA256Str, StrictModel
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateTerminalStateLedger,
    P8DecisionSnapshot,
    PromotedPortfolioFeedbackContext,
    ResolvedCandidateEvidenceIndex,
    ValidatedP7HandoffBundle,
)
from quant_pipeline.phase_08_contracts.state import CurrentPortfolioAndAccountState

from .equivalence import ExactEquivalenceGroupPanel, SoftSimilarityRequestPanel
from .graph import StructuralExposureGraph
from .intent import NormalizedCandidateIntentPanel
from .netting import NettingTransform
from .preferences import OrdinalPreferenceConstraintSet
from .universe import StaticAdmissibleActionUniverse


class S2InputBundleV1(StrictModel):
    contract_version: Literal["P8_S2_INPUT_BUNDLE_V1"]
    schema_version: Literal["1.0.0"]
    validated_handoff: ValidatedP7HandoffBundle
    terminal_ledger: CandidateTerminalStateLedger
    resolved_evidence: ResolvedCandidateEvidenceIndex
    feedback_context: PromotedPortfolioFeedbackContext
    current_state: CurrentPortfolioAndAccountState
    snapshot: P8DecisionSnapshot
    content_sha256: SHA256Str


class P8CandidateContextBundleV1(StrictModel):
    contract_version: Literal["P8_CANDIDATE_CONTEXT_BUNDLE_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    snapshot_hash: SHA256Str
    normalized_intents: NormalizedCandidateIntentPanel
    exposure_graph: StructuralExposureGraph
    equivalence_groups: ExactEquivalenceGroupPanel
    soft_similarity_requests: SoftSimilarityRequestPanel
    netting_transform: NettingTransform
    static_action_universe: StaticAdmissibleActionUniverse
    ordinal_preferences: OrdinalPreferenceConstraintSet
    content_sha256: SHA256Str

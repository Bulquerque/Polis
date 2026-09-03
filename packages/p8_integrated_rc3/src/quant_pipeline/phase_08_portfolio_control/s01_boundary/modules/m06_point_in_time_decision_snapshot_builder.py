"""P8.S1.M06 — seal the immutable point-in-time decision snapshot."""

from __future__ import annotations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, finalize_content_hash
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import (
    CandidateTerminalState,
    EvidenceResolutionStatus,
    NoActionReason,
    ReceiptStatus,
    StateQualityStatus,
)
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateConsumptionRecord,
    M01Result,
    M02Result,
    M03Result,
    M04Result,
    M05Result,
    M06Result,
    NoActionState,
    P8DecisionSnapshot,
    Phase7ConsumptionReceipt,
)

from ..context import S1ExecutionContext
from ..errors import LineageIntegrityError, StateInvariantError, TemporalIntegrityError
from ..module_support import build_receipt, read_verified_artifact
from ..ports import ArtifactStorePort

MODULE_ID = "P8.S1.M06"
_HASH_EXCLUDE = frozenset({"content_sha256"})


def _require_available(reference: ArtifactReference, *, context: S1ExecutionContext) -> None:
    if reference.available_at > context.decision_time:
        raise TemporalIntegrityError(f"artifact unavailable at decision_time: {reference.artifact_id}")


def run_module(
    m01: M01Result,
    m02: M02Result,
    m03: M03Result,
    m04: M04Result,
    m05: M05Result,
    *,
    market_snapshot_ref: ArtifactReference,
    store: ArtifactStorePort,
    context: S1ExecutionContext,
) -> M06Result:
    handoff = m01.bundle.handoff
    if handoff.available_at > context.decision_time:
        raise TemporalIntegrityError("P7 handoff was unavailable when snapshot was sealed")
    if handoff.run_id != context.run_id or handoff.cycle_id != context.cycle_id:
        raise StateInvariantError("P7 handoff run/cycle does not match P8 context")
    if handoff.market_cutoff_at > context.market_cutoff_at:
        raise TemporalIntegrityError("P7 market cutoff exceeds P8 market cutoff")
    _require_available(market_snapshot_ref, context=context)
    if market_snapshot_ref.artifact_type != "P2_TO_P8_MARKET_EXECUTION_SNAPSHOT_V1":
        raise StateInvariantError("market snapshot has unexpected artifact_type")
    read_verified_artifact(store, market_snapshot_ref, decision_time=context.decision_time)
    if m05.current_state.quality_report.status is StateQualityStatus.BLOCKED:
        raise StateInvariantError("portfolio/account state is blocked")
    ranked_ids = tuple(
        record.candidate_id
        for record in m02.ledger.records
        if record.terminal_state is CandidateTerminalState.RANKED
    )
    terminal_ids = tuple(
        record.candidate_id
        for record in m02.ledger.records
        if record.terminal_state is not CandidateTerminalState.RANKED
    )
    evidence_by_candidate = {row.candidate_id: row for row in m03.evidence_index.candidates}
    unresolved_ranked = [
        candidate_id
        for candidate_id in ranked_ids
        if candidate_id not in evidence_by_candidate
        or evidence_by_candidate[candidate_id].status
        not in {EvidenceResolutionStatus.RESOLVED, EvidenceResolutionStatus.ADAPTED_LOSSLESS}
    ]
    if unresolved_ranked:
        raise LineageIntegrityError(f"ranked candidates lack resolved evidence: {unresolved_ranked}")
    actionable = tuple(sorted(ranked_ids))
    portfolio_hash = canonical_sha256(m05.current_state)
    no_action = None
    if not actionable:
        no_action = NoActionState(
            reason=NoActionReason.NO_RANKED_CANDIDATES,
            preserved_portfolio_state_hash=portfolio_hash,
            candidate_ids=tuple(sorted(handoff.received_candidate_ids)),
        )
    component_hashes = {
        "handoff": canonical_sha256(m01.bundle),
        "ledger": canonical_sha256(m02.ledger),
        "evidence": canonical_sha256(m03.evidence_index),
        "feedback": canonical_sha256(m04.feedback_context),
        "portfolio": portfolio_hash,
        "market": market_snapshot_ref.content_sha256,
    }
    snapshot_seed = canonical_sha256((context.run_id, context.cycle_id, tuple(component_hashes.values())))
    provisional = P8DecisionSnapshot(
        snapshot_id=f"p8s1-{snapshot_seed[:24]}",
        contract_version="P8_DECISION_SNAPSHOT_V1",
        schema_version="1.0.0",
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        market_cutoff_at=context.market_cutoff_at,
        runtime_mode=context.runtime_mode,
        phase7_handoff_hash=component_hashes["handoff"],
        candidate_ledger_hash=component_hashes["ledger"],
        resolved_evidence_hash=component_hashes["evidence"],
        feedback_context_hash=component_hashes["feedback"],
        portfolio_state_hash=component_hashes["portfolio"],
        market_snapshot_ref=market_snapshot_ref,
        received_candidate_ids=tuple(sorted(handoff.received_candidate_ids)),
        ranked_candidate_ids=tuple(sorted(ranked_ids)),
        terminal_candidate_ids=tuple(sorted(terminal_ids)),
        actionable_ranked_candidate_ids=actionable,
        no_action=no_action,
        content_sha256="0" * 64,
    )
    snapshot = finalize_content_hash(provisional)
    candidate_receipts = tuple(
        CandidateConsumptionRecord(
            candidate_id=record.candidate_id,
            status=(
                ReceiptStatus.SEMANTICALLY_CONSUMED
                if record.terminal_state is CandidateTerminalState.RANKED
                else ReceiptStatus.PRESERVED_TERMINAL
            ),
            reason_codes=record.reason_codes,
        )
        for record in m02.ledger.records
    )
    phase7_receipt = Phase7ConsumptionReceipt(
        handoff_id=handoff.handoff_id,
        candidate_receipts=candidate_receipts,
        handoff_hash=component_hashes["handoff"],
    )
    receipt = build_receipt(
        module_id=MODULE_ID,
        status=ReceiptStatus.SEMANTICALLY_CONSUMED,
        inputs=(
            m01.bundle,
            m02.ledger,
            m03.evidence_index,
            m04.feedback_context,
            m05.current_state,
            market_snapshot_ref,
        ),
        output=(snapshot, phase7_receipt),
        computed_at=context.computed_at,
    )
    return M06Result(snapshot=snapshot, phase7_consumption_receipt=phase7_receipt, receipt=receipt)

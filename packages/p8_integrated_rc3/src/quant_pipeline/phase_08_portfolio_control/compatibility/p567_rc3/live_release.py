"""Build a conservative same-run P8→P9 LIMITED release from the P5/P6/P7 bridge.

This path is deliberately a no-action compatibility lane.  It preserves real
candidate identities and lineage but does not pretend that P8 optimization,
orders, fills, NAV or drawdown have run.  Those missing authorities keep P9 in
LIMITED mode until the operational P8 S3-S10 chain supplies FULL evidence.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Iterable

from quant_pipeline.phase_08_contracts.common import ArtifactReference

from ...subphases.s10_audit_release.enums import (
    CandidateTerminalState,
    CycleTerminalState,
    EvidenceClass,
    ImplementationRobustness,
    OutcomeMaturityHint,
    PnLQuality,
    ReasonCode,
    StatisticalQualification,
    TechnicalValidity,
)
from ...subphases.s10_audit_release.models_common import (
    ArtifactRef,
    AuditContext,
    content_sha256,
)
from ...subphases.s10_audit_release.models_handoff import (
    CandidateLineage,
    EvaluationCommitment,
    OutcomeEvidenceRecord,
    P9EvaluationHandoff,
    P9HandoffRequest,
)
from ...subphases.s10_audit_release.models_qualification import (
    QualificationDecision,
    StatisticalDiagnostics,
)
from ...subphases.s10_audit_release.models_state import (
    AccountSnapshot,
    CandidateStateRecord,
    PnLSnapshot,
    ReplayCheckpoint,
    StatefulEvidenceBundle,
)
from ...subphases.s10_audit_release.p9_handoff_builder import build_p9_handoff
from .models import P567RC3AdaptationResult


def _ref(value: ArtifactReference, *, phase: str, module: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=value.artifact_id,
        content_sha256=value.content_sha256,
        schema_version=value.schema_version,
        contract_version=value.contract_version,
        producer_phase=phase,
        producer_module=module,
    )


def _source_ref(result: P567RC3AdaptationResult, phase: str) -> ArtifactRef:
    for record in result.adaptation_receipt.source_artifacts:
        if record.source_phase == phase:
            return _ref(record.wrapped_reference, phase=phase, module=f"{phase}.EXTERNAL.AUTHORITY")
    raise ValueError(f"adaptation receipt has no {phase} source artifact")


def _p6_ref_by_candidate(result: P567RC3AdaptationResult) -> dict[str, ArtifactRef]:
    refs: dict[str, ArtifactRef] = {}
    for record in result.handoff.ranked:
        refs[record.candidate_id] = _ref(
            record.p6_economic_package_ref, phase="P6", module="P6.S10.M01"
        )
    for group in (result.handoff.eligibility_blocked, result.handoff.safety_blocked, result.handoff.abstained):
        for record in group:
            refs[record.candidate_id] = _ref(
                record.p6_economic_package_ref, phase="P6", module="P6.S10.M01"
            )
    return refs


def _terminal_states(result: P567RC3AdaptationResult) -> dict[str, CandidateTerminalState]:
    states = {candidate_id: CandidateTerminalState.RANKED for candidate_id in result.adaptation_receipt.ranked_candidate_ids}
    states.update({candidate_id: CandidateTerminalState.BLOCKED for candidate_id in result.adaptation_receipt.eligibility_blocked_candidate_ids})
    states.update({candidate_id: CandidateTerminalState.RISK_BLOCKED for candidate_id in result.adaptation_receipt.safety_blocked_candidate_ids})
    states.update({candidate_id: CandidateTerminalState.ABSTAINED for candidate_id in result.adaptation_receipt.abstained_candidate_ids})
    missing = set(result.adaptation_receipt.received_candidate_ids) - set(states)
    if missing:
        raise ValueError(f"P7 terminal states do not cover received candidates: {sorted(missing)}")
    return states


def build_limited_p9_release(
    result: P567RC3AdaptationResult,
    *,
    audit_time: datetime | None = None,
) -> tuple[P9EvaluationHandoff, StatefulEvidenceBundle]:
    decision_time = result.handoff.available_at.astimezone(UTC)
    audit_at = (audit_time or (decision_time + timedelta(seconds=1))).astimezone(UTC)
    if audit_at < decision_time:
        raise ValueError("audit_time cannot precede the P8 compatibility decision")
    context = AuditContext(
        run_id=result.handoff.run_id,
        cycle_id=result.handoff.cycle_id,
        trace_id=f"p567-p8-limited-{result.adaptation_receipt.content_sha256[:16]}",
        decision_time=decision_time,
        audit_time=audit_at,
    )
    candidate_ids = tuple(result.adaptation_receipt.received_candidate_ids)
    states = _terminal_states(result)
    p5_source = _source_ref(result, "P5")
    p7_source = _source_ref(result, "P7")
    p8_decision = _ref(
        result.adaptation_receipt_ref,
        phase="P8",
        module="P8.P567_RC3.BRIDGE",
    )
    p6_refs = _p6_ref_by_candidate(result)
    lineage: list[CandidateLineage] = []
    evidence: list[OutcomeEvidenceRecord] = []
    for candidate_id in candidate_ids:
        package = result.p6_packages[candidate_id]
        p5_ref = _ref(package.p5_belief_bundle_ref, phase="P5", module="P5.S9.M05")
        p6_ref = p6_refs[candidate_id]
        lineage.append(CandidateLineage(
            candidate_id=candidate_id,
            p4_view_refs=(),
            p5_belief_refs=(p5_ref,),
            p6_candidate_ref=p6_ref,
            p7_decision_ref=p7_source,
            p8_decision_ref=p8_decision,
        ))
        evidence.append(OutcomeEvidenceRecord(
            evidence_id=f"p8-limited-{sha256(candidate_id.encode()).hexdigest()[:20]}",
            candidate_id=candidate_id,
            evidence_class=EvidenceClass.UNOBSERVABLE,
            maturity_hint=OutcomeMaturityHint.EXPECTED_NOT_MATURED,
            expected_maturity_at=None,
            artifact_refs=(p6_ref, p7_source, p8_decision),
        ))

    qualification = QualificationDecision(
        qualification_id=f"p8-limited-{result.adaptation_receipt.content_sha256[:20]}",
        context=context,
        terminal_state=CycleTerminalState.NO_ACTION_VALID,
        technical_validity=TechnicalValidity.PASS,
        implementation_robustness=ImplementationRobustness.INSUFFICIENT_EVIDENCE,
        statistical_qualification=StatisticalQualification.NOT_APPLICABLE,
        diagnostics=StatisticalDiagnostics(
            observation_count=0,
            sharpe_ratio=None,
            deflated_sharpe_ratio=None,
            probability_backtest_overfitting=None,
        ),
        reason_codes=(ReasonCode.ROBUSTNESS_EVIDENCE_MISSING,),
        eligible_for_p9_evaluation=False,
        production_promotion_allowed=False,
    )
    commitment = EvaluationCommitment(
        commitment_id=f"commitment-{result.adaptation_receipt.content_sha256[:20]}",
        committed_at=decision_time - timedelta(microseconds=1),
        outcome_definition="P8 operational outcome after explicit optimization and execution",
        evaluation_horizons=("NEXT_OPERATIONAL_CYCLE",),
        metrics=("NET_PNL", "DRAWDOWN", "IMPLEMENTATION_SHORTFALL"),
        benchmarks=("NO_ACTION",),
        policy_hashes=(result.adaptation_receipt.content_sha256,),
        holdout_constraints=("NO_CURRENT_CYCLE_FEEDBACK", "NO_SYNTHETIC_EXECUTION"),
    )
    source_artifacts = tuple(dict.fromkeys(
        [p5_source, _source_ref(result, "P6"), p7_source, p8_decision]
    ))
    handoff = build_p9_handoff(P9HandoffRequest(
        context=context,
        qualification=qualification,
        evaluation_commitment=commitment,
        all_candidate_ids=candidate_ids,
        evidence_records=tuple(evidence),
        lineage_records=tuple(lineage),
        audit_report_ref=p8_decision,
        runtime_evidence_ref=None,
        source_artifacts=source_artifacts,
        full_evidence=None,
    ))
    empty_replay_hash = content_sha256([])
    state = StatefulEvidenceBundle(
        bundle_id=f"p8-limited-state-{result.adaptation_receipt.content_sha256[:20]}",
        context=context,
        expected_candidate_ids=candidate_ids,
        candidate_states=tuple(
            CandidateStateRecord(candidate_id=candidate_id, terminal_state=states[candidate_id])
            for candidate_id in candidate_ids
        ),
        initial_positions=(),
        orders=(),
        fills=(),
        final_positions=(),
        virtual_allocations=(),
        ledger_entries=(),
        account_snapshot=AccountSnapshot(
            functional_currency="FUNCTIONAL",
            initial_cash=Decimal("0"),
            final_cash=Decimal("0"),
            margin_used=Decimal("0"),
            collateral_value=Decimal("0"),
            liabilities=Decimal("0"),
            initial_nav=Decimal("0"),
            external_cashflows=Decimal("0"),
        ),
        valuations=(),
        pnl_snapshot=PnLSnapshot(
            quality=PnLQuality.UNAVAILABLE,
            realized_pnl=None,
            unrealized_pnl=None,
            costs=None,
            total_pnl=None,
        ),
        replay_events=(),
        replay_checkpoint=ReplayCheckpoint(expected_state_sha256=empty_replay_hash),
        source_artifacts=source_artifacts,
    )
    return handoff, state

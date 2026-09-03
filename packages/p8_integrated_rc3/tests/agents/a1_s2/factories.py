
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, finalize_content_hash, raw_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactConsumptionReceipt, ArtifactReference
from quant_pipeline.phase_08_contracts.enums import (
    CandidateTerminalState,
    ComponentQualificationStatus,
    ConfidenceState,
    EvidenceResolutionStatus,
    ExerciseStyle,
    P7TerminalState,
    PositionSide,
    ProbabilityMeasure,
    ReceiptStatus,
    RuntimeMode,
    ScoreSemantics,
    SettlementType,
    StateQualityStatus,
)
from quant_pipeline.phase_08_contracts.p5 import HorizonSpec, P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import CandidateLegV1, P6CandidateEconomicPackageV1, UnitEconomicsV1
from quant_pipeline.phase_08_contracts.p7 import (
    ComparisonGroupRecord,
    P7RankingHandoffV1,
    P7TerminalCandidateRecord,
    RankedCandidateRecord,
)
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateConservationProof,
    CandidateTerminalRecord,
    CandidateTerminalStateLedger,
    CompatibilityDecision,
    P8DecisionSnapshot,
    PromotedPortfolioFeedbackContext,
    ResolvedCandidateEvidence,
    ResolvedCandidateEvidenceIndex,
    ValidatedP7HandoffBundle,
)
from quant_pipeline.phase_08_contracts.state import (
    CashBalance,
    CurrentPortfolioAndAccountState,
    PortfolioStateProjection,
    PositionRecord,
    StateQualityReport,
)
from quant_pipeline.phase_08_contracts.enums import HorizonUnit
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import build_s2_input_bundle
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.context import S2ExecutionContext

BASE = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)


def ref(artifact_id: str, artifact_type: str, *, salt: str | None = None) -> ArtifactReference:
    raw = (salt or artifact_id).encode()
    return ArtifactReference(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        schema_version="1.0.0",
        contract_version=artifact_type,
        content_sha256=raw_sha256(raw),
        available_at=BASE - timedelta(minutes=5),
    )


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    rank: int
    group_id: str = "group-1"
    canonical_candidate_id: str | None = None
    instrument_id: str = "OPT-ABC-100-C"
    side: PositionSide = PositionSide.LONG
    unit_quantity: Decimal = Decimal("1")
    multiplier: Decimal = Decimal("100")
    strike: Decimal = Decimal("100")
    expiration_days: int = 30
    p5_variant: str = "base"
    score_semantics: ScoreSemantics = ScoreSemantics.ORDINAL
    score_value: Decimal | None = None
    confidence_state: ConfidenceState = ConfidenceState.UNCALIBRATED
    entry_cost: Decimal = Decimal("250")
    maximum_loss: Decimal = Decimal("250")
    margin: Decimal = Decimal("250")
    payoff_status: ComponentQualificationStatus = ComponentQualificationStatus.QUALIFIED
    lifecycle_status: ComponentQualificationStatus = ComponentQualificationStatus.QUALIFIED
    candidate_family: str = "LONG_CALL"
    objective_family: str = "DIRECTIONAL_UPSIDE"
    underlying: str = "ABC"


def _p5(spec: CandidateSpec) -> P5BeliefEvidenceBundleV1:
    return P5BeliefEvidenceBundleV1(
        belief_state_id=f"belief-{spec.candidate_id}",
        target_id="ABC_RETURN",
        underlying_or_factor_id=spec.underlying,
        forecast_horizon=HorizonSpec(value=24, unit=HorizonUnit.HOURS),
        as_of_time=BASE - timedelta(minutes=10),
        decision_time=BASE - timedelta(minutes=8),
        resolver_id="resolver-1",
        model_artifact_id=f"model-{spec.p5_variant}",
        probability_measure=ProbabilityMeasure.PHYSICAL,
        forecast_distribution_ref=ref(f"forecast-{spec.p5_variant}", "P5_FORECAST_DISTRIBUTION", salt=spec.p5_variant),
        calibration_ref=ref(f"calibration-{spec.p5_variant}", "P5_CALIBRATION", salt="cal-"+spec.p5_variant),
        view_refs=(ref(f"view-{spec.p5_variant}", "P4_VIEW", salt="view-"+spec.p5_variant),),
    )


def _package(spec: CandidateSpec) -> tuple[P6CandidateEconomicPackageV1, P5BeliefEvidenceBundleV1]:
    p5 = _p5(spec)
    canonical_id = spec.canonical_candidate_id or f"canonical-{spec.candidate_id}"
    leg = CandidateLegV1(
        instrument_id=spec.instrument_id,
        instrument_type="OPTION",
        side=spec.side,
        unit_quantity=spec.unit_quantity,
        contract_multiplier=spec.multiplier,
        strike=spec.strike,
        expiration=BASE + timedelta(days=spec.expiration_days),
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
        contract_valid_from=BASE - timedelta(days=1),
        contract_valid_until=BASE + timedelta(days=spec.expiration_days),
        instrument_master_ref=ref(f"instrument-{spec.instrument_id}", "P2_INSTRUMENT_MASTER", salt=spec.instrument_id),
    )
    package = P6CandidateEconomicPackageV1(
        candidate_id=spec.candidate_id,
        canonical_candidate_id=canonical_id,
        candidate_family=spec.candidate_family,
        objective_family=spec.objective_family,
        unit_definition="one normalized strategy unit",
        currency="USD",
        lot_size=Decimal("1"),
        quantity_increment=Decimal("1"),
        legs=(leg,),
        unit_economics=UnitEconomicsV1(
            entry_cost_status=ComponentQualificationStatus.QUALIFIED,
            payoff_status=spec.payoff_status,
            maximum_loss_status=ComponentQualificationStatus.QUALIFIED,
            liquidity_status=ComponentQualificationStatus.QUALIFIED,
            lifecycle_status=spec.lifecycle_status,
            unit_entry_cost=spec.entry_cost,
            unit_maximum_loss=spec.maximum_loss,
            margin_per_unit=spec.margin,
            liquidity_capacity_units=Decimal("50"),
        ),
        p5_belief_bundle_ref=ref(f"p5-{spec.candidate_id}", "P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1", salt=spec.p5_variant),
        lineage_refs=p5.view_refs,
    )
    return package, p5


def build_input(
    specs: tuple[CandidateSpec, ...] = (CandidateSpec("cand-1", 1),),
    *,
    terminal_candidates: tuple[tuple[str, P7TerminalState], ...] = (),
    positions: tuple[PositionRecord, ...] = (),
):
    ranked_rows=[]; evidences=[]; ledger_rows=[]; artifact_refs=[]
    groups: dict[str, list[CandidateSpec]] = {}
    for spec in specs:
        package,p5=_package(spec)
        canonical_id=package.canonical_candidate_id
        p6_ref=ref(f"p6-{spec.candidate_id}", "P6_CANDIDATE_ECONOMIC_PACKAGE_V1", salt=canonical_sha256(package))
        trace_ref=ref(f"trace-{spec.candidate_id}", "P7_DECISION_TRACE")
        calibration_ref = ref(f"conf-cal-{spec.candidate_id}", "P7_CONFIDENCE_CALIBRATION") if spec.confidence_state is ConfidenceState.CALIBRATED else None
        ranked_rows.append(RankedCandidateRecord(
            candidate_id=spec.candidate_id,
            canonical_candidate_id=canonical_id,
            comparison_group_id=spec.group_id,
            rank=spec.rank,
            score_semantics=spec.score_semantics,
            score_value=spec.score_value,
            confidence_state=spec.confidence_state,
            confidence_calibration_ref=calibration_ref,
            p6_economic_package_ref=p6_ref,
            decision_trace_ref=trace_ref,
        ))
        ledger_rows.append(CandidateTerminalRecord(
            candidate_id=spec.candidate_id,
            canonical_candidate_id=canonical_id,
            terminal_state=CandidateTerminalState.RANKED,
            comparison_group_id=spec.group_id,
            rank=spec.rank,
            p6_economic_package_ref=p6_ref,
        ))
        evidences.append(ResolvedCandidateEvidence(
            candidate_id=spec.candidate_id,
            status=EvidenceResolutionStatus.RESOLVED,
            p6_package=package,
            p5_belief_bundle=p5,
        ))
        artifact_refs.extend((p6_ref,trace_ref))
        if calibration_ref: artifact_refs.append(calibration_ref)
        groups.setdefault(spec.group_id,[]).append(spec)
    terminal_rows=[]
    for candidate_id,state in terminal_candidates:
        terminal_rows.append(P7TerminalCandidateRecord(
            candidate_id=candidate_id,
            terminal_state=state,
            reason_codes=("P7_TERMINAL_FIXTURE",),
        ))
        ledger_rows.append(CandidateTerminalRecord(
            candidate_id=candidate_id,
            terminal_state=CandidateTerminalState(state.value),
            reason_codes=("P7_TERMINAL_FIXTURE",),
        ))
        evidences.append(ResolvedCandidateEvidence(
            candidate_id=candidate_id,
            status=EvidenceResolutionStatus.UNAVAILABLE,
        ))
    comparison_groups=[]
    for group_id,rows in sorted(groups.items()):
        comparison_groups.append(ComparisonGroupRecord(
            comparison_group_id=group_id,
            objective_family=rows[0].objective_family,
            underlying_scope=tuple(sorted({row.underlying for row in rows})),
            horizon_scope="24H",
            member_candidate_ids=tuple(sorted(row.candidate_id for row in rows)),
            comparability_policy_id="comparability-v1",
        ))
    received=tuple(sorted([s.candidate_id for s in specs]+[x[0] for x in terminal_candidates]))
    handoff=finalize_content_hash(P7RankingHandoffV1(
        handoff_id="p7-handoff-s2",
        contract_version="P7_TO_P8_RANKING_HANDOFF_V1",
        schema_version="1.0.0",
        producer_phase="P7",
        producer_release="0.30.0",
        run_id="run-s2",
        cycle_id="cycle-s2",
        decision_time=BASE-timedelta(minutes=5),
        market_cutoff_at=BASE-timedelta(minutes=5),
        computed_at=BASE-timedelta(minutes=4),
        recorded_at=BASE-timedelta(minutes=3),
        available_at=BASE-timedelta(minutes=2),
        content_sha256="0"*64,
        received_candidate_ids=received,
        ranked=tuple(ranked_rows),
        abstained=tuple(row for row in terminal_rows if row.terminal_state is P7TerminalState.ABSTAINED),
        eligibility_blocked=tuple(row for row in terminal_rows if row.terminal_state is P7TerminalState.ELIGIBILITY_BLOCKED),
        safety_blocked=tuple(row for row in terminal_rows if row.terminal_state is P7TerminalState.SAFETY_BLOCKED),
        comparison_groups=tuple(comparison_groups),
        artifact_refs=tuple(artifact_refs),
    ))
    validated=ValidatedP7HandoffBundle(
        handoff=handoff,
        compatibility=CompatibilityDecision(contract_mode="FULL_NATIVE"),
        declared_artifact_refs=tuple(artifact_refs),
        artifact_receipts=tuple(ArtifactConsumptionReceipt(
            artifact_id=r.artifact_id,
            artifact_type=r.artifact_type,
            status=ReceiptStatus.REFERENCE_DECLARED,
            consumer_module_id="P8.S1.M01",
            input_hash=r.content_sha256,
        ) for r in artifact_refs),
    )
    ranked_count=len(specs)
    states=[row.terminal_state for row in ledger_rows]
    ledger=CandidateTerminalStateLedger(
        records=tuple(sorted(ledger_rows,key=lambda row:row.candidate_id)),
        proof=CandidateConservationProof(
            received_count=len(received), ranked_count=ranked_count,
            eligibility_blocked_count=states.count(CandidateTerminalState.ELIGIBILITY_BLOCKED),
            safety_blocked_count=states.count(CandidateTerminalState.SAFETY_BLOCKED),
            abstained_count=states.count(CandidateTerminalState.ABSTAINED),
            received_ids_hash=canonical_sha256(received),
            terminal_ids_hash=canonical_sha256(received), equation_valid=True,
        ),
    )
    evidence=ResolvedCandidateEvidenceIndex(candidates=tuple(sorted(evidences,key=lambda row:row.candidate_id)),full_lineage_resolution=True)
    feedback=PromotedPortfolioFeedbackContext(current_cycle_id="cycle-s2",current_cycle_sequence=10)
    event_ref=ref("event-log-s2","P8_EVENT_LOG")
    projection=finalize_content_hash(PortfolioStateProjection(
        state_id="state-s2",as_of_time=BASE-timedelta(minutes=1),positions=positions,
        cash=(CashBalance(currency="USD",amount=Decimal("100000")),),
        event_log_ref=event_ref,replay_hash=raw_sha256(b"replay"),content_sha256="0"*64,
    ))
    current=CurrentPortfolioAndAccountState(
        portfolio_state=projection,
        quality_report=StateQualityReport(runtime_mode=RuntimeMode.BACKTEST,status=StateQualityStatus.USABLE_BACKTEST,external_snapshot_present=False),
    )
    snapshot=finalize_content_hash(P8DecisionSnapshot(
        snapshot_id="p8s1-s2fixture",contract_version="P8_DECISION_SNAPSHOT_V1",schema_version="1.0.0",
        run_id="run-s2",cycle_id="cycle-s2",decision_time=BASE,market_cutoff_at=BASE-timedelta(minutes=5),
        runtime_mode=RuntimeMode.BACKTEST,phase7_handoff_hash=canonical_sha256(validated),
        candidate_ledger_hash=canonical_sha256(ledger),resolved_evidence_hash=canonical_sha256(evidence),
        feedback_context_hash=canonical_sha256(feedback),portfolio_state_hash=canonical_sha256(current),
        market_snapshot_ref=ref("market-s2","P2_TO_P8_MARKET_EXECUTION_SNAPSHOT_V1"),
        received_candidate_ids=received,ranked_candidate_ids=tuple(sorted(s.candidate_id for s in specs)),
        terminal_candidate_ids=tuple(sorted(x[0] for x in terminal_candidates)),
        actionable_ranked_candidate_ids=tuple(sorted(s.candidate_id for s in specs)),content_sha256="0"*64,
    ))
    bundle=build_s2_input_bundle(
        validated_handoff=validated,terminal_ledger=ledger,resolved_evidence=evidence,
        feedback_context=feedback,current_state=current,snapshot=snapshot,
    )
    context=S2ExecutionContext(run_id="run-s2",cycle_id="cycle-s2",decision_time=BASE,computed_at=BASE+timedelta(seconds=1))
    return bundle,context



def replace_candidate_package(bundle, candidate_id: str, package: P6CandidateEconomicPackageV1):
    candidates=[]
    for evidence in bundle.resolved_evidence.candidates:
        candidates.append(evidence.model_copy(update={"p6_package":package}) if evidence.candidate_id==candidate_id else evidence)
    index=bundle.resolved_evidence.model_copy(update={"candidates":tuple(candidates)})
    snapshot=finalize_content_hash(bundle.snapshot.model_copy(update={"resolved_evidence_hash":canonical_sha256(index)}))
    return finalize_content_hash(bundle.model_copy(update={"resolved_evidence":index,"snapshot":snapshot}))


def replace_validated_handoff(bundle, handoff: P7RankingHandoffV1):
    handoff=finalize_content_hash(handoff.model_copy(update={"content_sha256":"0"*64}))
    validated=bundle.validated_handoff.model_copy(update={"handoff":handoff})
    snapshot=finalize_content_hash(bundle.snapshot.model_copy(update={"phase7_handoff_hash":canonical_sha256(validated)}))
    return finalize_content_hash(bundle.model_copy(update={"validated_handoff":validated,"snapshot":snapshot}))

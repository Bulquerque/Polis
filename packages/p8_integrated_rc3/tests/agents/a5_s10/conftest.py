from __future__ import annotations
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import (
    CandidateTerminalState, CycleTerminalState, EvidenceClass, LedgerCategory,
    MarkQuality, OrderSide, OutcomeMaturityHint, StatisticalQualification,
    TechnicalValidity, ImplementationRobustness,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_audit import IndependentAuditReport
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_common import ArtifactRef, AuditContext
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_handoff import (
    CandidateLineage, EvaluationCommitment, OutcomeEvidenceRecord, P9HandoffRequest,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_orchestration import AuditReleaseRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_qualification import (
    QualificationDecision, RobustnessEvidence, StatisticalDiagnostics, StatisticalEvidence,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import (
    AccountSnapshot, CandidateStateRecord, FillRecord, LedgerEntry, OrderRecord,
    PnLSnapshot, PositionRecord, ReplayCheckpoint, ReplayEvent, StatefulEvidenceBundle,
    ValuationRecord, VirtualAllocation,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.replay import replay_hash
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.p9_handoff_builder import build_p9_handoff

NOW=datetime(2026,8,3,15,0,tzinfo=timezone.utc)

def make_ref(name: str, phase: str='P8', module: str='P8.S8.M07') -> ArtifactRef:
    import hashlib
    return ArtifactRef(artifact_id=name, content_sha256=hashlib.sha256(name.encode()).hexdigest(),
        schema_version='1.0.0', contract_version='1.0.0', producer_phase=phase, producer_module=module)

@pytest.fixture
def ref():
    return make_ref

@pytest.fixture
def context() -> AuditContext:
    return AuditContext(run_id='run-1',cycle_id='cycle-1',trace_id='trace-1',
        decision_time=NOW,audit_time=NOW+timedelta(hours=1))

@pytest.fixture
def replay_events() -> tuple[ReplayEvent,...]:
    return (
        ReplayEvent(sequence=0,event_id='e0',event_type='POSITION',instrument_id='A',quantity_delta=Decimal('2')),
        ReplayEvent(sequence=1,event_id='e1',event_type='CASH',cash_delta=Decimal('-21')),
        ReplayEvent(sequence=2,event_id='e2',event_type='VIRTUAL_ALLOCATION',instrument_id='A',candidate_id='c1',quantity_delta=Decimal('2')),
    )

@pytest.fixture
def bundle(context, replay_events) -> StatefulEvidenceBundle:
    return StatefulEvidenceBundle(bundle_id='state-1',context=context,
        expected_candidate_ids=('c1','c2'),
        candidate_states=(CandidateStateRecord(candidate_id='c1',terminal_state=CandidateTerminalState.EXECUTED),
            CandidateStateRecord(candidate_id='c2',terminal_state=CandidateTerminalState.BLOCKED)),
        initial_positions=(PositionRecord(instrument_id='A',quantity=Decimal('0')),),
        orders=(OrderRecord(order_id='o1',instrument_id='A',side=OrderSide.BUY,total_quantity=Decimal('2'),
            filled_quantity=Decimal('2'),cancelled_quantity=Decimal('0'),rejected_quantity=Decimal('0'),open_quantity=Decimal('0')),),
        fills=(FillRecord(fill_id='f1',order_id='o1',instrument_id='A',side=OrderSide.BUY,
            quantity=Decimal('2'),price=Decimal('10'),fees=Decimal('1')),),
        final_positions=(PositionRecord(instrument_id='A',quantity=Decimal('2')),),
        virtual_allocations=(VirtualAllocation(candidate_id='c1',instrument_id='A',quantity=Decimal('2')),),
        ledger_entries=(
            LedgerEntry(entry_id='l1',category=LedgerCategory.PREMIUM,amount=Decimal('-20'),event_time=NOW),
            LedgerEntry(entry_id='l2',category=LedgerCategory.COST,amount=Decimal('-1'),event_time=NOW),
            LedgerEntry(entry_id='l3',category=LedgerCategory.MARGIN,amount=Decimal('5'),event_time=NOW),
        ),
        account_snapshot=AccountSnapshot(initial_cash=Decimal('1000'),final_cash=Decimal('979'),margin_used=Decimal('5'),
            collateral_value=Decimal('0'),liabilities=Decimal('0'),initial_nav=Decimal('1000')),
        valuations=(ValuationRecord(instrument_id='A',quantity=Decimal('2'),mark_price=Decimal('12'),
            market_value=Decimal('24'),mark_quality=MarkQuality.MID),),
        pnl_snapshot=PnLSnapshot(realized_pnl=Decimal('0'),unrealized_pnl=Decimal('4'),costs=Decimal('-1'),total_pnl=Decimal('3')),
        replay_events=replay_events,replay_checkpoint=ReplayCheckpoint(expected_state_sha256=replay_hash(replay_events)),
        source_artifacts=(make_ref('s1'),make_ref('s9',module='P8.S9.M05')))

@pytest.fixture
def robustness() -> RobustnessEvidence:
    return RobustnessEvidence(clean_replay_passed=True,clean_install_passed=True,clean_extraction_passed=True,
        consumer_contracts_passed=True,golden_threads_required=('NO_ACTION','EXECUTED'),
        golden_threads_passed=('NO_ACTION','EXECUTED'),perturbations_required=3,perturbations_passed=3)

@pytest.fixture
def statistical() -> StatisticalEvidence:
    returns=tuple(Decimal(str(x)) for x in [0.01,0.012,0.008,0.011,0.009]*8)
    matrix=tuple(tuple(Decimal(str(v)) for v in row) for row in [
        (0.01,0.005,-0.002),(0.012,0.004,-0.001),(0.008,0.006,0.0),(0.011,0.003,0.001),
        (0.009,0.005,-0.003),(0.013,0.002,0.001),(0.007,0.006,-0.001),(0.010,0.004,0.0),
        (0.012,0.003,-0.002),(0.008,0.005,0.001),(0.011,0.004,-0.001),(0.009,0.006,0.0),
    ])
    return StatisticalEvidence(returns=returns,periods_per_year=252,
        trial_sharpes=(Decimal('0.1'),Decimal('0.2'),Decimal('0.3')),strategy_returns=matrix,
        trial_registry_complete=True,holdout_preserved=True,minimum_observations=30,
        dsr_threshold=Decimal('0.1'),pbo_threshold=Decimal('1'))

@pytest.fixture
def dummy_qualification(context) -> QualificationDecision:
    return QualificationDecision(qualification_id='dummy',context=context,terminal_state=CycleTerminalState.EXECUTED_VALID,
        technical_validity=TechnicalValidity.PASS,implementation_robustness=ImplementationRobustness.PASS,
        statistical_qualification=StatisticalQualification.QUALIFIED,
        diagnostics=StatisticalDiagnostics(observation_count=40,sharpe_ratio=Decimal('1'),
            deflated_sharpe_ratio=Decimal('0.99'),probability_backtest_overfitting=Decimal('0.1')),
        reason_codes=(),eligible_for_p9_evaluation=True,production_promotion_allowed=False)

@pytest.fixture
def p9_template(context,dummy_qualification) -> P9HandoffRequest:
    execution=make_ref('fill-ref',module='P8.S7.M06')
    common=dict(p4_view_refs=(make_ref('p4','P4','P4.S1.M01'),),p5_belief_refs=(make_ref('p5','P5','P5.S1.M01'),),
        p6_candidate_ref=make_ref('p6','P6','P6.S1.M01'),p7_decision_ref=make_ref('p7','P7','P7.S1.M01'),
        p8_decision_ref=make_ref('p8','P8','P8.S5.M07'))
    return P9HandoffRequest(context=context,qualification=dummy_qualification,
        evaluation_commitment=EvaluationCommitment(commitment_id='ec1',committed_at=context.decision_time-timedelta(minutes=1),
            outcome_definition='portfolio net pnl after costs',evaluation_horizons=('1D','5D'),metrics=('NET_PNL','DRAWDOWN'),
            benchmarks=('CASH',),policy_hashes=('a'*64,),holdout_constraints=('NO_REUSE',)),
        all_candidate_ids=('c1','c2'),
        evidence_records=(OutcomeEvidenceRecord(evidence_id='ev1',candidate_id='c1',evidence_class=EvidenceClass.FACTUAL_EXECUTED,
                maturity_hint=OutcomeMaturityHint.EXPECTED_MATURED,artifact_refs=(execution,),execution_ref=execution),
            OutcomeEvidenceRecord(evidence_id='ev2',candidate_id='c2',evidence_class=EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
                maturity_hint=OutcomeMaturityHint.EXPECTED_MATURED,artifact_refs=(make_ref('obs'),))),
        lineage_records=(CandidateLineage(candidate_id='c1',**common,order_refs=(make_ref('o1'),),fill_refs=(execution,),position_refs=(make_ref('pos'),)),
            CandidateLineage(candidate_id='c2',**common)),
        audit_report_ref=make_ref('audit',module='P8.S10.M01'),runtime_evidence_ref=make_ref('runtime',module='P8.S9.M05'),
        source_artifacts=(make_ref('source'),))

@pytest.fixture
def p9_handoff(p9_template):
    return build_p9_handoff(p9_template)

@pytest.fixture
def orchestration_request(bundle,robustness,statistical,p9_template) -> AuditReleaseRequest:
    return AuditReleaseRequest(stateful_evidence=bundle,terminal_state=CycleTerminalState.EXECUTED_VALID,
        robustness=robustness,statistical=statistical,p9_request_template=p9_template)

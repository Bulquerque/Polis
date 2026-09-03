import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality
from quant_pipeline.phase_09.subphases.s08_attribution.m02_payoff_attribution import (
    CandidateOutcome, PayoffAttributionPolicy, PayoffScenarioPoint, evaluate_payoff_fidelity,
)


def _scenarios(candidate: str):
    return tuple(PayoffScenarioPoint(candidate_id=candidate, scenario_id=f"s{i}", target_payoff_per_unit=v, candidate_payoff_per_unit=v, probability_weight=1.0) for i,v in enumerate((-1.0,0.0,2.0)))


def test_payoff_regret_zero_when_selected_is_best():
    outcomes=(CandidateOutcome(candidate_id="a", selected_by_p6=True, observable=True, realized_unit_pnl=3.0, evidence_class=EvidenceClass.FACTUAL_EXECUTED), CandidateOutcome(candidate_id="b", selected_by_p6=False, observable=True, realized_unit_pnl=1.0, evidence_class=EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED))
    result=evaluate_payoff_fidelity(_scenarios("a")+_scenarios("b"), outcomes, PayoffAttributionPolicy())
    assert result.synthesis_regret == 0.0
    assert result.quality is AttributionQuality.QUALIFIED


def test_payoff_regret_detects_missed_candidate():
    outcomes=(CandidateOutcome(candidate_id="a", selected_by_p6=True, observable=True, realized_unit_pnl=1.0, evidence_class=EvidenceClass.FACTUAL_EXECUTED), CandidateOutcome(candidate_id="b", selected_by_p6=False, observable=True, realized_unit_pnl=4.0, evidence_class=EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED))
    result=evaluate_payoff_fidelity(_scenarios("a")+_scenarios("b"), outcomes, PayoffAttributionPolicy())
    assert result.synthesis_regret == 3.0
    assert result.aggregate_pnl_effect == -3.0


def test_incomplete_scenario_panel_is_insufficient():
    outcome=(CandidateOutcome(candidate_id="a", selected_by_p6=True, observable=True, realized_unit_pnl=1.0, evidence_class=EvidenceClass.FACTUAL_EXECUTED),)
    result=evaluate_payoff_fidelity(_scenarios("a")[:1], outcome, PayoffAttributionPolicy())
    assert result.quality is AttributionQuality.INSUFFICIENT_EVIDENCE


def test_estimate_actual_pair_must_be_complete():
    with pytest.raises(ValueError):
        CandidateOutcome(candidate_id="a", selected_by_p6=True, observable=True, realized_unit_pnl=1.0, estimated_cost=1.0, evidence_class=EvidenceClass.FACTUAL_EXECUTED)

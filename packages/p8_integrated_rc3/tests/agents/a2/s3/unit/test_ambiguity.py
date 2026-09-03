from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ActionabilityPolicy, QualityAssessment, QualityStatus, ReductionAssessment,
    ReductionStatus, ScenarioPolicy,
)
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.ambiguity_compiler import compile_ambiguity
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_materializer import materialize_scenarios


def quality(score, status):
    return QualityAssessment(status_by_family={"LINEAR": status}, score=score, metrics=())


def reduction(status=ReductionStatus.SAFE):
    return ReductionAssessment(status=status, original_count=32, output_count=8, mean_error=0,covariance_error=0,tail_error=0,transport_cost=0,decision_aware_status="CAPABILITY_UNAVAILABLE",content_sha256="a"*64)


def test_good_quality_nominal(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    result = compile_ambiguity(scenarios, quality(0.95,QualityStatus.FULLY_QUALIFIED), reduction(), 0.98,0.01,0.02,None,ActionabilityPolicy())
    assert result.actionability_state.value == "NOMINAL_ACTIONABLE"
    assert result.risk_budget_cap > 0.8


def test_higher_ood_never_increases_cap(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    low = compile_ambiguity(scenarios, quality(0.9,QualityStatus.FULLY_QUALIFIED), reduction(),0.9,0.1,0.1,None,ActionabilityPolicy())
    high = compile_ambiguity(scenarios, quality(0.9,QualityStatus.FULLY_QUALIFIED), reduction(),0.9,0.8,0.1,None,ActionabilityPolicy())
    assert high.risk_budget_cap <= low.risk_budget_cap
    assert high.liquidity_haircut >= low.liquidity_haircut


def test_ordinal_cap_only_caps_risk(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    base = compile_ambiguity(scenarios, quality(0.95,QualityStatus.FULLY_QUALIFIED), reduction(),0.95,0.05,0.05,None,ActionabilityPolicy())
    capped = compile_ambiguity(scenarios, quality(0.95,QualityStatus.FULLY_QUALIFIED), reduction(),0.95,0.05,0.05,0.2,ActionabilityPolicy())
    assert capped.risk_budget_cap == 0.2
    assert capped.probability_lower_bounds == base.probability_lower_bounds
    assert capped.probability_upper_bounds == base.probability_upper_bounds


def test_bad_quality_no_action(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    result = compile_ambiguity(scenarios, quality(0.0,QualityStatus.NOT_ACTIONABLE), reduction(),0.0,1.0,1.0,None,ActionabilityPolicy())
    assert result.actionability_state.value == "NO_ACTION_VALID"
    assert result.risk_budget_cap == 0.0


def test_unsafe_reduction_increases_uncertainty(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    safe = compile_ambiguity(scenarios, quality(0.9,QualityStatus.FULLY_QUALIFIED), reduction(),0.9,0.1,0.1,None,ActionabilityPolicy())
    unsafe = compile_ambiguity(scenarios, quality(0.9,QualityStatus.FULLY_QUALIFIED), reduction(ReductionStatus.SCENARIO_REDUCTION_UNSAFE),0.9,0.1,0.1,None,ActionabilityPolicy())
    assert unsafe.uncertainty_score >= safe.uncertainty_score

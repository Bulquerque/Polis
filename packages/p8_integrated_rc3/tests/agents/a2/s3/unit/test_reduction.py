import numpy as np

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import ReductionPolicy, ReductionStatus, ScenarioPolicy
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_materializer import materialize_scenarios
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_reduction import reduce_scenarios
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.ports import DecisionEvaluation


class MeanDecision:
    def evaluate(self, scenario_set):
        mean = np.average(scenario_set.values[:,-1,:], axis=0, weights=scenario_set.probabilities)
        return DecisionEvaluation(first_action=tuple(mean), objective=float(mean.sum()), risk_metrics={})


class UnstableDecision:
    def evaluate(self, scenario_set):
        action = (float(scenario_set.shape[0]),)
        return DecisionEvaluation(first_action=action, objective=0.0, risk_metrics={})


def test_reduces_count(normal_belief):
    full = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64, seed_entropy=2))
    policy = ReductionPolicy(target_count=16, mean_error_max=1, covariance_error_max=1, tail_error_max=1, first_action_tolerance=1)
    reduced, assessment = reduce_scenarios(full, policy, MeanDecision())
    assert assessment.status == ReductionStatus.SAFE
    assert reduced.shape[0] == 16
    assert np.isclose(reduced.probabilities.sum(),1.0)


def test_unstable_decision_falls_back(normal_belief):
    full = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64))
    policy = ReductionPolicy(target_count=8, mean_error_max=10, covariance_error_max=10, tail_error_max=10, first_action_tolerance=0)
    reduced, assessment = reduce_scenarios(full, policy, UnstableDecision())
    assert assessment.status == ReductionStatus.SCENARIO_REDUCTION_UNSAFE
    assert reduced.shape[0] == full.shape[0]


def test_no_port_marks_capability_unavailable(normal_belief):
    full = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    policy = ReductionPolicy(target_count=8, mean_error_max=10, covariance_error_max=10, tail_error_max=10)
    _, assessment = reduce_scenarios(full, policy)
    assert assessment.decision_aware_status == "CAPABILITY_UNAVAILABLE"


def test_target_above_count_returns_same(normal_belief):
    full = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=16))
    reduced, assessment = reduce_scenarios(full, ReductionPolicy(target_count=20))
    assert reduced is full
    assert assessment.output_count == 16


def test_tail_scenarios_preserved(normal_belief):
    full = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64, seed_entropy=11))
    flat = full.flattened()
    tail = set(np.argsort(np.linalg.norm(flat,axis=1))[-4:])
    reduced, _ = reduce_scenarios(full, ReductionPolicy(target_count=16,preserve_tail_count=4,mean_error_max=10,covariance_error_max=10,tail_error_max=10))
    selected = {full.scenario_ids.index(x) for x in reduced.scenario_ids}
    assert tail.issubset(selected)

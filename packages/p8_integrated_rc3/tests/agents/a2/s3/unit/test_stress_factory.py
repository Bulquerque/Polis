import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import ScenarioPolicy, StressPolicy, StressTemplate
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.errors import ContractIntegrityError
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_materializer import materialize_scenarios
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.stress_factory import build_stresses, find_reverse_stress
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.ports import RiskResponse


class ThresholdRisk:
    def evaluate(self, shock_vector):
        loss = -sum(shock_vector)
        failed = ("LOSS_LIMIT",) if loss >= 1.0 else ()
        return RiskResponse(loss=loss, margin=loss/2, liquidity=1.0, failure_states=failed)


def test_build_additive_stress(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    policy = StressPolicy(templates=(StressTemplate(stress_id="shock", factor_shocks={"A": -1.0}),))
    stresses = build_stresses(scenarios, policy)
    baseline = np.average(scenarios.values, axis=0, weights=scenarios.probabilities)
    assert np.isclose(stresses.values[0,0,0], baseline[0,0]-1.0)


def test_unknown_factor_rejected(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    policy = StressPolicy(templates=(StressTemplate(stress_id="shock", factor_shocks={"X": -1.0}),))
    with pytest.raises(ContractIntegrityError):
        build_stresses(scenarios, policy)


def test_reverse_stress_bisection():
    status, multiplier, states = find_reverse_stress((-0.5,-0.5), ThresholdRisk(), StressPolicy())
    assert status == "COMPUTED"
    assert multiplier == pytest.approx(1.0, abs=2e-4)
    assert states == ("LOSS_LIMIT",)


def test_reverse_stress_capability_unavailable():
    assert find_reverse_stress((-1.0,), None, StressPolicy())[0] == "CAPABILITY_UNAVAILABLE"


def test_zero_reverse_shock_rejected():
    with pytest.raises(ContractIntegrityError):
        find_reverse_stress((0.0,0.0), ThresholdRisk(), StressPolicy())

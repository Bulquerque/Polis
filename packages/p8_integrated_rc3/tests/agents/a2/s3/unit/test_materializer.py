from datetime import timedelta
import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    DistributionType, HistoricalScenarioPanel, MixtureComponent, MixturePayload,
    QuantilePayload, ScenarioPolicy,
)
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.errors import TemporalIntegrityError
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_materializer import materialize_scenarios


def test_deterministic_seed(normal_belief):
    policy = ScenarioPolicy(scenario_count=64, seed_entropy=123)
    first = materialize_scenarios(normal_belief, policy)
    second = materialize_scenarios(normal_belief, policy)
    np.testing.assert_array_equal(first.values, second.values)
    assert first.content_sha256() == second.content_sha256()


def test_different_seed_changes_values(normal_belief):
    first = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64, seed_entropy=1))
    second = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64, seed_entropy=2))
    assert not np.array_equal(first.values, second.values)


def test_sobol_count_and_probability(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=70, sampling_method="SOBOL"))
    assert scenarios.shape == (70,1,2)
    assert np.isclose(scenarios.probabilities.sum(), 1.0)


def test_mixture_is_multimodal(normal_belief):
    payload = MixturePayload(components=(
        MixtureComponent(weight=0.5, family="NORMAL", mean=(-5,-5), covariance=((0.01,0),(0,0.01))),
        MixtureComponent(weight=0.5, family="NORMAL", mean=(5,5), covariance=((0.01,0),(0,0.01))),
    ))
    belief = normal_belief.model_copy(update={"distribution_type": DistributionType.MIXTURE, "payload": payload})
    scenarios = materialize_scenarios(belief, ScenarioPolicy(scenario_count=512, seed_entropy=4))
    values = scenarios.values[:,0,0]
    assert np.mean(values < -4) > 0.35
    assert np.mean(values > 4) > 0.35


def test_quantile_copula_preserves_positive_dependence(normal_belief):
    payload = QuantilePayload(
        levels=(0.01,0.5,0.99), values=((-3,-3),(0,0),(3,3)),
        gaussian_copula_correlation=((1,0.8),(0.8,1)),
    )
    belief = normal_belief.model_copy(update={"distribution_type": DistributionType.QUANTILE, "payload": payload})
    scenarios = materialize_scenarios(belief, ScenarioPolicy(scenario_count=512, seed_entropy=8))
    assert np.corrcoef(scenarios.values[:,0,:], rowvar=False)[0,1] > 0.65


def test_historical_weight(normal_belief):
    now = normal_belief.decision_time
    history = HistoricalScenarioPanel(
        factor_ids=("A","B"), samples=((10.0,10.0),(11.0,11.0)),
        sample_available_at=(now-timedelta(days=2), now-timedelta(days=1)), decision_time=now,
    )
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=16, historical_weight=0.2), history)
    assert scenarios.shape[0] == 18
    assert np.isclose(scenarios.probabilities[-2:].sum(), 0.2)


def test_future_history_rejected(normal_belief):
    now = normal_belief.decision_time
    history = HistoricalScenarioPanel(
        factor_ids=("A","B"), samples=((1.0,1.0),),
        sample_available_at=(now+timedelta(seconds=1),), decision_time=now,
    )
    with pytest.raises(TemporalIntegrityError):
        materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=16, historical_weight=0.2), history)


def test_arrays_are_readonly(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=16))
    with pytest.raises(ValueError):
        scenarios.values[0,0,0] = 999

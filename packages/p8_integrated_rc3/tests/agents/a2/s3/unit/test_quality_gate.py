from datetime import timedelta
import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import QualityPolicy, QualityStatus, RealizedSamplePanel, ScenarioPolicy
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.errors import ContractIntegrityError, TemporalIntegrityError
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.quality_gate import assess_quality
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_materializer import materialize_scenarios


def test_missing_realized_is_not_actionable(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64))
    result = assess_quality(scenarios, None, ("LINEAR",), QualityPolicy())
    assert result.status_by_family["LINEAR"] == QualityStatus.NOT_ACTIONABLE
    assert result.score == 0.0


def test_matching_samples_qualify(normal_belief, realized):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=1024, seed_entropy=9))
    policy = QualityPolicy(mean_relative_error_max=2.0, covariance_relative_error_max=0.8, quantile_absolute_error_max=0.8, tail_quantile_error_max=0.8)
    result = assess_quality(scenarios, realized, ("LINEAR",), policy)
    assert result.status_by_family["LINEAR"] in {QualityStatus.FULLY_QUALIFIED, QualityStatus.QUALIFIED_WITH_HAIRCUT}


def test_path_family_requires_paths(normal_belief, realized):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64))
    policy = QualityPolicy(mean_relative_error_max=5, covariance_relative_error_max=5, quantile_absolute_error_max=5, tail_quantile_error_max=5)
    result = assess_quality(scenarios, realized, ("CALENDAR",), policy)
    assert result.status_by_family["CALENDAR"] == QualityStatus.PATH_INCOMPLETE


def test_factor_mismatch_rejected(normal_belief, realized):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64))
    bad = realized.model_copy(update={"factor_ids": ("X","Y")})
    with pytest.raises(ContractIntegrityError):
        assess_quality(scenarios, bad, ("LINEAR",), QualityPolicy())


def test_future_realized_rejected(normal_belief, realized):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=64))
    bad = realized.model_copy(update={"available_at": realized.decision_time+timedelta(seconds=1)})
    with pytest.raises(TemporalIntegrityError):
        assess_quality(scenarios, bad, ("LINEAR",), QualityPolicy())

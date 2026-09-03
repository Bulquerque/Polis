import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State, SeedPolicy
from quant_pipeline.phase_09.subphases.s06_structural_stress.m04_conditional_extreme_value_tail_engine import (
    _expected_shortfall,
    _tail_quantile,
    fit_conditional_evt,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import EVTRequest
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import EVTPolicy


def test_exponential_tail_formula_and_invalid_tail_probability():
    value = _tail_quantile(1.0, 0.0, 2.0, 0.1, 0.01)
    assert value > 1.0
    with pytest.raises(ValueError):
        _tail_quantile(1.0, 0.1, 2.0, 0.1, 0.2)
    with pytest.raises(ValueError):
        _expected_shortfall(1.0, 2.0, 1.0, 1.0)


def test_too_few_exceedances_are_explicit(context):
    generator = np.random.default_rng(3)
    losses = tuple(float(x) for x in generator.normal(size=100))
    result = fit_conditional_evt(
        EVTRequest(
            context=context,
            loss_series_id="short",
            losses=losses,
            conditional_scales=tuple(1.0 for _ in losses),
            seed_policy=SeedPolicy(root_entropy=3),
            policy=EVTPolicy(
                threshold_quantile=0.98,
                minimum_exceedances=20,
                maximum_absolute_residual_autocorrelation=1.0,
            ),
        )
    )
    assert result.status in {S6State.INSUFFICIENT_EXCEEDANCES, S6State.THRESHOLD_NOT_IDENTIFIED}


def test_ewma_path_is_supported(context):
    generator = np.random.default_rng(11)
    values = generator.normal(0.0, 1.0, 600)
    values[::20] += generator.pareto(4.0, 30)
    result = fit_conditional_evt(
        EVTRequest(
            context=context,
            loss_series_id="ewma",
            losses=tuple(float(x) for x in values),
            seed_policy=SeedPolicy(root_entropy=5),
            policy=EVTPolicy(
                threshold_quantile=0.9,
                minimum_exceedances=30,
                parameter_bootstrap_replicates=30,
                maximum_absolute_residual_autocorrelation=1.0,
                maximum_tail_index_range=10.0,
            ),
        )
    )
    assert result.status in {
        S6State.QUALIFIED,
        S6State.QUALIFIED_WITH_LIMITATIONS,
        S6State.UNSTABLE_TAIL_INDEX,
    }

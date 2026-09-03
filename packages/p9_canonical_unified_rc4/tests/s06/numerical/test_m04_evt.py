import numpy as np

from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State, SeedPolicy
from quant_pipeline.phase_09.subphases.s06_structural_stress.m04_conditional_extreme_value_tail_engine import (
    fit_conditional_evt,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import EVTRequest
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import EVTPolicy


def test_gpd_synthetic_tail_is_recovered(context):
    generator = np.random.default_rng(99)
    body = generator.normal(0.0, 0.1, 1800)
    tail = 0.4 + generator.pareto(5.0, 200) * 0.2
    combined = np.concatenate([body, tail])
    generator.shuffle(combined)
    losses = tuple(float(value) for value in combined)
    result = fit_conditional_evt(
        EVTRequest(
            context=context,
            loss_series_id="synthetic-gpd",
            losses=losses,
            conditional_scales=tuple(1.0 for _ in losses),
            seed_policy=SeedPolicy(root_entropy=12),
            policy=EVTPolicy(
                threshold_quantile=0.9,
                minimum_exceedances=100,
                parameter_bootstrap_replicates=60,
                maximum_absolute_residual_autocorrelation=0.2,
                maximum_tail_index_range=1.0,
            ),
        )
    )
    assert result.status in {S6State.QUALIFIED, S6State.QUALIFIED_WITH_LIMITATIONS}
    assert result.tail_index is not None
    assert -0.5 < result.tail_index < 1.0
    assert result.conditional_expected_shortfall > result.conditional_var


def test_dependent_residuals_are_rejected(context):
    values = [0.0]
    for _ in range(300):
        values.append(0.95 * values[-1] + 0.05)
    result = fit_conditional_evt(
        EVTRequest(
            context=context,
            loss_series_id="dependent",
            losses=tuple(values),
            conditional_scales=tuple(1.0 for _ in values),
            seed_policy=SeedPolicy(root_entropy=1),
            policy=EVTPolicy(maximum_absolute_residual_autocorrelation=0.1),
        )
    )
    assert result.status is S6State.DEPENDENCE_NOT_REMOVED

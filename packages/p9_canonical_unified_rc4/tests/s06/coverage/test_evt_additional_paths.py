from __future__ import annotations

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s06_structural_stress import (
    m04_conditional_extreme_value_tail_engine as engine,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State, SeedPolicy
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import EVTRequest
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import EVTPolicy


def _request(context, losses, **policy_updates):
    policy = EVTPolicy(
        threshold_quantile=0.8,
        minimum_exceedances=5,
        parameter_bootstrap_replicates=20,
        maximum_absolute_residual_autocorrelation=1.0,
        maximum_tail_index_range=10.0,
    ).model_copy(update=policy_updates)
    return EVTRequest(
        context=context,
        loss_series_id="evt-edge",
        losses=tuple(float(x) for x in losses),
        conditional_scales=tuple(1.0 for _ in losses),
        seed_policy=SeedPolicy(root_entropy=600),
        policy=policy,
    )


def test_invalid_gpd_fit_is_rejected(monkeypatch):
    monkeypatch.setattr(engine.genpareto, "fit", lambda *_args, **_kwargs: (0.2, 1.0, 1.0))
    with pytest.raises(ValueError, match="invalid GPD fit"):
        engine._fit_excesses(np.asarray([0.1, 0.2, 0.3]))


def test_main_fit_failure_returns_threshold_not_identified(context, monkeypatch):
    request = _request(context, np.linspace(0.0, 1.0, 100))
    monkeypatch.setattr(engine, "_threshold_fit", lambda *_args: (_ for _ in ()).throw(ValueError("bad")))
    result = engine.fit_conditional_evt(request)
    assert result.status is S6State.THRESHOLD_NOT_IDENTIFIED


def test_infinite_expected_shortfall_is_explicit(context, monkeypatch):
    request = _request(context, np.linspace(0.0, 2.0, 100))

    def shape_above_one(_standardized, _quantile):
        return 0.5, 1.2, 0.3, 20

    monkeypatch.setattr(engine, "_threshold_fit", shape_above_one)
    result = engine.fit_conditional_evt(request)
    assert result.status is S6State.UNSTABLE_TAIL_INDEX
    assert "P9_STRESS_EVT_TAIL_INDEX_INVALID_FOR_ES" in result.reason_codes


def test_bootstrap_with_too_few_successful_fits_returns_empty(context, monkeypatch):
    request = _request(context, np.linspace(0.0, 2.0, 100))
    monkeypatch.setattr(
        engine,
        "_fit_excesses",
        lambda *_args: (_ for _ in ()).throw(ValueError("fit failed")),
    )
    intervals = engine._bootstrap_intervals(np.asarray([0.1, 0.2, 0.3, 0.4]), request)
    assert intervals == ()


def test_threshold_sensitivity_skips_out_of_range_quantile(context):
    generator = np.random.default_rng(41)
    losses = generator.normal(size=200)
    request = _request(
        context,
        losses,
        threshold_quantile=0.51,
        threshold_sensitivity_step=0.09,
        minimum_exceedances=20,
    )
    result = engine.fit_conditional_evt(request)
    assert result.status in {
        S6State.QUALIFIED,
        S6State.QUALIFIED_WITH_LIMITATIONS,
        S6State.UNSTABLE_TAIL_INDEX,
    }

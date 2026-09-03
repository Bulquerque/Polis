from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from quant_pipeline.phase_05_underlying_forecasts.errors import DataQualityError
from quant_pipeline.phase_05_underlying_forecasts.services.calendar import WeekdayTradingCalendar
from quant_pipeline.phase_05_underlying_forecasts.services.dependence import (
    dcc_covariance,
    network_dependence,
    validate_covariance,
)
from quant_pipeline.phase_05_underlying_forecasts.services.diagnostics import (
    ood_score,
    page_hinkley,
    recurrent_regime,
)
from quant_pipeline.phase_05_underlying_forecasts.services.modeling import get_resolver
from quant_pipeline.phase_05_underlying_forecasts.services.risk import (
    bootstrap_scenarios,
    dynamic_quantiles,
    gjr_variance,
    implied_blend,
    path_risk,
    validate_distribution_set,
)


def test_calendar_advances_market_sessions_not_civil_days():
    calendar = WeekdayTradingCalendar()
    friday = datetime(2026, 7, 31, 21, tzinfo=timezone.utc)
    assert calendar.advance_sessions(friday, 1).weekday() == 0
    assert calendar.advance_sessions(friday, 1).date().isoformat() == "2026-08-03"


def test_kalman_and_kernel_resolvers_are_portable_and_deterministic():
    x = np.arange(80, dtype=float).reshape(40, 2) / 100.0
    y = 0.02 + x[:, 0] * 0.5 - x[:, 1] * 0.25
    for implementation, parameters in (
        ("builtin.kalman_dlm", {"process_scale": 1e-4, "observation_scale": 1e-3}),
        ("builtin.kernel_ridge_rbf", {"alpha": 0.5, "gamma": 0.5, "max_dictionary": 64}),
    ):
        resolver = get_resolver(implementation)
        first = resolver.fit(x, y, parameters, seed=7)
        second = resolver.fit(x, y, parameters, seed=7)
        assert first == second
        prediction = resolver.predict(first, x[-3:])
        assert prediction.shape == (3,)
        assert np.all(np.isfinite(prediction))


def test_gjr_parameters_are_estimated_and_stationary():
    generator = np.random.default_rng(42)
    values = generator.normal(0.0, 0.02, size=120)
    variance, diagnostics = gjr_variance(values)
    assert variance > 0.0
    assert diagnostics["method"] == "GJR_GARCH_GRID_MLE"
    assert diagnostics["stationary"] is True
    assert diagnostics["alpha"] + 0.5 * diagnostics["gamma"] + diagnostics["beta"] < 1.0


def test_implied_blend_requires_explicit_coverage():
    with pytest.raises(DataQualityError, match="coverage"):
        implied_blend(0.01, {"implied_volatility": 0.20})


def test_path_risk_does_not_invent_liquidity():
    values = np.asarray([0.01, -0.02, 0.005, -0.01, 0.004, 0.003, -0.006, 0.002])
    output = path_risk(values)
    assert "liquidity_risk" not in output
    assert output["maximum_drawdown"] >= 0.0


def test_dynamic_quantiles_are_monotonic_and_rich():
    values = np.linspace(-0.05, 0.06, 80)
    distribution, diagnostics = dynamic_quantiles(values)
    levels = [point.level for point in distribution.quantiles]
    quantiles = [point.value for point in distribution.quantiles]
    assert levels == sorted(levels)
    assert quantiles == sorted(quantiles)
    assert diagnostics["effective_sample_size"] > 1.0


def test_stationary_bootstrap_is_deterministic_and_noncollapsed():
    values = np.sin(np.linspace(0, 6, 100)) * 0.02
    first = bootstrap_scenarios(values, seed=11, count=64, block=5)
    second = bootstrap_scenarios(values, seed=11, count=64, block=5)
    assert first == second
    assert len(set(np.round(first.samples, 12))) > 3


def test_scenario_validation_detects_collapse():
    record = {
        "record_id": "collapsed",
        "distribution": {
            "kind": "SCENARIOS",
            "scenarios": [
                {"scenario_id": "a", "value": 0.0, "probability": 0.5},
                {"scenario_id": "b", "value": 0.0, "probability": 0.5},
            ],
        },
    }
    report = validate_distribution_set([record])
    assert report["passed"] is False
    assert report["failures"][0]["reason"] == "SCENARIO_COLLAPSE"


def test_dcc_is_estimated_and_covariance_validates():
    generator = np.random.default_rng(13)
    common = generator.normal(size=160)
    values = np.column_stack([
        common + generator.normal(scale=0.3, size=160),
        0.6 * common + generator.normal(scale=0.5, size=160),
        generator.normal(size=160),
    ])
    covariance, diagnostics = dcc_covariance(values)
    repaired, validation = validate_covariance(covariance)
    assert diagnostics["method"] == "DCC_GRID_MLE"
    assert diagnostics["persistence"] < 1.0
    assert validation["validated"] is True
    assert np.allclose(repaired, repaired.T)


def test_network_contains_components_and_centrality():
    generator = np.random.default_rng(5)
    values = generator.normal(size=(80, 4))
    network = network_dependence(values, ("A", "B", "C", "D"))
    assert network["connected_components"]
    assert set(network["weighted_degree_centrality"]) == {"A", "B", "C", "D"}
    assert 0.0 <= network["concentration"] <= 1.0


def test_regime_changepoint_and_ood_have_richer_diagnostics():
    values = np.concatenate([np.zeros(40), np.ones(20) * 0.2])
    regime = recurrent_regime(values)
    change = page_hinkley(values)
    reference = np.column_stack([np.linspace(0, 1, 30), np.linspace(1, 0, 30)])
    ood = ood_score(reference, np.asarray([2.0, -1.0]))
    assert "expected_duration" in regime
    assert "cusum_score" in change
    assert ood["shrinkage_method"] == "LEDOIT_WOLF"
    assert len(ood["feature_contributions"]) == 2

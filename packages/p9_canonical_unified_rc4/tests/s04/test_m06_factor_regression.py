from __future__ import annotations

import math

from quant_pipeline.phase_09.subphases.s04_performance_risk.factor_models import (
    BenchmarkAndFactorPanel,
    FactorModelRegistry,
    FactorModelSpec,
    FactorObservation,
    FactorRegressionRequest,
    FactorValue,
    RegressionCovariance,
    RegressionPolicy,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.m01_returns import compute_returns
from quant_pipeline.phase_09.subphases.s04_performance_risk.m06_factor_regression import compute_factor_regressions
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import ReturnEngineRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256


def test_factor_engine_runs_hac(qualified, policies, risk_free, factor_panel, registries):
    returns = compute_returns(
        ReturnEngineRequest(
            qualified_backtest=qualified,
            policy=policies["return"],
            risk_free=risk_free,
        )
    )
    result = compute_factor_regressions(
        FactorRegressionRequest(
            returns=returns.return_series,
            factors=factor_panel,
            risk_free=risk_free,
            registry=registries[1],
            policy=policies["regression"],
        )
    )
    assert len(result.exposures.regressions) == 2
    assert all(record.covariance_method == "HAC" for record in result.exposures.regressions)
    assert any(coefficient.name == "alpha_annualized" for record in result.exposures.regressions for coefficient in record.coefficients)
    assert result.rolling.records


def test_synthetic_known_beta(qualified, policies, risk_free, timestamps):
    market = [0.001 * math.sin(index / 5) + 0.0002 * math.cos(index / 9) for index in range(len(timestamps))]
    observations = tuple(
        FactorObservation(
            timestamp=timestamp,
            available_at=timestamp,
            values=(FactorValue(factor_id="MKT_RF", value=value),),
        )
        for timestamp, value in zip(timestamps, market)
    )
    body = {"panel_id": "known-beta", "panel_version": "1.0.0", "observations": observations}
    factors = BenchmarkAndFactorPanel(**body, content_sha256=content_sha256(body))
    registry = FactorModelRegistry(
        registry_id="known",
        registry_version="1.0.0",
        models=(
            FactorModelSpec(
                factor_model_id="CAPM",
                factor_model_version="1.0.0",
                factor_ids=("MKT_RF",),
                description="known beta fixture",
            ),
        ),
    )
    # Build a return panel then replace net and gross returns with exact alpha + 2*market + rf.
    returns = compute_returns(
        ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"], risk_free=risk_free)
    )
    rf_values = [point.value for point in risk_free.points]
    synthetic = tuple(0.0001 + 2.0 * factor + rf for factor, rf in zip(market, rf_values))
    panel_body = returns.return_series.model_dump(mode="python", exclude={"content_sha256"})
    panel_body.update(
        {
            "gross_returns": synthetic,
            "net_returns": synthetic,
            "excess_returns": tuple(value - rf for value, rf in zip(synthetic, rf_values)),
            "active_returns": None,
        }
    )
    synthetic_panel = returns.return_series.__class__(
        **panel_body,
        content_sha256=content_sha256(panel_body),
    )
    policy = RegressionPolicy(
        policy_id="known",
        policy_version="1.0.0",
        factor_model_ids=(("CAPM", "1.0.0"),),
        covariance=RegressionCovariance.NONROBUST,
        minimum_observations=30,
    )
    result = compute_factor_regressions(
        FactorRegressionRequest(
            returns=synthetic_panel,
            factors=factors,
            risk_free=risk_free,
            registry=registry,
            policy=policy,
        )
    )
    net_record = next(record for record in result.exposures.regressions if record.gross_net == "NET")
    beta = next(coefficient.estimate for coefficient in net_record.coefficients if coefficient.name == "MKT_RF")
    assert abs(beta - 2.0) < 1e-8


def test_singular_factor_matrix_is_explicit(qualified, policies, risk_free, timestamps):
    observations = tuple(
        FactorObservation(
            timestamp=timestamp,
            available_at=timestamp,
            values=(
                FactorValue(factor_id="A", value=index / 1000),
                FactorValue(factor_id="B", value=index / 1000),
            ),
        )
        for index, timestamp in enumerate(timestamps)
    )
    body = {"panel_id": "singular", "panel_version": "1.0.0", "observations": observations}
    panel = BenchmarkAndFactorPanel(**body, content_sha256=content_sha256(body))
    registry = FactorModelRegistry(
        registry_id="singular",
        registry_version="1.0.0",
        models=(FactorModelSpec(factor_model_id="SINGULAR", factor_model_version="1.0.0", factor_ids=("A", "B"), description="singular fixture"),),
    )
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"], risk_free=risk_free))
    policy = RegressionPolicy(
        policy_id="singular",
        policy_version="1.0.0",
        factor_model_ids=(("SINGULAR", "1.0.0"),),
        condition_number_limit=1000.0,
    )
    result = compute_factor_regressions(
        FactorRegressionRequest(returns=returns.return_series, factors=panel, risk_free=risk_free, registry=registry, policy=policy)
    )
    assert all(record.status == "INVALID" for record in result.exposures.regressions)

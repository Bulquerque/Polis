from __future__ import annotations

from quant_pipeline.phase_09.subphases.s04_performance_risk.bundle_models import QualityState
from quant_pipeline.phase_09.subphases.s04_performance_risk.service import (
    S4AnalyticsRequest,
    S4AnalyticsService,
)


def test_full_s4_service_golden_thread(
    qualified,
    policies,
    benchmark,
    risk_free,
    factor_panel,
    registries,
    execution_inputs,
):
    targets, liquidity, exposures = execution_inputs
    request = S4AnalyticsRequest(
        qualified_backtest=qualified,
        return_policy=policies["return"],
        distribution_policy=policies["distribution"],
        tail_policy=policies["tail"],
        drawdown_policy=policies["drawdown"],
        risk_adjusted_policy=policies["risk_adjusted"],
        capacity_policy=policies["capacity"],
        metric_registry=registries[0],
        metric_quality_policy=policies["quality"],
        benchmark=benchmark,
        risk_free=risk_free,
        factor_panel=factor_panel,
        factor_registry=registries[1],
        regression_policy=policies["regression"],
        target_contexts=targets,
        liquidity=liquidity,
        exposures=exposures,
    )

    result = S4AnalyticsService().run(request)

    assert result.quality.receipt.state in {
        QualityState.QUALIFIED,
        QualityState.QUALIFIED_WITH_LIMITATIONS,
    }
    assert result.quality.panel.metric_count == len(result.quality.panel.metrics)
    assert result.quality.panel.metric_count >= 40
    assert result.factors is not None
    assert result.returns.return_series.identity == result.quality.panel.identity
    assert result.execution.execution.identity == result.quality.panel.identity
    assert result.execution.costs.identity == result.quality.panel.identity
    assert result.execution.capacity.identity == result.quality.panel.identity


def test_factor_inputs_are_all_or_none(
    qualified,
    policies,
    factor_panel,
    registries,
):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        S4AnalyticsRequest(
            qualified_backtest=qualified,
            return_policy=policies["return"],
            distribution_policy=policies["distribution"],
            tail_policy=policies["tail"],
            drawdown_policy=policies["drawdown"],
            risk_adjusted_policy=policies["risk_adjusted"],
            capacity_policy=policies["capacity"],
            metric_registry=registries[0],
            metric_quality_policy=policies["quality"],
            factor_panel=factor_panel,
        )

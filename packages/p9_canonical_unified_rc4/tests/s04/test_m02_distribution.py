from __future__ import annotations

import math

from quant_pipeline.phase_09.subphases.s04_performance_risk.distribution_models import (
    DistributionEngineRequest,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.m01_returns import compute_returns
from quant_pipeline.phase_09.subphases.s04_performance_risk.m02_distribution import compute_distribution
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import ReturnEngineRequest


def find(panel, metric_id, gross_net):
    return next(metric for metric in panel.metrics if metric.metric_id == metric_id and metric.gross_net.value == gross_net)


def test_distribution_metrics_are_finite(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    result = compute_distribution(
        DistributionEngineRequest(returns=returns.return_series, policy=policies["distribution"])
    )
    volatility = find(result.volatility, "risk.volatility", "NET")
    assert volatility.value is not None and volatility.value > 0
    skewness = find(result.volatility, "distribution.skewness", "NET")
    assert skewness.value is not None and math.isfinite(skewness.value)
    assert len(result.diagnostics.serial_correlations) == 3
    assert len(result.diagnostics.rolling) > 0


def test_distribution_ljung_box_is_reported(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    result = compute_distribution(
        DistributionEngineRequest(returns=returns.return_series, policy=policies["distribution"])
    )
    assert result.serial_dependence.ljung_box_lag is not None
    assert result.serial_dependence.net_ljung_box_pvalue is not None
    assert 0 <= result.serial_dependence.net_ljung_box_pvalue <= 1


def test_distribution_small_sample_is_explicit(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    short = returns.return_series.model_copy(
        update={
            "timestamps": returns.return_series.timestamps[:5],
            "gross_returns": returns.return_series.gross_returns[:5],
            "net_returns": returns.return_series.net_returns[:5],
            "active_returns": None,
            "excess_returns": None,
            "content_sha256": "0" * 64,
        }
    )
    from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
    short = short.model_copy(update={"content_sha256": content_sha256(short.hash_preimage())})
    result = compute_distribution(DistributionEngineRequest(returns=short, policy=policies["distribution"]))
    metric = find(result.volatility, "risk.volatility", "NET")
    assert metric.value is None
    assert metric.status.value == "INSUFFICIENT_SAMPLE"

from __future__ import annotations

from quant_pipeline.phase_09.subphases.s04_performance_risk.m01_returns import compute_returns
from quant_pipeline.phase_09.subphases.s04_performance_risk.m03_tail_risk import compute_tail_risk
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import ReturnEngineRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.tail_models import TailRiskRequest


def test_tail_risk_separates_historical_and_parametric(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    result = compute_tail_risk(TailRiskRequest(returns=returns.return_series, policy=policies["tail"]))
    methods = {estimate.method for estimate in result.metrics.estimates}
    assert methods == {"HISTORICAL", "NORMAL_PARAMETRIC"}
    historical = next(
        estimate
        for estimate in result.metrics.estimates
        if estimate.method == "HISTORICAL" and estimate.gross_net == "NET" and estimate.confidence_level == 0.95
    )
    assert historical.value_at_risk is not None
    assert historical.expected_shortfall is not None
    assert historical.expected_shortfall >= historical.value_at_risk


def test_tail_breaches_reference_positive_losses(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    result = compute_tail_risk(TailRiskRequest(returns=returns.return_series, policy=policies["tail"]))
    assert all(record.loss > record.value_at_risk for record in result.breaches.breaches)


def test_tail_small_sample_is_not_zero(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    short = returns.return_series.model_copy(
        update={
            "timestamps": returns.return_series.timestamps[:10],
            "gross_returns": returns.return_series.gross_returns[:10],
            "net_returns": returns.return_series.net_returns[:10],
            "active_returns": None,
            "excess_returns": None,
            "content_sha256": "0" * 64,
        }
    )
    from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
    short = short.model_copy(update={"content_sha256": content_sha256(short.hash_preimage())})
    result = compute_tail_risk(TailRiskRequest(returns=short, policy=policies["tail"]))
    estimate = next(item for item in result.metrics.estimates if item.method == "HISTORICAL")
    assert estimate.value_at_risk is None
    assert estimate.status == "INSUFFICIENT_SAMPLE"

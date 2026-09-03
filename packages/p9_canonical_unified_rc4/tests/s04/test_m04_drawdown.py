from __future__ import annotations

from quant_pipeline.phase_09.subphases.s04_performance_risk.drawdown_models import DrawdownRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.m01_returns import compute_returns
from quant_pipeline.phase_09.subphases.s04_performance_risk.m04_drawdown import compute_drawdowns
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import ReturnEngineRequest


def find(panel, metric_id):
    return next(metric for metric in panel.metrics if metric.metric_id == metric_id)


def test_drawdown_state_machine_finds_episodes(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    result = compute_drawdowns(DrawdownRequest(wealth_path=returns.wealth_path, policy=policies["drawdown"]))
    maximum = find(result.metrics, "drawdown.maximum")
    assert maximum.value is not None and maximum.value > 0
    assert len(result.episodes.episodes) >= 1
    assert all(episode.maximum_drawdown_fraction <= 0 for episode in result.episodes.episodes)


def test_underwater_uses_same_wealth_path(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    result = compute_drawdowns(DrawdownRequest(wealth_path=returns.wealth_path, policy=policies["drawdown"]))
    assert len(result.underwater.points) == len(returns.wealth_path.points)
    for underwater, wealth in zip(result.underwater.points, returns.wealth_path.points):
        assert underwater.timestamp == wealth.timestamp
        assert underwater.wealth == float(wealth.net_wealth)


def test_censored_episode_has_no_recovery(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    points = list(returns.wealth_path.points)
    # Force the final mark below the high-water mark while preserving a valid hash.
    last = points[-1].model_copy(update={"nav": points[-1].nav * __import__("decimal").Decimal("0.8"), "net_wealth": points[-1].net_wealth * __import__("decimal").Decimal("0.8")})
    points[-1] = last
    body = returns.wealth_path.model_dump(mode="python", exclude={"content_sha256"})
    body["points"] = tuple(points)
    from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
    altered = returns.wealth_path.__class__(**body, content_sha256=content_sha256(body))
    result = compute_drawdowns(DrawdownRequest(wealth_path=altered, policy=policies["drawdown"]))
    censored = [episode for episode in result.episodes.episodes if episode.censored]
    assert censored
    assert all(episode.recovery_time is None for episode in censored)

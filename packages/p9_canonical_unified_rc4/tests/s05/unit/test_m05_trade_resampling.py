from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m05_trade_and_execution_resampling_engine import resample_trade_episodes
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import TradeResamplingRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import TradeResamplingPolicy


def test_overlapping_trades_are_clustered(context, trade_panel, seed_policy) -> None:
    result = resample_trade_episodes(
        TradeResamplingRequest(
            context=context,
            trades=trade_panel,
            seed_policy=seed_policy,
            policy=TradeResamplingPolicy(replicate_count=30, cluster_block_length=2),
        )
    )
    assert len(result.clusters) < len(trade_panel.episodes)
    assert len(result.replicates) == 30
    assert any(len(cluster.trade_ids) > 1 for cluster in result.clusters)


def test_trade_replay_is_deterministic(context, trade_panel, seed_policy) -> None:
    request = TradeResamplingRequest(context=context, trades=trade_panel, seed_policy=seed_policy)
    assert resample_trade_episodes(request) == resample_trade_episodes(request)

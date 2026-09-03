from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from .contracts import S5State
from .models import (
    TradeCluster,
    TradeReplicateSummary,
    TradeResamplingRequest,
    TradeResamplingResult,
)
from .numerics import hhi
from .randomness import derive_generator

MODULE_ID = "P9.S5.M05"


def _build_clusters(request: TradeResamplingRequest) -> tuple[TradeCluster, ...]:
    episodes = sorted(
        request.trades.episodes,
        key=lambda item: (item.opened_at, item.closed_at, item.trade_id),
    )
    clusters: list[TradeCluster] = []
    current: list = []
    current_end: datetime | None = None
    for episode in episodes:
        if current_end is None or episode.opened_at > current_end:
            if current:
                clusters.append(_collapse_cluster(len(clusters) + 1, current))
            current = [episode]
            current_end = episode.closed_at
        else:
            current.append(episode)
            current_end = max(current_end, episode.closed_at)
    if current:
        clusters.append(_collapse_cluster(len(clusters) + 1, current))
    return tuple(clusters)


def _collapse_cluster(cluster_id: int, episodes: list) -> TradeCluster:
    return TradeCluster(
        cluster_id=cluster_id,
        trade_ids=tuple(episode.trade_id for episode in episodes),
        opened_at=min(episode.opened_at for episode in episodes),
        closed_at=max(episode.closed_at for episode in episodes),
        gross_pnl=float(sum(episode.gross_pnl for episode in episodes)),
        net_pnl=float(sum(episode.net_pnl for episode in episodes)),
        total_cost=float(sum(episode.total_cost for episode in episodes)),
    )


def _sample_cluster_indices(
    cluster_count: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    block_count = math.ceil(cluster_count / block_length)
    starts = rng.integers(0, cluster_count, size=block_count, dtype=np.int64)
    offsets = np.arange(block_length, dtype=np.int64)
    sampled = [np.mod(start + offsets, cluster_count) for start in starts]
    return np.concatenate(sampled)[:cluster_count]


def resample_trade_episodes(request: TradeResamplingRequest) -> TradeResamplingResult:
    """Resample overlapping trade clusters rather than treating trades as IID."""

    trade_count = len(request.trades.episodes)
    if trade_count < request.policy.minimum_trade_count:
        return TradeResamplingResult(
            status=S5State.INSUFFICIENT_TRADES,
            clusters=(),
            replicates=(),
            pnl_hhi=0.0,
            cost_hhi=0.0,
            reason_codes=("P9_BOOTSTRAP_INSUFFICIENT_TRADES",),
        )
    clusters = _build_clusters(request)
    if not clusters:
        return TradeResamplingResult(
            status=S5State.INSUFFICIENT_TRADES,
            clusters=(),
            replicates=(),
            pnl_hhi=0.0,
            cost_hhi=0.0,
            reason_codes=("P9_BOOTSTRAP_TRADE_CLUSTER_EMPTY",),
        )
    block_length = min(request.policy.cluster_block_length, len(clusters))
    rng = derive_generator(
        request.seed_policy,
        request.context.experiment_id,
        request.context.configuration_id,
        MODULE_ID,
        len(clusters),
        block_length,
    )
    replicates: list[TradeReplicateSummary] = []
    for replicate_id in range(1, request.policy.replicate_count + 1):
        sampled_indices = _sample_cluster_indices(len(clusters), block_length, rng)
        sampled = [clusters[int(index)] for index in sampled_indices]
        replicates.append(
            TradeReplicateSummary(
                replicate_id=replicate_id,
                sampled_cluster_ids=tuple(item.cluster_id for item in sampled),
                trade_count=sum(len(item.trade_ids) for item in sampled),
                gross_pnl=float(sum(item.gross_pnl for item in sampled)),
                net_pnl=float(sum(item.net_pnl for item in sampled)),
                total_cost=float(sum(item.total_cost for item in sampled)),
            )
        )
    pnl_hhi = hhi(episode.net_pnl for episode in request.trades.episodes)
    cost_hhi = hhi(episode.total_cost for episode in request.trades.episodes)
    limitations: list[str] = []
    reason_codes: list[str] = []
    if pnl_hhi >= request.policy.concentration_warning_hhi:
        limitations.append("trade PnL is concentrated")
        reason_codes.append("P9_BOOTSTRAP_TRADE_PNL_CONCENTRATED")
    if cost_hhi >= request.policy.concentration_warning_hhi:
        limitations.append("trade costs are concentrated")
        reason_codes.append("P9_BOOTSTRAP_TRADE_COST_CONCENTRATED")
    status = S5State.SUCCESS if not limitations else S5State.QUALIFIED_WITH_LIMITATIONS
    return TradeResamplingResult(
        status=status,
        clusters=clusters,
        replicates=tuple(replicates),
        pnl_hhi=pnl_hhi,
        cost_hhi=cost_hhi,
        reason_codes=tuple(reason_codes),
        limitations=tuple(limitations),
    )

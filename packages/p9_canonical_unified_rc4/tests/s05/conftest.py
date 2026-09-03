from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import (
    FoldScore,
    FoldScorePanel,
    GrossNet,
    MetricDefinition,
    MetricName,
    RunContext,
    SeedPolicy,
    TimeSeriesPanel,
    TradeEpisode,
    TradeEpisodePanel,
    TrialPerformancePanel,
    TrialState,
)

HASH = "0" * 64


def ar1(phi: float, nobs: int, seed: int, scale: float = 0.01, drift: float = 0.0004) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, scale, size=nobs)
    values = np.empty(nobs, dtype=np.float64)
    values[0] = noise[0]
    for index in range(1, nobs):
        values[index] = drift + phi * values[index - 1] + noise[index]
    return values


@pytest.fixture
def context() -> RunContext:
    at = datetime(2025, 1, 1, tzinfo=UTC)
    return RunContext(
        run_id="run-001",
        cycle_id="cycle-001",
        experiment_id="experiment-001",
        configuration_id="configuration-001",
        decision_time=at,
        available_at=at,
        code_sha256=HASH,
        data_sha256=HASH,
    )


@pytest.fixture
def series_panel() -> TimeSeriesPanel:
    nobs = 240
    start = datetime(2024, 1, 1, tzinfo=UTC)
    target = ar1(0.35, nobs, 11, drift=0.0007)
    benchmark = ar1(0.15, nobs, 12, drift=0.00025)
    risk_free = np.full(nobs, 0.00005, dtype=np.float64)
    values = np.column_stack([target, benchmark, risk_free])
    return TimeSeriesPanel(
        panel_id="returns-panel",
        timestamps=tuple(start + timedelta(days=index) for index in range(nobs)),
        series_ids=("strategy", "benchmark", "risk_free"),
        values=tuple(tuple(float(value) for value in row) for row in values),
        periods_per_year=252.0,
        gross_or_net=GrossNet.NET,
        benchmark_series_id="benchmark",
        risk_free_series_id="risk_free",
        fold_ids=tuple(f"fold-{index // 60}" for index in range(nobs)),
        regime_ids=tuple("high-vol" if index % 80 >= 60 else "normal" for index in range(nobs)),
        metric_registry_version="1.0.0",
    )


@pytest.fixture
def trade_panel() -> TradeEpisodePanel:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    episodes = []
    for index in range(24):
        opened = start + timedelta(days=index * 4)
        duration = 6 if index % 4 == 0 else 2
        gross = 100.0 + index
        cost = 5.0 + (index % 3)
        episodes.append(
            TradeEpisode(
                trade_id=f"trade-{index:02d}",
                candidate_id=f"candidate-{index % 5}",
                opened_at=opened,
                closed_at=opened + timedelta(days=duration),
                instrument_ids=(f"instrument-{index % 3}",),
                gross_pnl=gross,
                net_pnl=gross - cost,
                total_cost=cost,
            )
        )
    return TradeEpisodePanel(panel_id="trade-panel", episodes=tuple(episodes))


@pytest.fixture
def trial_panel(series_panel: TimeSeriesPanel) -> TrialPerformancePanel:
    target = np.asarray([row[0] for row in series_panel.values], dtype=np.float64)
    rng = np.random.default_rng(123)
    columns = [
        target,
        target + rng.normal(0.0, 0.002, size=target.size),
        0.8 * target + rng.normal(0.0, 0.004, size=target.size),
        rng.normal(0.0001, 0.012, size=target.size),
        rng.normal(0.0, 0.013, size=target.size),
        -0.3 * target + rng.normal(0.0, 0.01, size=target.size),
    ]
    matrix = np.column_stack(columns)
    return TrialPerformancePanel(
        panel_id="trial-panel",
        timestamps=series_panel.timestamps,
        trial_ids=tuple(f"trial-{index}" for index in range(matrix.shape[1])),
        configuration_ids=(
            "configuration-001",
            "configuration-002",
            "configuration-003",
            "configuration-004",
            "configuration-005",
            "configuration-006",
        ),
        states=tuple(TrialState.COMPLETED for _ in range(matrix.shape[1])),
        performance_values=tuple(tuple(float(value) for value in row) for row in matrix),
        family_complete=True,
        economic_cluster_ids=("cluster-a", "cluster-a", "cluster-b", "cluster-c", "cluster-d", "cluster-e"),
    )


@pytest.fixture
def fold_scores() -> FoldScorePanel:
    return FoldScorePanel(
        configuration_id="configuration-001",
        scores=(
            FoldScore(fold_id="fold-0", score=0.22, observation_count=60),
            FoldScore(fold_id="fold-1", score=0.18, observation_count=60),
            FoldScore(fold_id="fold-2", score=0.14, observation_count=60),
            FoldScore(fold_id="fold-3", score=0.11, observation_count=60),
        ),
    )


@pytest.fixture
def seed_policy() -> SeedPolicy:
    return SeedPolicy(root_entropy=20260803)


@pytest.fixture
def metric_definitions() -> tuple[MetricDefinition, ...]:
    return (
        MetricDefinition(
            metric_id="net-sharpe",
            metric_name=MetricName.SHARPE,
            target_series_id="strategy",
            metric_version="1.0.0",
            threshold=0.0,
            benchmark_series_id="benchmark",
            risk_free_series_id="risk_free",
            minimum_valid_replicates=50,
        ),
        MetricDefinition(
            metric_id="net-cagr",
            metric_name=MetricName.CAGR,
            target_series_id="strategy",
            metric_version="1.0.0",
            threshold=0.0,
            minimum_valid_replicates=50,
        ),
        MetricDefinition(
            metric_id="max-drawdown",
            metric_name=MetricName.MAX_DRAWDOWN,
            target_series_id="strategy",
            metric_version="1.0.0",
            threshold=-0.25,
            minimum_valid_replicates=50,
        ),
        MetricDefinition(
            metric_id="net-alpha",
            metric_name=MetricName.ALPHA,
            target_series_id="strategy",
            metric_version="1.0.0",
            threshold=0.0,
            benchmark_series_id="benchmark",
            minimum_valid_replicates=50,
        ),
    )

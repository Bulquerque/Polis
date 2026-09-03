from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import (
    BootstrapMethod,
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
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import (
    DependenceDiagnosticsRequest,
    S5RunRequest,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import (
    BootstrapPolicy,
    MultipleTestingPolicy,
    TradeResamplingPolicy,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.runner import run_s5

HASH = "0" * 64


def ar1(phi: float, nobs: int, seed: int, drift: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 0.01, nobs)
    values = np.empty(nobs)
    values[0] = noise[0]
    for index in range(1, nobs):
        values[index] = drift + phi * values[index - 1] + noise[index]
    return values


def build_request() -> S5RunRequest:
    nobs = 160
    start = datetime(2024, 1, 1, tzinfo=UTC)
    timestamps = tuple(start + timedelta(days=i) for i in range(nobs))
    strategy = ar1(0.30, nobs, 10, 0.0007)
    benchmark = ar1(0.10, nobs, 11, 0.0002)
    risk_free = np.full(nobs, 0.00005)
    matrix = np.column_stack([strategy, benchmark, risk_free])
    panel = TimeSeriesPanel(
        panel_id="example-return-panel",
        timestamps=timestamps,
        series_ids=("strategy", "benchmark", "risk_free"),
        values=tuple(tuple(float(v) for v in row) for row in matrix),
        periods_per_year=252.0,
        gross_or_net=GrossNet.NET,
        benchmark_series_id="benchmark",
        risk_free_series_id="risk_free",
        fold_ids=tuple(f"fold-{i // 40}" for i in range(nobs)),
        regime_ids=tuple("stress" if i % 80 >= 60 else "normal" for i in range(nobs)),
    )
    episodes = tuple(
        TradeEpisode(
            trade_id=f"trade-{i:02d}", candidate_id=f"candidate-{i % 4}",
            opened_at=start + timedelta(days=4 * i),
            closed_at=start + timedelta(days=4 * i + (6 if i % 5 == 0 else 2)),
            instrument_ids=(f"instrument-{i % 3}",),
            gross_pnl=100.0 + i, net_pnl=94.0 + i, total_cost=6.0,
        )
        for i in range(20)
    )
    trial_rng = np.random.default_rng(12)
    trial_matrix = np.column_stack([
        strategy,
        strategy + trial_rng.normal(0.0, 0.002, nobs),
        0.7 * strategy + trial_rng.normal(0.0, 0.005, nobs),
        trial_rng.normal(0.0001, 0.012, nobs),
    ])
    trials = TrialPerformancePanel(
        panel_id="example-trial-panel", timestamps=timestamps,
        trial_ids=("trial-0", "trial-1", "trial-2", "trial-3"),
        configuration_ids=("configuration-001", "configuration-002", "configuration-003", "configuration-004"),
        states=(TrialState.COMPLETED,) * 4,
        performance_values=tuple(tuple(float(v) for v in row) for row in trial_matrix),
        family_complete=True,
        economic_cluster_ids=("a", "a", "b", "c"),
    )
    at = datetime(2025, 1, 1, tzinfo=UTC)
    context = RunContext(
        run_id="example-run", cycle_id="cycle-001", experiment_id="experiment-001",
        configuration_id="configuration-001", decision_time=at, available_at=at,
        code_sha256=HASH, data_sha256=HASH,
    )
    metrics = (
        MetricDefinition(
            metric_id="net-sharpe", metric_name=MetricName.SHARPE,
            target_series_id="strategy", risk_free_series_id="risk_free",
            threshold=0.0, minimum_valid_replicates=50,
        ),
        MetricDefinition(
            metric_id="net-cagr", metric_name=MetricName.CAGR,
            target_series_id="strategy", threshold=0.0, minimum_valid_replicates=50,
        ),
        MetricDefinition(
            metric_id="max-drawdown", metric_name=MetricName.MAX_DRAWDOWN,
            target_series_id="strategy", threshold=-0.25, minimum_valid_replicates=50,
        ),
    )
    return S5RunRequest(
        dependence=DependenceDiagnosticsRequest(
            context=context, series=panel,
            trades=TradeEpisodePanel(panel_id="example-trades", episodes=episodes),
        ),
        bootstrap_policy=BootstrapPolicy(method=BootstrapMethod.STATIONARY, replicate_count=80),
        seed_policy=SeedPolicy(root_entropy=20260803),
        trade_policy=TradeResamplingPolicy(replicate_count=80),
        metric_definitions=metrics,
        sharpe_target_series_id="strategy",
        trial_performance=trials,
        fold_scores=FoldScorePanel(
            configuration_id="configuration-001",
            scores=tuple(FoldScore(fold_id=f"fold-{i}", score=0.15 - i * 0.02, observation_count=40) for i in range(4)),
        ),
        target_metric_id="net-sharpe",
        multiple_testing_policy=MultipleTestingPolicy(reality_check_replicates=100),
    )


def main() -> None:
    directory = Path(__file__).resolve().parent
    request = build_request()
    output = run_s5(request)
    for path, rendered in (
        (directory / "s5_request.json", request.model_dump_json(indent=2)),
        (directory / "s5_output.json", output.model_dump_json(indent=2)),
    ):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered + "\n")
    summary = {
        "bundle_id": output.bundle_id,
        "bundle_sha256": output.bundle_sha256,
        "qualification": output.qualification.status,
        "module_receipt_count": len(output.module_receipts),
        "bootstrap_replicates": output.bootstrap.manifest.replicate_count if output.bootstrap.manifest else 0,
    }
    with (directory / "s5_output_summary.json").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()

from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import DependenceDiagnosticsRequest, S5RunRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy, TradeResamplingPolicy
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.runner import run_s5


def test_full_runner_is_deterministic(
    context,
    series_panel,
    trade_panel,
    trial_panel,
    fold_scores,
    seed_policy,
    metric_definitions,
) -> None:
    request = S5RunRequest(
        dependence=DependenceDiagnosticsRequest(
            context=context,
            series=series_panel,
            trades=trade_panel,
        ),
        bootstrap_policy=BootstrapPolicy(
            method=BootstrapMethod.STATIONARY,
            replicate_count=120,
        ),
        seed_policy=seed_policy,
        trade_policy=TradeResamplingPolicy(replicate_count=120),
        metric_definitions=metric_definitions,
        sharpe_target_series_id="strategy",
        trial_performance=trial_panel,
        fold_scores=fold_scores,
        target_metric_id="net-sharpe",
    )
    first = run_s5(request)
    second = run_s5(request)
    assert first == second
    assert first.bundle_sha256 == second.bundle_sha256
    assert len(first.module_receipts) == 8

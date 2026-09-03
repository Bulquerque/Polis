from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod, S5State
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m04_hierarchical_portfolio_bootstrap_engine import evaluate_hierarchical_bootstrap
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockBootstrapRequest, HierarchicalBootstrapRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy


def test_joint_bootstrap_records_covariance_and_regimes(context, series_panel, seed_policy) -> None:
    bootstrap = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=len(series_panel.timestamps),
            block_length=8,
            seed_policy=seed_policy,
            policy=BootstrapPolicy(method=BootstrapMethod.STATIONARY, replicate_count=40),
        )
    )
    assert bootstrap.manifest is not None
    result = evaluate_hierarchical_bootstrap(
        HierarchicalBootstrapRequest(context=context, series=series_panel, indices=bootstrap.manifest)
    )
    assert result.status in {S5State.SUCCESS, S5State.QUALIFIED_WITH_LIMITATIONS}
    assert result.joint_resampling_verified
    assert result.diagnostics
    assert result.minimum_regime_coverage is not None

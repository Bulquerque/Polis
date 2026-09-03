from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod, S5State
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockBootstrapRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy


def test_block_larger_than_sample_is_rejected(context, seed_policy) -> None:
    result = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=10,
            block_length=11,
            seed_policy=seed_policy,
            policy=BootstrapPolicy(method=BootstrapMethod.MOVING, replicate_count=10),
        )
    )
    assert result.status is S5State.INVALID_INPUT
    assert result.manifest is None

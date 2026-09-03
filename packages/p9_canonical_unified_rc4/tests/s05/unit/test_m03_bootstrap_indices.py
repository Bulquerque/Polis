from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockBootstrapRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy


def _request(context, seed_policy, method: BootstrapMethod) -> BlockBootstrapRequest:
    return BlockBootstrapRequest(
        context=context,
        observation_count=60,
        block_length=5,
        seed_policy=seed_policy,
        policy=BootstrapPolicy(method=method, replicate_count=20),
    )


def test_same_seed_replays_same_manifest(context, seed_policy) -> None:
    first = generate_bootstrap_indices(_request(context, seed_policy, BootstrapMethod.STATIONARY))
    second = generate_bootstrap_indices(_request(context, seed_policy, BootstrapMethod.STATIONARY))
    assert first.manifest == second.manifest


def test_circular_bootstrap_preserves_contiguous_blocks(context, seed_policy) -> None:
    result = generate_bootstrap_indices(_request(context, seed_policy, BootstrapMethod.CIRCULAR))
    assert result.manifest is not None
    row = result.manifest.indices[0]
    for start in range(0, 60, 5):
        block = row[start : start + 5]
        assert all((right - left) % 60 == 1 for left, right in zip(block, block[1:]))

from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockBootstrapRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy


def test_all_generated_indices_are_in_range_for_multiple_sizes(context, seed_policy) -> None:
    for nobs in (20, 31, 64):
        for block_length in (1, 3, min(10, nobs)):
            for method in BootstrapMethod:
                result = generate_bootstrap_indices(
                    BlockBootstrapRequest(
                        context=context,
                        observation_count=nobs,
                        block_length=block_length,
                        seed_policy=seed_policy,
                        policy=BootstrapPolicy(method=method, replicate_count=15),
                    )
                )
                assert result.manifest is not None
                assert all(
                    0 <= index < nobs
                    for row in result.manifest.indices
                    for index in row
                )

from __future__ import annotations

import math

import numpy as np

from .contracts import BootstrapMethod, S5State, content_sha256
from .models import BlockBootstrapRequest, BlockBootstrapResult, BootstrapIndexManifest
from .randomness import derive_generator

MODULE_ID = "P9.S5.M03"


def _moving_indices(nobs: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    block_count = math.ceil(nobs / block_length)
    maximum_start = nobs - block_length
    starts = rng.integers(0, maximum_start + 1, size=block_count, dtype=np.int64)
    blocks = [np.arange(start, start + block_length, dtype=np.int64) for start in starts]
    return np.concatenate(blocks)[:nobs]


def _circular_indices(nobs: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    block_count = math.ceil(nobs / block_length)
    starts = rng.integers(0, nobs, size=block_count, dtype=np.int64)
    offsets = np.arange(block_length, dtype=np.int64)
    blocks = [np.mod(start + offsets, nobs) for start in starts]
    return np.concatenate(blocks)[:nobs]


def _stationary_indices(nobs: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    restart_probability = min(1.0, 1.0 / block_length)
    indices = np.empty(nobs, dtype=np.int64)
    indices[0] = int(rng.integers(0, nobs))
    for position in range(1, nobs):
        if float(rng.random()) < restart_probability:
            indices[position] = int(rng.integers(0, nobs))
        else:
            indices[position] = (indices[position - 1] + 1) % nobs
    return indices


def generate_bootstrap_indices(request: BlockBootstrapRequest) -> BlockBootstrapResult:
    """Generate deterministic dependent-bootstrap index sequences."""

    if request.block_length > request.observation_count:
        return BlockBootstrapResult(
            status=S5State.INVALID_INPUT,
            manifest=None,
            reason_codes=("P9_BOOTSTRAP_BLOCK_EXCEEDS_SAMPLE",),
        )
    element_count = request.observation_count * request.policy.replicate_count
    if element_count > request.policy.maximum_materialized_elements:
        return BlockBootstrapResult(
            status=S5State.INVALID_INPUT,
            manifest=None,
            reason_codes=("P9_BOOTSTRAP_MATERIALIZATION_BUDGET_EXCEEDED",),
            limitations=("streaming manifests are not enabled in this release",),
        )
    rng = derive_generator(
        request.seed_policy,
        request.context.experiment_id,
        request.context.configuration_id,
        MODULE_ID,
        request.policy.method.value,
        request.observation_count,
        request.block_length,
    )
    generators = {
        BootstrapMethod.MOVING: _moving_indices,
        BootstrapMethod.CIRCULAR: _circular_indices,
        BootstrapMethod.STATIONARY: _stationary_indices,
    }
    generator = generators[request.policy.method]
    rows: list[tuple[int, ...]] = []
    row_hashes: list[str] = []
    for _ in range(request.policy.replicate_count):
        row = generator(request.observation_count, request.block_length, rng)
        serialized = tuple(int(value) for value in row)
        rows.append(serialized)
        row_hashes.append(content_sha256(serialized))
    seed_lineage = content_sha256(
        {
            "root_entropy": request.seed_policy.root_entropy,
            "tokens": [
                request.context.experiment_id,
                request.context.configuration_id,
                MODULE_ID,
                request.policy.method.value,
            ],
        }
    )
    payload = {
        "method": request.policy.method.value,
        "observation_count": request.observation_count,
        "replicate_count": request.policy.replicate_count,
        "block_length": request.block_length,
        "seed_lineage": seed_lineage,
        "replicate_sha256": row_hashes,
    }
    manifest_hash = content_sha256(payload)
    manifest = BootstrapIndexManifest(
        manifest_id=f"{request.context.run_id}:{MODULE_ID}:{manifest_hash[:16]}",
        method=request.policy.method,
        observation_count=request.observation_count,
        replicate_count=request.policy.replicate_count,
        block_length=request.block_length,
        seed_lineage=seed_lineage,
        indices=tuple(rows),
        replicate_sha256=tuple(row_hashes),
        manifest_sha256=manifest_hash,
    )
    return BlockBootstrapResult(status=S5State.SUCCESS, manifest=manifest)

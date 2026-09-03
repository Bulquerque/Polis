"""Small deterministic resampling routines used only by STABILITY mode."""
from __future__ import annotations

import random
from collections.abc import Callable, Sequence

from .ports import QuantDataError
from .series import quantile


def moving_block_resamples(
    values: Sequence[float],
    *,
    samples: int,
    block_length: int,
    seed: int,
) -> tuple[tuple[float, ...], ...]:
    if samples <= 0:
        return ()
    if not values:
        raise QuantDataError("bootstrap requires non-empty values")
    block = min(block_length, len(values))
    starts = range(0, len(values) - block + 1)
    candidates = tuple(starts)
    if not candidates:
        raise QuantDataError("bootstrap has no valid blocks")
    rng = random.Random(seed)
    results: list[tuple[float, ...]] = []
    for _ in range(samples):
        sample: list[float] = []
        while len(sample) < len(values):
            start = rng.choice(candidates)
            sample.extend(values[start : start + block])
        results.append(tuple(sample[: len(values)]))
    return tuple(results)


def bootstrap_interval(
    values: Sequence[float],
    *,
    statistic: Callable[[Sequence[float]], float],
    samples: int,
    confidence: float,
    block_length: int,
    seed: int,
) -> tuple[float, float] | None:
    if samples <= 0:
        return None
    estimates = [statistic(sample) for sample in moving_block_resamples(
        values,
        samples=samples,
        block_length=block_length,
        seed=seed,
    )]
    alpha = 1.0 - confidence
    return quantile(estimates, alpha / 2.0), quantile(estimates, 1.0 - alpha / 2.0)


def paired_moving_block_resamples(
    pairs: Sequence[tuple[float, float]],
    *,
    samples: int,
    block_length: int,
    seed: int,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    if samples <= 0:
        return ()
    if not pairs:
        raise QuantDataError("paired bootstrap requires observations")
    block = min(block_length, len(pairs))
    candidates = tuple(range(0, len(pairs) - block + 1))
    rng = random.Random(seed)
    results: list[tuple[tuple[float, float], ...]] = []
    for _ in range(samples):
        sample: list[tuple[float, float]] = []
        while len(sample) < len(pairs):
            start = rng.choice(candidates)
            sample.extend(pairs[start : start + block])
        results.append(tuple(sample[: len(pairs)]))
    return tuple(results)

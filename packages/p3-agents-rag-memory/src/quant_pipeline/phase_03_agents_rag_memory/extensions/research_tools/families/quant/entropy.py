"""Shannon and permutation entropy with frozen discretization policies."""
from __future__ import annotations

import bisect
import itertools
import math
from collections import Counter
from collections.abc import Sequence

from .model_base import BinningPolicy
from .ports import QuantDataError
from .series import quantile


def _equal_width_edges(values: Sequence[float], bins: int) -> tuple[float, ...]:
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return (minimum, maximum)
    width = (maximum - minimum) / bins
    return tuple(minimum + width * index for index in range(bins + 1))


def _equal_frequency_edges(values: Sequence[float], bins: int) -> tuple[float, ...]:
    edges = [quantile(values, index / bins) for index in range(bins + 1)]
    unique = sorted(set(edges))
    return tuple(unique)


def discretize(
    values: Sequence[float],
    *,
    policy: BinningPolicy,
    bins: int,
    fixed_edges: Sequence[float],
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    if not values:
        raise QuantDataError("entropy requires observations")
    if policy is BinningPolicy.EQUAL_WIDTH:
        edges = _equal_width_edges(values, bins)
    elif policy is BinningPolicy.EQUAL_FREQUENCY:
        edges = _equal_frequency_edges(values, bins)
    elif policy is BinningPolicy.FIXED_EDGES:
        edges = tuple(fixed_edges)
    else:
        raise QuantDataError(f"unsupported binning policy: {policy}")
    if len(edges) < 2:
        return tuple(0 for _ in values), edges
    labels = []
    for value in values:
        index = bisect.bisect_right(edges, value) - 1
        labels.append(max(0, min(index, len(edges) - 2)))
    return tuple(labels), edges


def shannon_entropy(labels: Sequence[int], *, normalize: bool) -> float:
    if not labels:
        raise QuantDataError("Shannon entropy requires labels")
    counts = Counter(labels)
    total = len(labels)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    if not normalize:
        return entropy
    maximum = math.log2(max(len(counts), 1))
    return 0.0 if maximum == 0.0 else entropy / maximum


def ordinal_patterns(
    values: Sequence[float],
    *,
    embedding_dimension: int,
    delay: int,
) -> tuple[tuple[int, ...], ...]:
    required = (embedding_dimension - 1) * delay + 1
    if len(values) < required:
        raise QuantDataError("permutation entropy sample is shorter than the embedding window")
    patterns: list[tuple[int, ...]] = []
    for start in range(0, len(values) - required + 1):
        window = [values[start + offset * delay] for offset in range(embedding_dimension)]
        pattern = tuple(index for index, _ in sorted(enumerate(window), key=lambda item: (item[1], item[0])))
        patterns.append(pattern)
    return tuple(patterns)


def permutation_entropy(
    values: Sequence[float],
    *,
    embedding_dimension: int,
    delay: int,
    normalize: bool,
) -> tuple[float, int, int]:
    patterns = ordinal_patterns(values, embedding_dimension=embedding_dimension, delay=delay)
    counts = Counter(patterns)
    total = len(patterns)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    maximum = math.log2(math.factorial(embedding_dimension))
    if normalize and maximum > 0.0:
        entropy /= maximum
    tie_windows = 0
    required = (embedding_dimension - 1) * delay + 1
    for start in range(0, len(values) - required + 1):
        window = [values[start + offset * delay] for offset in range(embedding_dimension)]
        if len(set(window)) != len(window):
            tie_windows += 1
    return entropy, len(counts), tie_windows


def bin_sensitivity_candidates(bins: int) -> tuple[int, ...]:
    return tuple(sorted({max(2, bins - 2), bins, min(64, bins + 2)}))

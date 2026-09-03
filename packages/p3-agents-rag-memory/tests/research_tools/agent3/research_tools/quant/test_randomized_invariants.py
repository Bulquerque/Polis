from __future__ import annotations

import math
import random

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.dependence import pearson_correlation
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.entropy import shannon_entropy
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.series import quantile


def test_randomized_correlation_symmetry_and_bounds() -> None:
    rng = random.Random(20260804)
    for _ in range(50):
        left = [rng.uniform(-1.0, 1.0) for _ in range(20)]
        right = [rng.uniform(-1.0, 1.0) for _ in range(20)]
        lr = pearson_correlation(left, right)
        rl = pearson_correlation(right, left)
        assert math.isclose(lr, rl, rel_tol=1e-12, abs_tol=1e-12)
        assert -1.0 <= lr <= 1.0


def test_randomized_quantiles_are_monotone_and_bounded() -> None:
    rng = random.Random(20260805)
    for _ in range(50):
        values = [rng.gauss(0.0, 1.0) for _ in range(25)]
        qs = [quantile(values, probability) for probability in (0.05, 0.25, 0.5, 0.75, 0.95)]
        assert qs == sorted(qs)
        assert min(values) <= qs[0] <= qs[-1] <= max(values)


def test_normalized_shannon_stays_in_unit_interval() -> None:
    rng = random.Random(20260806)
    for _ in range(50):
        labels = [rng.randrange(0, 6) for _ in range(40)]
        value = shannon_entropy(labels, normalize=True)
        assert 0.0 <= value <= 1.0

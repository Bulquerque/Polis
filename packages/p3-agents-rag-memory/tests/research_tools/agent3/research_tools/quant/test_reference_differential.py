from __future__ import annotations

import math

import numpy as np
from scipy import stats

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.dependence import (
    pearson_correlation,
    spearman_correlation,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.entropy import shannon_entropy
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.series import quantile, sample_std


def test_pearson_matches_numpy() -> None:
    left = (0.1, -0.2, 0.4, 0.3, -0.1)
    right = (0.2, -0.1, 0.5, 0.25, -0.05)
    expected = float(np.corrcoef(left, right)[0, 1])
    assert math.isclose(pearson_correlation(left, right), expected, rel_tol=1e-12, abs_tol=1e-12)


def test_spearman_matches_scipy_with_ties() -> None:
    left = (1.0, 2.0, 2.0, 4.0, 5.0)
    right = (5.0, 3.0, 3.0, 2.0, 1.0)
    expected = float(stats.spearmanr(left, right).statistic)
    assert math.isclose(spearman_correlation(left, right), expected, rel_tol=1e-12, abs_tol=1e-12)


def test_linear_quantile_matches_numpy() -> None:
    values = (1.0, 3.0, 7.0, 9.0, 12.0)
    for probability in (0.05, 0.25, 0.5, 0.95):
        expected = float(np.quantile(values, probability, method="linear"))
        assert math.isclose(quantile(values, probability), expected, rel_tol=1e-12, abs_tol=1e-12)


def test_sample_std_matches_numpy_ddof_one() -> None:
    values = (0.01, -0.02, 0.03, 0.015, -0.005)
    expected = float(np.std(values, ddof=1))
    assert math.isclose(sample_std(values), expected, rel_tol=1e-12, abs_tol=1e-12)


def test_shannon_matches_scipy_base_two() -> None:
    labels = (0, 0, 1, 1, 1, 2)
    counts = np.array([2, 3, 1], dtype=float)
    expected = float(stats.entropy(counts, base=2))
    assert math.isclose(shannon_entropy(labels, normalize=False), expected, rel_tol=1e-12, abs_tol=1e-12)

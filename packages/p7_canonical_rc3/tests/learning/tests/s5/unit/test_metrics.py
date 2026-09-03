import pytest
import numpy as np
from quant_pipeline.phase_07_strategy_tournament.learning.domain.ranking_metrics import ndcg_at_k, regret_at_k, spearman


def test_perfect_ranking_metrics():
    values=np.array([1.,2.,3.]); scores=np.array([1.,2.,3.]); ids=["a","b","c"]
    assert ndcg_at_k(values,scores,ids,3) == 1.0
    assert regret_at_k(values,scores,ids,1) == 0.0
    assert spearman(values,scores) == pytest.approx(1.0)

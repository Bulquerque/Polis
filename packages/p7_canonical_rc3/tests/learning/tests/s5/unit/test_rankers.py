import numpy as np
from quant_pipeline.phase_07_strategy_tournament.learning.adapters.numpy_pairwise_ranker import PairwiseLinearRanker
from quant_pipeline.phase_07_strategy_tournament.learning.adapters.numpy_pointwise_ranker import PointwiseRidgeRanker


def _data():
    x = np.array([[0.,1.],[1.,0.],[2.,0.],[0.,2.],[1.,1.],[2.,1.]])
    y = np.array([0.,1.,2.,0.,1.,2.])
    q = ["q1"]*3+["q2"]*3
    c = [f"c{i}" for i in range(6)]
    return x,y,q,c


def test_pairwise_orders_known_signal():
    x,y,q,c = _data()
    ranker = PairwiseLinearRanker(alpha=0.1)
    state = ranker.fit(x,y,q,c)
    scores = ranker.predict(x,state)
    assert scores[2] > scores[1] > scores[0]
    assert state["pair_count"] == 6


def test_pairwise_is_deterministic():
    x,y,q,c = _data()
    ranker = PairwiseLinearRanker(alpha=0.1)
    assert ranker.fit(x,y,q,c) == ranker.fit(x,y,q,c)


def test_ridge_orders_known_signal():
    x,y,q,c = _data()
    ranker = PointwiseRidgeRanker(alpha=0.1)
    state = ranker.fit(x,y,q,c)
    scores = ranker.predict(x,state)
    assert scores[2] > scores[0]

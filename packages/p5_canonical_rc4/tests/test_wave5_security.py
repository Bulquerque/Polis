from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from quant_pipeline.phase_05_underlying_forecasts.errors import TrainingError
from quant_pipeline.phase_05_underlying_forecasts.services.sklearn_resolvers import (
    ExtraTreesResolver,
    HistogramGradientBoostingResolver,
    _TRUSTED_PICKLE_HASHES,
)


def _sample() -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray([[0.0], [1.0], [2.0], [3.0], [4.0], [5.0], [6.0], [7.0]], dtype=float)
    y = np.asarray([0.0, 0.9, 2.1, 3.0, 4.2, 4.9, 6.1, 7.0], dtype=float)
    return x, y


@pytest.mark.parametrize(
    ("resolver", "parameters"),
    [
        (ExtraTreesResolver(), {"n_estimators": 8, "max_depth": 3, "min_samples_leaf": 1}),
        (HistogramGradientBoostingResolver(), {"max_iter": 10, "max_leaf_nodes": 3}),
    ],
)
def test_internal_sklearn_state_remains_usable_in_same_process(resolver, parameters) -> None:
    x, y = _sample()
    state = resolver.fit(x, y, parameters, seed=7)
    predicted = resolver.predict(state, x[:2])
    assert predicted.shape == (2,)
    assert state["deserialization_policy"] == "SAME_PROCESS_ONLY"
    assert state["blob_sha256"] in _TRUSTED_PICKLE_HASHES


def test_self_rehashed_external_pickle_never_reaches_pickle_loads() -> None:
    x, y = _sample()
    resolver = ExtraTreesResolver()
    state = resolver.fit(x, y, {"n_estimators": 8, "max_depth": 3, "min_samples_leaf": 1}, seed=7)
    _TRUSTED_PICKLE_HASHES.discard(state["blob_sha256"])
    with patch("quant_pipeline.phase_05_underlying_forecasts.services.sklearn_resolvers.pickle.loads") as loads:
        with pytest.raises(TrainingError, match="not trusted in this process"):
            resolver.predict(state, x[:1])
        loads.assert_not_called()

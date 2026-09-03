from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from quant_pipeline.phase_05_underlying_forecasts.domain.distributions import (
    MixtureComponent,
    MixtureDistribution,
)
from quant_pipeline.phase_05_underlying_forecasts.errors import (
    DataQualityError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_05_underlying_forecasts.services.belief_publication import _horizon_days
from quant_pipeline.phase_05_underlying_forecasts.services.diagnostics import ood_score
from quant_pipeline.phase_05_underlying_forecasts.services.v2_artifacts import distribution_statistics
from quant_pipeline.phase_05_underlying_forecasts.subphases import s7


def test_horizon_hours_use_same_day_semantics_as_p6() -> None:
    assert _horizon_days("24H") == 1
    assert _horizon_days("48H") == 2
    assert _horizon_days("1D") == 1
    assert _horizon_days("1W") == 7
    with pytest.raises(DataQualityError, match="sub-day"):
        _horizon_days("12H")


def test_future_training_cutoff_is_fatal_not_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fatal(*args, **kwargs):
        raise TemporalIntegrityError("future cutoff")

    monkeypatch.setattr(s7, "_model_ood_records", fatal)
    payload = {
        "authorized_consumer_view_registry": {"views": [{"view_id": "v1"}]},
        "qualified_resolver_registry": {"records": [{"resolver_id": "r1", "feature_view_id": "v1"}]},
    }
    with pytest.raises(TemporalIntegrityError, match="future cutoff"):
        s7.m03(payload, as_of_time=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_ood_reference_minimum_scales_with_dimension() -> None:
    reference_2d = np.arange(24, dtype=float).reshape(12, 2)
    result = ood_score(reference_2d, np.array([1.0, 2.0]))
    assert result["minimum_reference_rows"] == 12
    reference_3d = np.arange(36, dtype=float).reshape(12, 3)
    with pytest.raises(DataQualityError, match="at least 15"):
        ood_score(reference_3d, np.array([1.0, 2.0, 3.0]))


def test_mixture_mode_and_tail_semantics_are_explicit() -> None:
    distribution = MixtureDistribution(components=(
        MixtureComponent(family="NORMAL", weight=0.7, location=-1.0, scale=0.5),
        MixtureComponent(family="NORMAL", weight=0.3, location=2.0, scale=1.0),
    ))
    stats = distribution_statistics(distribution)
    assert stats["mode_method"] == "NUMERICAL_GLOBAL_GRID_PLUS_BOUNDED_REFINEMENT"
    assert stats["mode"] == pytest.approx(-1.0, abs=0.15)
    assert stats["tail_probability_semantics"] == "CDF_EVALUATED_AT_PUBLISHED_QUANTILES"
    assert set(stats["tail_probabilities"]) == {
        "probability_below_or_equal_q01",
        "probability_below_or_equal_q05",
        "probability_above_q95",
        "probability_above_q99",
    }

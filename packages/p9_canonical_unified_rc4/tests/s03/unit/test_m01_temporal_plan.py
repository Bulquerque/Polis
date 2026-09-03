from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import DurationSpec, TimeWindow
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.errors import TemporalIntegrityError
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m01_temporal_plan import (
    build_temporal_evaluation_plan,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.temporal_models import (
    TemporalPlanPolicy,
    WindowMode,
)

from tests.s03.conftest import utc_day


def policy(**overrides):
    values = dict(
        policy_id="temporal-v1",
        dataset_window=TimeWindow(start=utc_day(0), end=utc_day(140)),
        initial_train=DurationSpec(seconds=30 * 86400),
        tuning=DurationSpec(seconds=10 * 86400),
        test=DurationSpec(seconds=10 * 86400),
        step=DurationSpec(seconds=10 * 86400),
        embargo=DurationSpec(seconds=2 * 86400),
        holdout=DurationSpec(seconds=20 * 86400),
        minimum_outer_folds=2,
    )
    values.update(overrides)
    return TemporalPlanPolicy(**values)


def test_builds_ordered_folds_and_reserved_holdout():
    result = build_temporal_evaluation_plan(policy())
    assert len(result.folds) >= 2
    assert all(fold.test_window.end <= result.holdout_firewall.holdout_window.start for fold in result.folds)
    assert result.folds[0].train_window.start == utc_day(0)
    assert result.folds[0].train_window.duration() >= timedelta(days=30)


def test_is_deterministic():
    first = build_temporal_evaluation_plan(policy())
    second = build_temporal_evaluation_plan(policy())
    assert first == second
    assert first.content_sha256 == second.content_sha256


def test_rolling_window_limits_train_history():
    result = build_temporal_evaluation_plan(
        policy(
            window_mode=WindowMode.ROLLING,
            max_train=DurationSpec(seconds=40 * 86400),
        )
    )
    assert all(fold.train_window.duration() <= timedelta(days=40) for fold in result.folds)


def test_rejects_overlapping_test_windows_by_default():
    with pytest.raises(ValueError, match="step must be"):
        policy(step=DurationSpec(seconds=5 * 86400))


def test_can_explicitly_allow_overlapping_test_windows():
    result = build_temporal_evaluation_plan(
        policy(
            step=DurationSpec(seconds=5 * 86400),
            allow_overlapping_test_windows=True,
        )
    )
    assert len(result.folds) > 2


def test_rejects_infeasible_history():
    short = policy(
        dataset_window=TimeWindow(start=utc_day(0), end=utc_day(50)),
        holdout=DurationSpec(seconds=20 * 86400),
        minimum_outer_folds=2,
    )
    with pytest.raises(TemporalIntegrityError):
        build_temporal_evaluation_plan(short)


def test_holdout_must_be_positive():
    with pytest.raises(ValueError, match="holdout must be positive"):
        policy(holdout=DurationSpec(seconds=0))

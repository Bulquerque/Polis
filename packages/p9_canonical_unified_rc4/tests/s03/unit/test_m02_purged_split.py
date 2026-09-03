from __future__ import annotations

import random
from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import DurationSpec, TimeWindow
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.errors import TemporalIntegrityError
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m01_temporal_plan import build_temporal_evaluation_plan
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m02_purged_walk_forward import (
    build_purged_walk_forward_assignments,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.temporal_models import (
    SampleRecord,
    SampleRole,
    TemporalPlanPolicy,
)

from tests.s03.conftest import utc_day


def make_plan():
    return build_temporal_evaluation_plan(
        TemporalPlanPolicy(
            policy_id="temporal-v1",
            dataset_window=TimeWindow(start=utc_day(0), end=utc_day(100)),
            initial_train=DurationSpec(seconds=20 * 86400),
            tuning=DurationSpec(seconds=5 * 86400),
            test=DurationSpec(seconds=5 * 86400),
            step=DurationSpec(seconds=5 * 86400),
            embargo=DurationSpec(seconds=86400),
            holdout=DurationSpec(seconds=10 * 86400),
            minimum_outer_folds=2,
        )
    )


def sample(record_id: str, day: int, label_end: int | None = None, available_day: int | None = None):
    return SampleRecord(
        record_id=record_id,
        entity_id="ABC",
        decision_time=utc_day(day),
        available_at=utc_day(day if available_day is None else available_day),
        label_start_time=utc_day(day),
        label_end_time=utc_day(label_end if label_end is not None else day + 1),
        vintage_time=utc_day(day if available_day is None else available_day),
    )


def test_assigns_train_tuning_test_and_excluded():
    plan = make_plan()
    fold = plan.folds[0]
    records_list = [
        sample("train", (fold.train_window.start - utc_day(0)).days + 1),
        sample("tune", (fold.tuning_window.start - utc_day(0)).days + 1),
        sample("test", (fold.test_window.start - utc_day(0)).days + 1),
        sample("outside", 99),
    ]
    for extra_fold in plan.folds[1:]:
        index = extra_fold.outer_index
        records_list.extend(
            [
                sample(f"train-{index}", (extra_fold.train_window.start - utc_day(0)).days + 1),
                sample(f"tune-{index}", (extra_fold.tuning_window.start - utc_day(0)).days + 1),
                sample(f"test-{index}", (extra_fold.test_window.start - utc_day(0)).days + 1),
            ]
        )
    records = tuple(records_list)
    panel, receipt = build_purged_walk_forward_assignments(plan, records)
    selected_ids = {"train", "tune", "test", "outside"}
    first_roles = {
        item.record_id: item.role
        for item in panel.assignments
        if item.fold_id == fold.fold_id and item.record_id in selected_ids
    }
    assert first_roles == {
        "train": SampleRole.TRAIN,
        "tune": SampleRole.TUNING,
        "test": SampleRole.TEST,
        "outside": SampleRole.EXCLUDED,
    }
    assert receipt.status == "VALID"


def test_purges_training_label_that_overlaps_tuning_or_test():
    plan = make_plan()
    fold = plan.folds[0]
    day = (fold.train_window.end - utc_day(0)).days - 2
    record = sample("overlap", day, label_end=(fold.tuning_window.start - utc_day(0)).days + 1)
    panel, _ = build_purged_walk_forward_assignments(plan, (record,))
    assignment = next(item for item in panel.assignments if item.fold_id == fold.fold_id)
    assert assignment.role is SampleRole.EXCLUDED
    assert "P9_S3_LABEL_OVERLAP_PURGED" in assignment.reason_codes


def test_rejects_late_availability_point_in_time():
    plan = make_plan()
    record = sample("late", 2, available_day=3)
    panel, receipt = build_purged_walk_forward_assignments(plan, (record,))
    assert all(item.role is SampleRole.EXCLUDED for item in panel.assignments)
    assert "P9_S3_PIT_AVAILABILITY_VIOLATION" in receipt.reason_codes


def test_is_permutation_invariant():
    plan = make_plan()
    records = [sample(f"r{i}", i + 1) for i in range(60)]
    first, first_receipt = build_purged_walk_forward_assignments(plan, tuple(records))
    random.Random(123).shuffle(records)
    second, second_receipt = build_purged_walk_forward_assignments(plan, tuple(records))
    assert first == second
    assert first_receipt == second_receipt


def test_duplicate_record_ids_fail_closed():
    plan = make_plan()
    with pytest.raises(TemporalIntegrityError, match="DUPLICATE_RECORD_ID"):
        build_purged_walk_forward_assignments(plan, (sample("dup", 1), sample("dup", 2)))


def test_sample_label_interval_must_be_positive():
    with pytest.raises(ValueError, match="positive duration"):
        sample("bad", 2, label_end=2)

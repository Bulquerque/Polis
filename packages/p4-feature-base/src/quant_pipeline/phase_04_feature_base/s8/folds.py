from __future__ import annotations
from datetime import datetime, timedelta
from .records import RepresentationPolicy
from .errors import S8Error


def build_fold_records(times: tuple[datetime, ...], policy: RepresentationPolicy) -> list[dict[str, object]]:
    if len(times) < policy.min_train_timestamps + policy.validation_timestamps:
        raise S8Error("P4_S8_INSUFFICIENT_TIMESTAMPS", "not enough timestamps for one outer fold")
    all_records: list[dict[str, object]] = []
    validation_start = policy.min_train_timestamps
    while validation_start + policy.validation_timestamps <= len(times):
        train_start = 0
        if policy.fold_mode == "rolling":
            assert policy.rolling_train_timestamps is not None
            train_start = max(0, validation_start - policy.rolling_train_timestamps)
        train_times = times[train_start:validation_start]
        validation_times = times[validation_start:validation_start + policy.validation_timestamps]
        all_records.append({"fold_id": f"fold-{len(all_records)+1:02d}", "fit_start": train_times[0].isoformat(),
            "fit_end": train_times[-1].isoformat(), "transform_start": validation_times[0].isoformat(),
            "transform_end": validation_times[-1].isoformat(), "train_timestamp_count": len(train_times),
            "validation_timestamp_count": len(validation_times), "fold_mode": policy.fold_mode})
        validation_start += policy.step_timestamps
    if not all_records:
        raise S8Error("P4_S8_NO_FOLDS", "fold policy produced no folds")
    # Longitudinal inputs can begin before a feature family is observable.  The
    # latest bounded folds are the production-relevant evaluation window and
    # avoid making the entire representation stage empty because of an
    # uninformative early warm-up.  Every fit still ends before its validation
    # interval, so this does not relax the PIT boundary.
    multi_vintage = times[-1] - times[0] > timedelta(days=365)
    records = (
        all_records[-policy.max_outer_folds :]
        if multi_vintage
        else all_records[: policy.max_outer_folds]
    )
    for index, record in enumerate(records, start=1):
        record["fold_id"] = f"fold-{index:02d}"
    return records


def rows_for_interval(row_keys: tuple[tuple[datetime, str], ...], start: datetime, end: datetime) -> list[int]:
    return [index for index, (time, _) in enumerate(row_keys) if start <= time <= end]

from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pytest

from quant_pipeline.phase_05_underlying_forecasts.errors import DataQualityError, LeakageError
from quant_pipeline.phase_05_underlying_forecasts.services.calendar import WeekdayTradingCalendar
from quant_pipeline.phase_05_underlying_forecasts.services.tabular import (
    assert_no_forbidden_fields,
    feature_rows,
    multivariate_series,
    normalize_view_bundle,
    semantic_series,
    target_rows,
)

UTC = timezone.utc


def test_calendar_complete_fail_closed_surface() -> None:
    calendar = WeekdayTradingCalendar(holidays=frozenset({date(2026, 8, 3)}), close_hour_utc=20)
    friday = datetime(2026, 7, 31, 15, 30, tzinfo=UTC)

    assert calendar.advance_sessions(friday, 0) == friday
    assert calendar.advance_sessions(friday, 1).date() == date(2026, 8, 4)
    assert calendar.previous_session(datetime(2026, 8, 4, 15, 30, tzinfo=UTC)).date() == date(2026, 7, 31)
    assert calendar.session_close(date(2026, 8, 4)).hour == 20
    assert calendar.horizon_end(friday, "2H").hour == 17
    assert calendar.horizon_end(friday, "1W").date() == date(2026, 8, 10)
    assert calendar.horizon_end(friday, "1M") > friday

    with pytest.raises(DataQualityError):
        calendar.advance_sessions(friday, -1)
    with pytest.raises(DataQualityError):
        calendar.session_close(date(2026, 8, 1))
    with pytest.raises(DataQualityError):
        calendar.horizon_end(friday, "1Q")


def test_recursive_forbidden_field_detection() -> None:
    with pytest.raises(LeakageError):
        assert_no_forbidden_fields({"outer": [{"future_return": 1.0}]})


def _valid_view_record() -> dict[str, object]:
    stamp = datetime(2026, 7, 31, 20, tzinfo=UTC)
    return {
        "underlying": "AAA",
        "decision_time": stamp,
        "available_at": stamp,
        "horizon_group": "SHORT",
        "features": {"x": 1.0},
        "lineage_id": "lin-row",
    }


def _valid_bundle() -> dict[str, object]:
    return {
        "views": [{
            "view_id": "TABULAR_INTERPRETABLE",
            "quality_state": "PASS",
            "lineage_id": "lin-view",
            "grain": ["underlying", "decision_time", "horizon_group"],
            "missingness_policy": "EXPLICIT_MASK",
            "records": [_valid_view_record()],
        }]
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda view: view.update({"quality_state": "FAILED"}),
        lambda view: view.update({"lineage_id": ""}),
        lambda view: view.update({"grain": ["underlying"]}),
        lambda view: view.update({"missingness_policy": "MAGIC"}),
        lambda view: view.update({"records": ["bad-record"]}),
    ],
)
def test_view_bundle_rejects_invalid_contracts(mutation) -> None:
    bundle = _valid_bundle()
    view = bundle["views"][0]
    mutation(view)
    with pytest.raises(DataQualityError):
        normalize_view_bundle(bundle)


def test_view_bundle_rejects_duplicate_ids() -> None:
    bundle = _valid_bundle()
    bundle["views"].append(dict(bundle["views"][0]))
    with pytest.raises(DataQualityError):
        normalize_view_bundle(bundle)


def test_feature_rows_temporal_and_numeric_guards() -> None:
    bundle = _valid_bundle()
    view = normalize_view_bundle(bundle)["TABULAR_INTERPRETABLE"]
    stamp = view["records"][0]["decision_time"]
    assert feature_rows(view, as_of_time=stamp)
    assert feature_rows(view, as_of_time=datetime(2026, 7, 30, tzinfo=UTC)) == []

    future = dict(view["records"][0])
    future["available_at"] = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises(LeakageError):
        feature_rows({**view, "records": [future]})

    nonfinite = dict(view["records"][0])
    nonfinite["features"] = {"x": np.inf}
    with pytest.raises(DataQualityError):
        feature_rows({**view, "records": [nonfinite]})


def test_target_rows_rejects_temporal_duplicates_and_invalid_values() -> None:
    prediction = datetime(2026, 7, 1, tzinfo=UTC)
    label_end = datetime(2026, 7, 2, tzinfo=UTC)
    base = {
        "underlying": "AAA",
        "prediction_timestamp": prediction,
        "label_end_time": label_end,
        "available_at": label_end,
        "target_id": "RETURN_1D",
        "horizon": "1D",
        "unit": "decimal_return",
        "value": 0.01,
        "lineage_id": "target-lineage",
    }
    assert len(target_rows({"records": [base]})) == 1

    with pytest.raises(DataQualityError):
        target_rows({"records": [base, dict(base)]})
    with pytest.raises(DataQualityError):
        target_rows({"records": [{**base, "available_at": prediction}]})
    with pytest.raises(DataQualityError):
        target_rows({"records": [{**base, "value": -1.5}]})
    with pytest.raises(DataQualityError):
        target_rows({"records": [{**base, "lineage_id": ""}]})


def test_multivariate_and_semantic_fail_closed() -> None:
    view = normalize_view_bundle(_valid_bundle())["TABULAR_INTERPRETABLE"]
    with pytest.raises(DataQualityError):
        multivariate_series(view, "x")
    with pytest.raises(DataQualityError):
        semantic_series(view, "NON_EXISTENT_ROLE")

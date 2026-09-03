"""Event-window diagnostics anchored only on already observable market records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import JsonValue

from .model_base import EventAdjustment, ReturnKind
from .ports import EventWindowNotMatureError, QuantDataError, parse_datetime
from .series import MarketBar, compute_returns


EVENT_TIME_ADAPTER_VERSION = "p3.s39.event-time-adapter.v1"


def adapt_event_record(record: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Normalize the canonical daily event boundary without inventing an instant."""
    adapted = dict(record)
    if record.get("event_time") is not None:
        adapted["event_time_source"] = "event_time"
        adapted["event_time_precision"] = "INSTANT"
    elif record.get("observed_at") is not None:
        adapted["event_time"] = record["observed_at"]
        adapted["event_time_source"] = "observed_at"
        adapted["event_time_precision"] = "INSTANT"
    elif record.get("reference_date") is not None:
        reference_date = record["reference_date"]
        if not isinstance(reference_date, str):
            raise QuantDataError("reference_date must be an ISO date")
        try:
            day = datetime.fromisoformat(reference_date[:10]).date()
        except ValueError as exc:
            raise QuantDataError(f"invalid reference_date: {reference_date}") from exc
        adapted["event_time"] = datetime.combine(day, datetime.min.time(), tzinfo=UTC).isoformat()
        adapted["event_time_source"] = "reference_date_daily_start"
        adapted["event_time_precision"] = "DAILY"
    else:
        raise QuantDataError(
            "event_time is missing and no approved observed_at/reference_date adapter is available"
        )
    adapted["event_time_adapter_version"] = EVENT_TIME_ADAPTER_VERSION
    return adapted


def event_time_from_records(
    records: Sequence[Mapping[str, JsonValue]],
    *,
    event_id: str,
) -> tuple[datetime, Mapping[str, JsonValue]]:
    matches = [record for record in records if str(record.get("event_id")) == event_id]
    if not matches:
        raise QuantDataError(f"event not found: {event_id}")
    if len(matches) != 1:
        raise QuantDataError(f"event_id is not unique: {event_id}")
    record = adapt_event_record(matches[0])
    return parse_datetime(record.get("event_time"), field_name="event_time"), record


def _anchor_index(bars: Sequence[MarketBar], event_time: datetime) -> int:
    for index, bar in enumerate(bars):
        if bar.observation_time >= event_time:
            return index
    raise EventWindowNotMatureError("no market observation exists on or after event_time")


def _window_returns(
    bars: Sequence[MarketBar],
    *,
    anchor: int,
    pre_window: int,
    post_window: int,
    return_kind: ReturnKind,
) -> tuple[tuple[datetime, float], ...]:
    start = anchor - pre_window
    end = anchor + post_window
    if start < 0 or end >= len(bars):
        raise EventWindowNotMatureError("requested event window is not fully observable")
    selected = bars[start : end + 1]
    returns = compute_returns(selected, return_kind)
    return tuple((point.observation_time, point.value) for point in returns)


def _compound(values: Sequence[float], kind: ReturnKind) -> float:
    if kind is ReturnKind.LOG:
        return sum(values)
    wealth = 1.0
    for value in values:
        wealth *= 1.0 + value
    return wealth - 1.0


def event_window_metrics(
    *,
    bars: Sequence[MarketBar],
    event_time: datetime,
    pre_window: int,
    post_window: int,
    return_kind: ReturnKind,
    adjustment: EventAdjustment,
    benchmark_bars: Sequence[MarketBar] = (),
) -> tuple[dict[str, float | int | str], tuple[dict[str, float | str], ...]]:
    anchor = _anchor_index(bars, event_time)
    instrument = _window_returns(
        bars,
        anchor=anchor,
        pre_window=pre_window,
        post_window=post_window,
        return_kind=return_kind,
    )
    benchmark_map: dict[datetime, float] = {}
    if adjustment is EventAdjustment.BENCHMARK:
        benchmark_anchor = _anchor_index(benchmark_bars, event_time)
        benchmark = _window_returns(
            benchmark_bars,
            anchor=benchmark_anchor,
            pre_window=pre_window,
            post_window=post_window,
            return_kind=return_kind,
        )
        benchmark_map = dict(benchmark)
        if set(benchmark_map) != {time for time, _ in instrument}:
            raise QuantDataError("benchmark and instrument event windows are not aligned")
    rows: list[dict[str, float | str]] = []
    adjusted_values: list[float] = []
    for time, value in instrument:
        adjusted = value - benchmark_map.get(time, 0.0)
        adjusted_values.append(adjusted)
        rows.append(
            {
                "observation_time": time.isoformat(),
                "instrument_return": value,
                "benchmark_return": benchmark_map.get(time, 0.0),
                "adjusted_return": adjusted,
            }
        )
    metrics: dict[str, float | int | str] = {
        "event_time": event_time.isoformat(),
        "pre_window": pre_window,
        "post_window": post_window,
        "return_observation_count": len(adjusted_values),
        "cumulative_adjusted_return": _compound(adjusted_values, return_kind),
        "adjustment": adjustment.value,
    }
    return metrics, tuple(rows)

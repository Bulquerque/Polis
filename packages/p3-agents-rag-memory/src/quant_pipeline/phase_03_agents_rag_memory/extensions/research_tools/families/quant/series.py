"""Deterministic parsing, alignment and descriptive primitives for market series."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from .model_base import ReturnKind
from .ports import QuantDataError, parse_datetime


@dataclass(frozen=True, slots=True)
class MarketBar:
    observation_time: datetime
    available_at: datetime
    close: float
    open: float | None
    high: float | None
    low: float | None
    record: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    observation_time: datetime
    value: float


def _finite_number(value: JsonValue, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QuantDataError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise QuantDataError(f"{field_name} must be finite")
    return result


def parse_market_bars(records: Sequence[Mapping[str, JsonValue]]) -> tuple[MarketBar, ...]:
    bars: list[MarketBar] = []
    for record in records:
        observation_time = parse_datetime(record.get("observation_time"), field_name="observation_time")
        available_at = parse_datetime(record.get("available_at"), field_name="available_at")
        close = _finite_number(record.get("close"), field_name="close")
        if close <= 0.0:
            raise QuantDataError("close must be positive")
        ohl = []
        for field in ("open", "high", "low"):
            raw = record.get(field)
            value = None if raw is None else _finite_number(raw, field_name=field)
            if value is not None and value <= 0.0:
                raise QuantDataError(f"{field} must be positive")
            ohl.append(value)
        open_value, high, low = ohl
        if high is not None and low is not None and high < low:
            raise QuantDataError("high must not be below low")
        if high is not None and high < close:
            raise QuantDataError("high must not be below close")
        if low is not None and low > close:
            raise QuantDataError("low must not be above close")
        if open_value is not None and high is not None and high < open_value:
            raise QuantDataError("high must not be below open")
        if open_value is not None and low is not None and low > open_value:
            raise QuantDataError("low must not be above open")
        bars.append(
            MarketBar(
                observation_time=observation_time,
                available_at=available_at,
                close=close,
                open=open_value,
                high=high,
                low=low,
                record=dict(record),
            )
        )
    bars.sort(key=lambda item: item.observation_time)
    timestamps = [bar.observation_time for bar in bars]
    if len(timestamps) != len(set(timestamps)):
        raise QuantDataError("market series contains duplicate observation_time values")
    return tuple(bars)


def compute_returns(bars: Sequence[MarketBar], kind: ReturnKind) -> tuple[ReturnPoint, ...]:
    points: list[ReturnPoint] = []
    for previous, current in zip(bars, bars[1:], strict=False):
        ratio = current.close / previous.close
        value = ratio - 1.0 if kind is ReturnKind.SIMPLE else math.log(ratio)
        points.append(ReturnPoint(current.observation_time, value))
    return tuple(points)


def quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise QuantDataError("quantile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise QuantDataError("sample standard deviation requires at least two values")
    return statistics.stdev(values)


def median_absolute_deviation(values: Sequence[float]) -> float:
    if not values:
        raise QuantDataError("median absolute deviation requires values")
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def trimmed_mean(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise QuantDataError("trimmed mean requires values")
    ordered = sorted(values)
    trim = int(len(ordered) * fraction)
    if trim * 2 >= len(ordered):
        raise QuantDataError("trim fraction removes every observation")
    sample = ordered[trim : len(ordered) - trim] if trim else ordered
    return statistics.fmean(sample)


def average_ranks(values: Sequence[float]) -> tuple[float, ...]:
    indexed = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average = ((cursor + 1) + end) / 2.0
        for original_index, _ in indexed[cursor:end]:
            ranks[original_index] = average
        cursor = end
    return tuple(ranks)


def align_returns(
    left: Sequence[ReturnPoint],
    right: Sequence[ReturnPoint],
) -> tuple[tuple[datetime, float, float], ...]:
    left_map = {point.observation_time: point.value for point in left}
    right_map = {point.observation_time: point.value for point in right}
    times = sorted(set(left_map) & set(right_map))
    return tuple((time, left_map[time], right_map[time]) for time in times)


def json_number(value: float) -> float:
    if not math.isfinite(value):
        raise QuantDataError("numeric result is not finite")
    return float(value)


def record_count(records: Sequence[Mapping[str, Any]]) -> int:
    return len(records)

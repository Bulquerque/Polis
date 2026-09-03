from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..feature_records import records_from_series
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec
from ..observation_frame import build_numeric_wide, entity_groups
from ..provenance import ProvenanceIndex

MODULE_ID = "P4.S4.M03"
SUPPORTED_OBSERVERS = {
    "risk.realized_volatility",
    "risk.downside_semivariance",
    "risk.drawdown",
    "risk.drawdown_duration",
    "risk.skewness",
    "risk.kurtosis",
    "risk.vol_of_vol",
}


def _window(spec: ObserverSpec, default: int) -> int:
    value = int(spec.parameters.get("window", default))
    if value < 2:
        raise ValueError("window must be >= 2")
    return value


def _drawdown_duration(close: pd.Series, window: int) -> pd.Series:
    running_max = close.rolling(window, min_periods=1).max()
    below = close.lt(running_max)
    durations: list[float] = []
    current = 0
    for is_below in below.fillna(False):
        current = min(current + 1, window) if is_below else 0
        durations.append(float(current))
    return pd.Series(durations, index=close.index, dtype=float)


def _series(close: pd.Series, spec: ObserverSpec) -> tuple[pd.Series, str]:
    returns = np.log(close.where(close > 0)).diff()
    observer_id = spec.observer_id
    if observer_id == "risk.realized_volatility":
        window = _window(spec, 21)
        return returns.rolling(window, min_periods=window).std(ddof=1).mul(math.sqrt(252.0)), "annualized_volatility"
    if observer_id == "risk.downside_semivariance":
        window = _window(spec, 21)
        downside = returns.where(returns < 0, 0.0).pow(2)
        return downside.rolling(window, min_periods=window).mean().mul(252.0), "annualized_variance"
    if observer_id == "risk.drawdown":
        window = _window(spec, 63)
        peak = close.rolling(window, min_periods=1).max()
        return close.div(peak.where(peak > 0)).sub(1.0), "return"
    if observer_id == "risk.drawdown_duration":
        return _drawdown_duration(close, _window(spec, 63)), "sessions"
    if observer_id == "risk.skewness":
        window = _window(spec, 63)
        return returns.rolling(window, min_periods=window).skew(), "skewness"
    if observer_id == "risk.kurtosis":
        window = _window(spec, 63)
        return returns.rolling(window, min_periods=window).kurt(), "excess_kurtosis"
    if observer_id == "risk.vol_of_vol":
        window = _window(spec, 21)
        base_window = int(spec.parameters.get("base_window", 5))
        if base_window < 2:
            raise ValueError("base_window must be >= 2")
        rv = returns.rolling(base_window, min_periods=base_window).std(ddof=1).mul(math.sqrt(252.0))
        return rv.rolling(window, min_periods=window).std(ddof=1), "volatility_of_volatility"
    raise KeyError(observer_id)


def _required_close_count(spec: ObserverSpec) -> int:
    observer_id = spec.observer_id
    if observer_id in {"risk.realized_volatility", "risk.downside_semivariance", "risk.skewness", "risk.kurtosis"}:
        return _window(spec, 21 if "variance" in observer_id or "volatility" in observer_id else 63) + 1
    if observer_id == "risk.vol_of_vol":
        return _window(spec, 21) + int(spec.parameters.get("base_window", 5)) + 1
    return _window(spec, 63)


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    frame = build_numeric_wide(observations, variable_prefixes=("market.",))
    provenance_index = ProvenanceIndex(observations)
    output: list[AtomicFeatureRecord] = []
    for entity_id, group in entity_groups(frame.values):
        close = group.get("market.close")
        if close is None:
            continue
        for spec in specs:
            series, unit = _series(close, spec)
            count = _required_close_count(spec)
            provenance = {
                decision_time: provenance_index.collect(
                    entity_id=entity_id,
                    decision_time=decision_time,
                    requirements={"market.close": count},
                )
                for decision_time in series.index
            }
            output.extend(
                records_from_series(
                    entity_id=entity_id,
                    series=series,
                    spec=spec,
                    unit=unit,
                    provenance_by_time=provenance,
                    attributes={
                        "window": spec.parameters.get("window"),
                        "base_window": spec.parameters.get("base_window"),
                    },
                )
            )
    return output

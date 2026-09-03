from __future__ import annotations

import numpy as np
import pandas as pd

from ..feature_records import records_from_series
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec
from ..observation_frame import build_numeric_wide, entity_groups
from ..provenance import ProvenanceIndex

MODULE_ID = "P4.S4.M01"
SUPPORTED_OBSERVERS = {
    "price.simple_return_1",
    "price.log_return_1",
    "price.overnight_return_1",
    "price.intraday_return_1",
    "price.gap_return_1",
    "price.true_range",
    "price.close_location",
}


def _series_for_observer(group: pd.DataFrame, observer_id: str) -> tuple[pd.Series, str]:
    close = group.get("market.close")
    if close is None:
        return pd.Series(index=group.index, dtype=float), "ratio"
    previous_close = close.shift(1)
    if observer_id == "price.simple_return_1":
        return close.pct_change(fill_method=None), "return"
    if observer_id == "price.log_return_1":
        return np.log(close.where(close > 0)).diff(), "log_return"
    open_price = group.get("market.open")
    if observer_id in {"price.overnight_return_1", "price.gap_return_1"}:
        if open_price is None:
            return pd.Series(index=group.index, dtype=float), "return"
        return open_price.div(previous_close.where(previous_close != 0)).sub(1.0), "return"
    if observer_id == "price.intraday_return_1":
        if open_price is None:
            return pd.Series(index=group.index, dtype=float), "return"
        return close.div(open_price.where(open_price != 0)).sub(1.0), "return"
    high = group.get("market.high")
    low = group.get("market.low")
    if observer_id == "price.true_range":
        if high is None or low is None:
            return pd.Series(index=group.index, dtype=float), "price"
        values = pd.concat(
            [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()], axis=1
        )
        return values.max(axis=1), "price"
    if observer_id == "price.close_location":
        if high is None or low is None:
            return pd.Series(index=group.index, dtype=float), "ratio"
        width = (high - low).where((high - low) > 0)
        return close.sub(low).div(width), "ratio"
    raise KeyError(observer_id)


def _requirements(observer_id: str) -> dict[str, int]:
    if observer_id in {"price.simple_return_1", "price.log_return_1"}:
        return {"market.close": 2}
    if observer_id in {"price.overnight_return_1", "price.gap_return_1"}:
        return {"market.open": 1, "market.close": 2}
    if observer_id == "price.intraday_return_1":
        return {"market.open": 1, "market.close": 1}
    if observer_id == "price.true_range":
        return {"market.high": 1, "market.low": 1, "market.close": 2}
    return {"market.high": 1, "market.low": 1, "market.close": 1}


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    frame = build_numeric_wide(observations, variable_prefixes=("market.",))
    provenance_index = ProvenanceIndex(observations)
    output: list[AtomicFeatureRecord] = []
    for entity_id, group in entity_groups(frame.values):
        for spec in specs:
            series, unit = _series_for_observer(group, spec.observer_id)
            provenance = {
                decision_time: provenance_index.collect(
                    entity_id=entity_id,
                    decision_time=decision_time,
                    requirements=_requirements(spec.observer_id),
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
                    attributes={"calculation": spec.observer_id},
                )
            )
    return output

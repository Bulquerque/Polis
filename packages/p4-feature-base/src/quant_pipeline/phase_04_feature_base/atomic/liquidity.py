from __future__ import annotations

import pandas as pd

from ..feature_records import records_from_series
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec
from ..observation_frame import build_numeric_wide, entity_groups
from ..provenance import ProvenanceIndex

MODULE_ID = "P4.S4.M02"
SUPPORTED_OBSERVERS = {
    "liquidity.relative_spread",
    "liquidity.turnover",
    "liquidity.relative_volume",
    "liquidity.amihud",
    "liquidity.stale_frequency",
}


def _window(spec: ObserverSpec, default: int = 21) -> int:
    value = int(spec.parameters.get("window", default))
    if value < 2:
        raise ValueError("window must be >= 2")
    return value


def _series(group: pd.DataFrame, spec: ObserverSpec) -> tuple[pd.Series, str]:
    observer_id = spec.observer_id
    if observer_id == "liquidity.relative_spread":
        bid, ask = group.get("market.bid"), group.get("market.ask")
        if bid is None or ask is None:
            return pd.Series(index=group.index, dtype=float), "ratio"
        midpoint = (bid + ask).div(2.0).where((ask >= bid) & ((bid + ask) > 0))
        return ask.sub(bid).div(midpoint), "ratio"
    volume = group.get("market.volume")
    if observer_id == "liquidity.turnover":
        shares = group.get("market.shares_outstanding")
        if volume is None or shares is None:
            return pd.Series(index=group.index, dtype=float), "ratio"
        return volume.div(shares.where(shares > 0)), "ratio"
    if observer_id == "liquidity.relative_volume":
        if volume is None:
            return pd.Series(index=group.index, dtype=float), "ratio"
        window = _window(spec)
        baseline = volume.rolling(window, min_periods=window).median().shift(1)
        return volume.div(baseline.where(baseline > 0)), "ratio"
    close = group.get("market.close")
    if observer_id == "liquidity.amihud":
        financial_volume = group.get("market.financial_volume")
        if close is None or financial_volume is None:
            return pd.Series(index=group.index, dtype=float), "return_per_currency"
        window = _window(spec)
        daily = close.pct_change(fill_method=None).abs().div(financial_volume.where(financial_volume > 0))
        return daily.rolling(window, min_periods=window).mean().mul(1_000_000.0), "return_per_million_currency"
    if observer_id == "liquidity.stale_frequency":
        if close is None:
            return pd.Series(index=group.index, dtype=float), "ratio"
        window = _window(spec)
        unchanged = close.eq(close.shift(1)).astype(float)
        return unchanged.rolling(window, min_periods=window).mean(), "ratio"
    raise KeyError(observer_id)


def _requirements(spec: ObserverSpec) -> dict[str, int]:
    observer_id = spec.observer_id
    if observer_id == "liquidity.relative_spread":
        return {"market.bid": 1, "market.ask": 1}
    if observer_id == "liquidity.turnover":
        return {"market.volume": 1, "market.shares_outstanding": 1}
    window = _window(spec)
    if observer_id == "liquidity.relative_volume":
        return {"market.volume": window + 1}
    if observer_id == "liquidity.amihud":
        return {"market.close": window + 1, "market.financial_volume": window}
    return {"market.close": window + 1}


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    frame = build_numeric_wide(observations, variable_prefixes=("market.",))
    provenance_index = ProvenanceIndex(observations)
    output: list[AtomicFeatureRecord] = []
    for entity_id, group in entity_groups(frame.values):
        for spec in specs:
            series, unit = _series(group, spec)
            requirements = _requirements(spec)
            provenance = {
                decision_time: provenance_index.collect(
                    entity_id=entity_id,
                    decision_time=decision_time,
                    requirements=requirements,
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
                    attributes={"window": spec.parameters.get("window")},
                )
            )
    return output

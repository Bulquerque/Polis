from __future__ import annotations

import pandas as pd

from ..feature_records import records_from_series
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec
from ..observation_frame import build_numeric_wide, entity_groups
from ..provenance import ProvenanceIndex

MODULE_ID = "P4.S4.M08"
SUPPORTED_OBSERVERS = {
    "fundamental.book_to_market",
    "fundamental.earnings_yield",
    "fundamental.gross_profitability",
    "fundamental.operating_profitability",
    "fundamental.leverage",
    "fundamental.accruals",
    "fundamental.asset_growth",
}


def _ratio(numerator: pd.Series | None, denominator: pd.Series | None) -> pd.Series:
    if numerator is None or denominator is None:
        index = numerator.index if numerator is not None else denominator.index if denominator is not None else None
        return pd.Series(index=index, dtype=float)
    return numerator.div(denominator.where(denominator != 0))


def _series(group: pd.DataFrame, observer_id: str) -> tuple[pd.Series, str]:
    if observer_id == "fundamental.book_to_market":
        return _ratio(group.get("fundamental.book_equity"), group.get("fundamental.market_cap")), "ratio"
    if observer_id == "fundamental.earnings_yield":
        return _ratio(group.get("fundamental.net_income_ttm"), group.get("fundamental.market_cap")), "ratio"
    if observer_id == "fundamental.gross_profitability":
        return _ratio(group.get("fundamental.gross_profit_ttm"), group.get("fundamental.total_assets")), "ratio"
    if observer_id == "fundamental.operating_profitability":
        return _ratio(group.get("fundamental.operating_income_ttm"), group.get("fundamental.book_equity")), "ratio"
    if observer_id == "fundamental.leverage":
        return _ratio(group.get("fundamental.total_debt"), group.get("fundamental.total_assets")), "ratio"
    if observer_id == "fundamental.accruals":
        income = group.get("fundamental.net_income_ttm")
        cash_flow = group.get("fundamental.operating_cash_flow_ttm")
        assets = group.get("fundamental.total_assets")
        if income is None or cash_flow is None:
            return pd.Series(index=group.index, dtype=float), "ratio"
        return _ratio(income.sub(cash_flow), assets), "ratio"
    if observer_id == "fundamental.asset_growth":
        assets = group.get("fundamental.total_assets")
        return (assets.pct_change(fill_method=None) if assets is not None else pd.Series(index=group.index, dtype=float)), "growth_rate"
    raise KeyError(observer_id)


def _requirements(observer_id: str) -> dict[str, int]:
    mapping = {
        "fundamental.book_to_market": {"fundamental.book_equity": 1, "fundamental.market_cap": 1},
        "fundamental.earnings_yield": {"fundamental.net_income_ttm": 1, "fundamental.market_cap": 1},
        "fundamental.gross_profitability": {"fundamental.gross_profit_ttm": 1, "fundamental.total_assets": 1},
        "fundamental.operating_profitability": {"fundamental.operating_income_ttm": 1, "fundamental.book_equity": 1},
        "fundamental.leverage": {"fundamental.total_debt": 1, "fundamental.total_assets": 1},
        "fundamental.accruals": {
            "fundamental.net_income_ttm": 1,
            "fundamental.operating_cash_flow_ttm": 1,
            "fundamental.total_assets": 1,
        },
        "fundamental.asset_growth": {"fundamental.total_assets": 2},
    }
    return mapping[observer_id]


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    frame = build_numeric_wide(observations, variable_prefixes=("fundamental.",))
    provenance_index = ProvenanceIndex(observations)
    output: list[AtomicFeatureRecord] = []
    for entity_id, group in entity_groups(frame.values):
        for spec in specs:
            series, unit = _series(group, spec.observer_id)
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
                    attributes={"point_in_time_fundamentals": True},
                )
            )
    return output

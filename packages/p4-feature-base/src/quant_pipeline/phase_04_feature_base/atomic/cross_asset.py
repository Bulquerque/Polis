from __future__ import annotations

import pandas as pd

from ..feature_records import one_record, records_from_series
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec
from ..observation_frame import build_numeric_wide
from ..provenance import ProvenanceIndex

MODULE_ID = "P4.S4.M04"
SUPPORTED_OBSERVERS = {
    "cross_asset.relative_return",
    "cross_asset.beta",
    "cross_asset.correlation",
    "cross_asset.residual_return",
    "cross_asset.breadth_positive",
    "cross_asset.dispersion",
}


def _market_returns(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["market.close"].unstack("entity_id").sort_index()
    return close.pct_change(fill_method=None)


def _rolling_beta(asset: pd.Series, benchmark: pd.Series, window: int) -> pd.Series:
    covariance = asset.rolling(window, min_periods=window).cov(benchmark)
    variance = benchmark.rolling(window, min_periods=window).var(ddof=1)
    return covariance.div(variance.where(variance > 0)).shift(1)


def _window(spec: ObserverSpec) -> int:
    value = int(spec.parameters.get("window", 63))
    if value < 2:
        raise ValueError("window must be >= 2")
    return value


def _cross_sectional_records(
    *,
    returns: pd.DataFrame,
    assets: list[str],
    benchmark_id: str,
    spec: ObserverSpec,
    provenance_index: ProvenanceIndex,
) -> list[AtomicFeatureRecord]:
    series = (
        returns[assets].gt(0).mean(axis=1)
        if spec.observer_id.endswith("breadth_positive")
        else returns[assets].std(axis=1, ddof=1)
    )
    unit = "ratio" if spec.observer_id.endswith("breadth_positive") else "return_dispersion"
    output: list[AtomicFeatureRecord] = []
    for decision_time, raw_value in series.items():
        provenance = provenance_index.collect_many(
            decision_time=decision_time,
            requirements=[(entity_id, "market.close", 2) for entity_id in [benchmark_id, *assets]],
        )
        if provenance is None:
            continue
        value = None if pd.isna(raw_value) else float(raw_value)
        for entity_id in assets:
            output.append(
                one_record(
                    decision_time=decision_time,
                    entity_id=entity_id,
                    spec=spec,
                    value=value,
                    unit=unit,
                    available_at=provenance.available_at,
                    lineage_ids=provenance.lineage_ids,
                    modalities=provenance.modalities,
                    quality_state=provenance.quality_state,
                    attributes={"benchmark_entity_id": benchmark_id, "universe_size": len(assets)},
                )
            )
    return output


def _asset_series(
    asset: pd.Series,
    benchmark: pd.Series,
    spec: ObserverSpec,
    window: int,
) -> tuple[pd.Series, str, int]:
    beta = _rolling_beta(asset, benchmark, window)
    if spec.observer_id == "cross_asset.relative_return":
        return asset.sub(benchmark), "return", 2
    if spec.observer_id == "cross_asset.beta":
        return beta, "beta", window + 2
    if spec.observer_id == "cross_asset.correlation":
        return asset.rolling(window, min_periods=window).corr(benchmark).shift(1), "correlation", window + 2
    if spec.observer_id == "cross_asset.residual_return":
        return asset.sub(beta.mul(benchmark)), "return", window + 2
    raise KeyError(spec.observer_id)


def _asset_records(
    *,
    entity_id: str,
    benchmark_id: str,
    asset: pd.Series,
    benchmark: pd.Series,
    spec: ObserverSpec,
    window: int,
    provenance_index: ProvenanceIndex,
) -> list[AtomicFeatureRecord]:
    series, unit, count = _asset_series(asset, benchmark, spec, window)
    provenance = {
        decision_time: provenance_index.collect_many(
            decision_time=decision_time,
            requirements=[
                (entity_id, "market.close", count),
                (benchmark_id, "market.close", count),
            ],
        )
        for decision_time in series.index
    }
    return records_from_series(
        entity_id=entity_id,
        series=series,
        spec=spec,
        unit=unit,
        provenance_by_time=provenance,
        attributes={"benchmark_entity_id": benchmark_id, "window": window},
    )


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    source = build_numeric_wide(observations, variable_prefixes=("market.", "benchmark."))
    if source.values.empty or "market.close" not in source.values:
        return []
    provenance_index = ProvenanceIndex(observations)
    returns = _market_returns(source.values)
    output: list[AtomicFeatureRecord] = []
    for spec in specs:
        benchmark_id = str(spec.parameters.get("benchmark_entity_id", "BENCHMARK"))
        if benchmark_id not in returns.columns:
            continue
        benchmark = returns[benchmark_id]
        assets = [name for name in returns.columns if name != benchmark_id]
        if spec.observer_id in {"cross_asset.breadth_positive", "cross_asset.dispersion"}:
            output.extend(
                _cross_sectional_records(
                    returns=returns,
                    assets=assets,
                    benchmark_id=benchmark_id,
                    spec=spec,
                    provenance_index=provenance_index,
                )
            )
            continue
        window = _window(spec)
        for entity_id in assets:
            output.extend(
                _asset_records(
                    entity_id=entity_id,
                    benchmark_id=benchmark_id,
                    asset=returns[entity_id],
                    benchmark=benchmark,
                    spec=spec,
                    window=window,
                    provenance_index=provenance_index,
                )
            )
    return output

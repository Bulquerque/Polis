from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import JsonValue

from .normalization import (
    available_at,
    infer_frequency,
    numeric_value,
    observation_date,
    optional_bool,
    published_at,
    revision_id,
    vintage_date,
)
from .request_contracts import GetObservationsRequest, GetReleaseSnapshotRequest
from .result_contracts import MacroObservation, MacroSeriesDefinition
from .transformations import required_lag
from .types import MacroMode, Transformation, VintagePolicy


def request_issue(
    request: GetObservationsRequest,
    definition: MacroSeriesDefinition | None,
) -> str | None:
    if definition is None:
        return "P3_RT_DATA_SERIES_UNKNOWN"
    if request.transformation not in definition.allowed_transformations:
        return "P3_RT_DATA_TRANSFORMATION_NOT_AUTHORIZED"
    if request.research_mode is MacroMode.VINTAGE_ANALYSIS and not definition.vintage_support:
        return "P3_RT_PIT_VINTAGE_UNAVAILABLE"
    return None


def release_filter(
    rows: tuple[Mapping[str, object], ...],
    request: GetReleaseSnapshotRequest,
) -> tuple[Mapping[str, object], ...]:
    filtered = rows
    if request.release_id:
        filtered = tuple(
            row
            for row in filtered
            if str(row.get("release_id") or "") == request.release_id
        )
    if request.vintage_date:
        filtered = tuple(
            row for row in filtered if vintage_date(row) == request.vintage_date
        )
    return filtered


def select_vintage(
    rows: tuple[Mapping[str, object], ...],
    policy: VintagePolicy,
) -> tuple[Mapping[str, object], ...]:
    grouped: dict[date, list[Mapping[str, object]]] = {}
    for row in rows:
        grouped.setdefault(observation_date(row), []).append(row)
    selected = []
    for candidates in grouped.values():
        candidates.sort(key=lambda row: (available_at(row), revision_id(row) or ""))
        selected.append(
            candidates[0]
            if policy is VintagePolicy.ORIGINAL_RELEASE
            else candidates[-1]
        )
    return tuple(sorted(selected, key=observation_date))


def to_observation(
    row: Mapping[str, object],
    definition: MacroSeriesDefinition,
) -> MacroObservation:
    raw = numeric_value(row)
    return MacroObservation(
        series_id=definition.series_id,
        observation_date=observation_date(row),
        raw_value=raw,
        value=raw,
        transformation=Transformation.LEVEL,
        unit=str(row.get("unit") or definition.unit or "") or None,
        frequency=infer_frequency(row.get("frequency") or definition.frequency.value),
        available_at=available_at(row),
        published_at=published_at(row),
        vintage_date=vintage_date(row),
        revision_id=revision_id(row),
        release_id=str(row.get("release_id") or definition.release_id or "") or None,
        is_original_release=optional_bool(row.get("is_original_release")),
        source_id=str(row.get("source_id") or definition.source_id),
        lineage_id=str(row.get("lineage_id") or "unknown"),
        quality_flag=str(
            row.get("quality_flag")
            or row.get("source_quality_status")
            or "PASS"
        ),
    )


def source_rows_for_transformation(
    selected: tuple[Mapping[str, object], ...],
    returned: tuple[MacroObservation, ...],
    definition: MacroSeriesDefinition,
    transformation: Transformation,
) -> tuple[Mapping[str, object], ...]:
    returned_dates = {item.observation_date for item in returned}
    source_rows = tuple(
        row for row in selected if observation_date(row) in returned_dates
    )
    if transformation is Transformation.LEVEL or not returned:
        return source_rows
    first_returned = returned[0].observation_date
    prior_rows = tuple(
        row for row in selected if observation_date(row) < first_returned
    )
    lag = required_lag(definition.frequency, transformation)
    return prior_rows[-lag:] + source_rows


def history_warnings(
    selected: tuple[Mapping[str, object], ...],
    records: tuple[dict[str, JsonValue], ...],
    transformation: Transformation,
) -> tuple[str, ...]:
    if selected and not records and transformation is not Transformation.LEVEL:
        return ("P3_RT_DATA_INSUFFICIENT_HISTORY_FOR_TRANSFORMATION",)
    return ()


def date_in_range(
    value: date,
    start: date | None,
    end: date | None,
) -> bool:
    return (start is None or value >= start) and (end is None or value <= end)

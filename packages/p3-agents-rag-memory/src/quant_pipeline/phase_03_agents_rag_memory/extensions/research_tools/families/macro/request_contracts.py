from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from ._compat import MacroToolModel
from .types import (
    AlignmentPolicy,
    ComparisonKind,
    MacroMode,
    NonEmptyStr,
    Transformation,
    VintagePolicy,
    aware_utc,
)


class MacroToolCallContext(MacroToolModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    request_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    decision_time: datetime
    deterministic_seed: int = Field(ge=0)

    _decision = field_validator("decision_time")(aware_utc)


class SearchSeriesRequest(MacroToolModel):
    query: str = ""
    regions: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    families: tuple[str, ...] = ()
    frequencies: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    research_mode: MacroMode = MacroMode.LOOKUP
    max_results: int = Field(default=20, ge=1, le=200)


class GetObservationsRequest(MacroToolModel):
    series_id: NonEmptyStr
    start_date: date | None = None
    end_date: date | None = None
    transformation: Transformation = Transformation.LEVEL
    vintage_policy: VintagePolicy = VintagePolicy.KNOWN_AT_DECISION_TIME
    research_mode: MacroMode = MacroMode.LOOKUP
    max_records: int = Field(default=500, ge=1, le=10000)

    @model_validator(mode="after")
    def date_range(self) -> "GetObservationsRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class GetReleaseSnapshotRequest(MacroToolModel):
    series_id: NonEmptyStr
    release_id: str | None = None
    vintage_date: date | None = None
    vintage_policy: VintagePolicy = VintagePolicy.LATEST_KNOWN_AT_DECISION_TIME
    research_mode: MacroMode = MacroMode.VINTAGE_ANALYSIS
    max_records: int = Field(default=500, ge=1, le=10000)


class CompareSeriesRequest(MacroToolModel):
    series_ids: tuple[NonEmptyStr, ...]
    start_date: date | None = None
    end_date: date | None = None
    transformations: dict[str, Transformation] = Field(default_factory=dict)
    vintage_policy: VintagePolicy = VintagePolicy.KNOWN_AT_DECISION_TIME
    comparison_kind: ComparisonKind = ComparisonKind.RAW_ALIGNED
    alignment: AlignmentPolicy = AlignmentPolicy.INNER
    research_mode: MacroMode = MacroMode.CONTEXT
    max_records_per_series: int = Field(default=500, ge=2, le=10000)

    @model_validator(mode="after")
    def request_is_consistent(self) -> "CompareSeriesRequest":
        if not 2 <= len(self.series_ids) <= 10:
            raise ValueError("series_ids must contain between 2 and 10 entries")
        if len(self.series_ids) != len(set(self.series_ids)):
            raise ValueError("series_ids must be unique")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        unknown = set(self.transformations) - set(self.series_ids)
        if unknown:
            raise ValueError(f"transformations contain unknown series: {sorted(unknown)}")
        return self


class GetAssetContextRequest(MacroToolModel):
    asset_id: NonEmptyStr
    regions: tuple[str, ...] = ()
    families: tuple[str, ...] = ()
    research_mode: MacroMode = MacroMode.CONTEXT
    max_factors: int = Field(default=20, ge=1, le=100)

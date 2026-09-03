from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, JsonValue, field_validator, model_validator

from ._compat import MacroToolModel, content_hash
from .types import (
    Frequency,
    NonEmptyStr,
    OutcomeStatus,
    Probability,
    Sha256,
    Transformation,
    aware_utc,
)


class MacroSeriesDefinition(MacroToolModel):
    series_id: NonEmptyStr
    title: NonEmptyStr
    aliases: tuple[str, ...] = ()
    region: str | None = None
    country: str | None = None
    family: str | None = None
    unit: str | None = None
    frequency: Frequency = Frequency.UNKNOWN
    seasonal_adjustment: str | None = None
    source_id: NonEmptyStr
    release_id: str | None = None
    description: str | None = None
    vintage_support: bool = False
    allowed_transformations: tuple[Transformation, ...] = (Transformation.LEVEL,)
    valid_from: date | None = None
    valid_to: date | None = None


class MacroObservation(MacroToolModel):
    series_id: NonEmptyStr
    observation_date: date
    raw_value: float
    value: float
    transformation: Transformation
    unit: str | None = None
    frequency: Frequency = Frequency.UNKNOWN
    available_at: datetime
    published_at: datetime | None = None
    vintage_date: date | None = None
    revision_id: str | None = None
    release_id: str | None = None
    is_original_release: bool | None = None
    source_id: NonEmptyStr
    lineage_id: NonEmptyStr
    quality_flag: str = "PASS"

    _available = field_validator("available_at")(aware_utc)
    _published = field_validator("published_at")(lambda v: None if v is None else aware_utc(v))


class MacroComparisonRow(MacroToolModel):
    observation_date: date
    values: dict[NonEmptyStr, float | None]
    derived_values: dict[NonEmptyStr, float | None] = Field(default_factory=dict)


class AssetMacroFactor(MacroToolModel):
    asset_id: NonEmptyStr
    factor_id: NonEmptyStr
    family: NonEmptyStr
    series_ids: tuple[NonEmptyStr, ...]
    relationship_type: NonEmptyStr
    rationale: NonEmptyStr
    region: str | None = None
    source_id: NonEmptyStr
    available_at: datetime
    valid_from: date | None = None
    valid_to: date | None = None
    lineage_id: NonEmptyStr

    _available = field_validator("available_at")(aware_utc)


class MacroEvidenceRef(MacroToolModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    p2_artifact_id: NonEmptyStr
    p2_record_id: NonEmptyStr
    p2_lineage_id: str | None = None
    available_at: datetime
    content_hash: Sha256
    source_quality: Probability = 1.0

    _available = field_validator("available_at")(aware_utc)


class CoverageReport(MacroToolModel):
    score: Probability
    records_requested: int = Field(ge=0)
    records_returned: int = Field(ge=0)
    series_requested: int = Field(ge=0)
    series_returned: int = Field(ge=0)
    missing_series: tuple[str, ...] = ()
    missing_dimensions: tuple[str, ...] = ()
    truncated: bool = False


class PitQueryProof(MacroToolModel):
    policy_version: NonEmptyStr
    decision_time: datetime
    vintage_policy: NonEmptyStr
    records_scanned: int = Field(ge=0)
    records_visible: int = Field(ge=0)
    records_rejected_future: int = Field(ge=0)
    records_rejected_missing_time: int = Field(ge=0)
    records_rejected_filter: int = Field(ge=0)
    earliest_available_at: datetime | None = None
    latest_available_at: datetime | None = None
    snapshot_id: NonEmptyStr
    input_hashes: tuple[Sha256, ...]
    proof_hash: Sha256

    _decision = field_validator("decision_time")(aware_utc)
    _earliest = field_validator("earliest_available_at")(
        lambda v: None if v is None else aware_utc(v)
    )
    _latest = field_validator("latest_available_at")(
        lambda v: None if v is None else aware_utc(v)
    )

    @model_validator(mode="after")
    def no_future_evidence(self) -> "PitQueryProof":
        if self.latest_available_at and self.latest_available_at > self.decision_time:
            raise ValueError("latest_available_at exceeds decision_time")
        return self


class ExecutionReport(MacroToolModel):
    cost_units: float = Field(ge=0.0)
    internal_subquery_count: int = Field(ge=0)
    records_scanned: int = Field(ge=0)
    records_returned: int = Field(ge=0)
    deterministic: bool = True
    warnings: tuple[str, ...] = ()


class MacroToolResultEnvelope(MacroToolModel):
    envelope_version: str = "1.0.0"
    tool_id: NonEmptyStr = "macro.observation.v1"
    operation_id: NonEmptyStr
    request_id: NonEmptyStr
    outcome_status: OutcomeStatus
    requested_mode: NonEmptyStr
    executed_mode: NonEmptyStr
    downgrade_reason: str | None = None
    records: tuple[dict[str, JsonValue], ...]
    evidence_refs: tuple[MacroEvidenceRef, ...]
    coverage: CoverageReport
    provenance: dict[str, JsonValue]
    pit_proof: PitQueryProof
    execution: ExecutionReport
    result_hash: Sha256

    @model_validator(mode="after")
    def result_hash_matches(self) -> "MacroToolResultEnvelope":
        payload = self.model_dump(mode="json", exclude={"result_hash"})
        if content_hash(payload) != self.result_hash:
            raise ValueError("result_hash mismatch")
        return self

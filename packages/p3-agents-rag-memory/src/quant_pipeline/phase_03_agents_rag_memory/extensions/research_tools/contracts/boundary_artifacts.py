"""Strict serialized contracts produced by P3.S33."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from ..core.models import NonEmptyStr, ResearchToolModel, SemVer, Sha256
from .artifacts import ArtifactEnvelope


class ViewClass(StrEnum):
    DOCUMENTARY = "DOCUMENTARY"
    MARKET = "MARKET"
    MACRO = "MACRO"
    OPTIONS = "OPTIONS"
    FUNDAMENTAL_STRUCTURED = "FUNDAMENTAL_STRUCTURED"
    REFERENCE = "REFERENCE"


class ReadinessStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class QualityStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    DEGRADED = "DEGRADED"
    BLOCK = "BLOCK"
    LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"
    UNKNOWN = "UNKNOWN"


class CustodyStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    DEGRADED = "DEGRADED"
    UNAUTHORIZED_ORPHAN = "UNAUTHORIZED_ORPHAN"
    HASH_MISMATCH = "HASH_MISMATCH"
    UNREADABLE = "UNREADABLE"


class VintagePolicyName(StrEnum):
    KNOWN_AT_DECISION_TIME = "KNOWN_AT_DECISION_TIME"
    ORIGINAL_RELEASE = "ORIGINAL_RELEASE"
    LATEST_KNOWN_AT_DECISION_TIME = "LATEST_KNOWN_AT_DECISION_TIME"


class MissingTimeAction(StrEnum):
    BLOCK_RECORD = "BLOCK_RECORD"
    REQUIRE_VALIDITY_INTERVAL = "REQUIRE_VALIDITY_INTERVAL"
    ALLOW_EXPLICIT_ATEMPORAL = "ALLOW_EXPLICIT_ATEMPORAL"


class QualificationStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class EntityResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class EntityMatchMethod(StrEnum):
    EXACT_IDENTIFIER = "EXACT_IDENTIFIER"
    TICKER_VENUE = "TICKER_VENUE"
    TEMPORAL_ALIAS = "TEMPORAL_ALIAS"
    COMPANY_INSTRUMENT_MAP = "COMPANY_INSTRUMENT_MAP"
    OPTIONAL_PROBABILISTIC = "OPTIONAL_PROBABILISTIC"


class PortKind(StrEnum):
    PIT_RESEARCH_QUERY = "PIT_RESEARCH_QUERY"
    RAW_EVIDENCE_RESOLVER = "RAW_EVIDENCE_RESOLVER"
    TEMPORAL_ENTITY_RESOLVER = "TEMPORAL_ENTITY_RESOLVER"
    PROVENANCE_QUERY = "PROVENANCE_QUERY"


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class Phase2ResearchViewRecord(ResearchToolModel):
    view_id: NonEmptyStr
    view_class: ViewClass
    artifact_name: NonEmptyStr
    artifact_id: NonEmptyStr
    schema_version: NonEmptyStr
    content_hash: Sha256
    lineage_ids: tuple[NonEmptyStr, ...] = ()
    availability_field: NonEmptyStr
    entity_key_fields: tuple[NonEmptyStr, ...]
    temporal_grain: tuple[NonEmptyStr, ...]
    allowed_operation_refs: tuple[NonEmptyStr, ...]
    quality_status: QualityStatus
    readiness: ReadinessStatus
    record_count: Annotated[int, Field(ge=0)]
    source_ids: tuple[NonEmptyStr, ...] = ()
    routed_by_handoffs: tuple[NonEmptyStr, ...] = ()
    storage_metadata_hash: Sha256
    reason_codes: tuple[NonEmptyStr, ...] = ()


class Phase2ResearchViewManifest(ArtifactEnvelope):
    artifact_name: Literal["phase2_research_view_manifest"] = "phase2_research_view_manifest"
    schema_id: Literal["p3.research_tools.phase2_view_manifest.v1"] = (
        "p3.research_tools.phase2_view_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    extension_snapshot_hash: Sha256
    views: tuple[Phase2ResearchViewRecord, ...]
    view_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def count_matches(self) -> "Phase2ResearchViewManifest":
        if self.view_count != len(self.views):
            raise ValueError("view_count must match views")
        if len({item.view_id for item in self.views}) != len(self.views):
            raise ValueError("view_id must be unique")
        return self


class ViewOperationReadinessRecord(ResearchToolModel):
    view_id: NonEmptyStr
    operation_ref: NonEmptyStr
    status: ReadinessStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()


class Phase2ResearchViewReadinessReport(ArtifactEnvelope):
    artifact_name: Literal["phase2_research_view_readiness_report"] = (
        "phase2_research_view_readiness_report"
    )
    schema_id: Literal["p3.research_tools.phase2_view_readiness.v1"] = (
        "p3.research_tools.phase2_view_readiness.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    quality_status: QualityStatus
    records: tuple[ViewOperationReadinessRecord, ...]
    ready_count: Annotated[int, Field(ge=0)]
    degraded_count: Annotated[int, Field(ge=0)]
    blocked_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def counts_match(self) -> "Phase2ResearchViewReadinessReport":
        counts = {
            ReadinessStatus.READY: self.ready_count,
            ReadinessStatus.DEGRADED: self.degraded_count,
            ReadinessStatus.BLOCKED_UPSTREAM: self.blocked_count,
        }
        for status, expected in counts.items():
            if sum(item.status == status for item in self.records) != expected:
                raise ValueError(f"{status.value} count does not match records")
        return self


class RawEvidenceReference(ResearchToolModel):
    raw_artifact_id: NonEmptyStr
    source_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    file_hash: Sha256
    file_size_bytes: Annotated[int, Field(ge=0)]
    media_type: NonEmptyStr
    readability_status: NonEmptyStr
    schema_fingerprint: Sha256 | None = None
    storage_ref_token: Sha256
    captured_at: datetime | None = None
    declared_available_at: datetime | None = None
    linked_p2_artifact_ids: tuple[NonEmptyStr, ...] = ()
    linked_p2_lineage_ids: tuple[NonEmptyStr, ...] = ()
    custody_status: CustodyStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @field_validator("captured_at", "declared_available_at")
    @classmethod
    def aware_datetime(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name)


class Phase1RawEvidenceReferenceIndex(ArtifactEnvelope):
    artifact_name: Literal["phase1_raw_evidence_reference_index"] = (
        "phase1_raw_evidence_reference_index"
    )
    schema_id: Literal["p3.research_tools.phase1_raw_evidence_index.v1"] = (
        "p3.research_tools.phase1_raw_evidence_index.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[RawEvidenceReference, ...]
    record_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def unique_and_counted(self) -> "Phase1RawEvidenceReferenceIndex":
        if self.record_count != len(self.records):
            raise ValueError("record_count must match records")
        ids = [item.raw_artifact_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("raw_artifact_id must be unique")
        return self


class CustodyQualificationRecord(ResearchToolModel):
    raw_artifact_id: NonEmptyStr
    status: CustodyStatus
    checks: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()


class Phase1CustodyQualificationReport(ArtifactEnvelope):
    artifact_name: Literal["phase1_custody_qualification_report"] = (
        "phase1_custody_qualification_report"
    )
    schema_id: Literal["p3.research_tools.phase1_custody_qualification.v1"] = (
        "p3.research_tools.phase1_custody_qualification.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[CustodyQualificationRecord, ...]
    authorized_count: Annotated[int, Field(ge=0)]
    blocked_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def counts_match(self) -> "Phase1CustodyQualificationReport":
        if sum(item.status == CustodyStatus.AUTHORIZED for item in self.records) != self.authorized_count:
            raise ValueError("authorized_count does not match records")
        if sum(item.status != CustodyStatus.AUTHORIZED for item in self.records) != self.blocked_count:
            raise ValueError("blocked_count does not match records")
        return self


class PitVisibilityPolicy(ArtifactEnvelope):
    artifact_name: Literal["pit_visibility_policy"] = "pit_visibility_policy"
    schema_id: Literal["p3.research_tools.pit_visibility_policy.v1"] = (
        "p3.research_tools.pit_visibility_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_time: datetime
    execution_mode: NonEmptyStr
    canonical_timezone: NonEmptyStr
    availability_field: Literal["available_at"] = "available_at"
    require_request_as_of_equals_decision_time: Literal[True] = True
    observational_missing_time_action: MissingTimeAction
    temporal_reference_missing_time_action: MissingTimeAction
    atemporal_allowlist: tuple[NonEmptyStr, ...]
    forbidden_vintage_policies: tuple[NonEmptyStr, ...]
    extension_snapshot_hash: Sha256
    phase3_run_snapshot_hash: Sha256

    @field_validator("decision_time")
    @classmethod
    def decision_time_aware(cls, value: datetime) -> datetime:
        result = _aware(value, "decision_time")
        assert result is not None
        return result


class VintagePolicySpec(ResearchToolModel):
    policy_name: VintagePolicyName
    description: NonEmptyStr
    allowed_execution_modes: tuple[NonEmptyStr, ...]
    selection_rule: NonEmptyStr
    permits_revision_after_decision_time: Literal[False] = False


class VintagePolicyRegistry(ArtifactEnvelope):
    artifact_name: Literal["vintage_policy_registry"] = "vintage_policy_registry"
    schema_id: Literal["p3.research_tools.vintage_policy_registry.v1"] = (
        "p3.research_tools.vintage_policy_registry.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    default_policy: VintagePolicyName
    policies: tuple[VintagePolicySpec, ...]

    @model_validator(mode="after")
    def unique_and_default_present(self) -> "VintagePolicyRegistry":
        names = [item.policy_name for item in self.policies]
        if len(names) != len(set(names)):
            raise ValueError("vintage policy names must be unique")
        if self.default_policy not in names:
            raise ValueError("default_policy must be registered")
        return self


class QualificationCheck(ResearchToolModel):
    check_id: NonEmptyStr
    status: QualificationStatus
    summary: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()
    details: dict[str, JsonValue] = Field(default_factory=dict)


class PitBoundaryQualificationReport(ArtifactEnvelope):
    artifact_name: Literal["pit_boundary_qualification_report"] = (
        "pit_boundary_qualification_report"
    )
    schema_id: Literal["p3.research_tools.pit_boundary_qualification.v1"] = (
        "p3.research_tools.pit_boundary_qualification.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_time: datetime
    checks: tuple[QualificationCheck, ...]
    overall_status: QualificationStatus

    @field_validator("decision_time")
    @classmethod
    def decision_time_aware(cls, value: datetime) -> datetime:
        result = _aware(value, "decision_time")
        assert result is not None
        return result


class PitQueryProof(ResearchToolModel):
    policy_version: SemVer
    decision_time: datetime
    request_as_of: datetime
    vintage_policy: VintagePolicyName
    records_scanned: Annotated[int, Field(ge=0)]
    records_visible: Annotated[int, Field(ge=0)]
    records_rejected_future: Annotated[int, Field(ge=0)]
    records_rejected_missing_time: Annotated[int, Field(ge=0)]
    earliest_available_at: datetime | None = None
    latest_available_at: datetime | None = None
    p1_snapshot_id: NonEmptyStr
    p2_snapshot_id: NonEmptyStr
    input_hashes: tuple[Sha256, ...]
    proof_hash: Sha256

    @field_validator(
        "decision_time", "request_as_of", "earliest_available_at", "latest_available_at"
    )
    @classmethod
    def aware_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def counts_and_cutoff_match(self) -> "PitQueryProof":
        rejected = self.records_rejected_future + self.records_rejected_missing_time
        if self.records_visible + rejected != self.records_scanned:
            raise ValueError("visible and rejected counts must match records_scanned")
        if self.latest_available_at and self.latest_available_at > self.decision_time:
            raise ValueError("latest_available_at cannot exceed decision_time")
        if self.request_as_of != self.decision_time:
            raise ValueError("request_as_of must equal decision_time")
        return self


class EntityResolutionCandidate(ResearchToolModel):
    resolution_key: NonEmptyStr
    entity_id: NonEmptyStr
    instrument_id: NonEmptyStr | None = None
    method: EntityMatchMethod
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class EntityResolutionResult(ResearchToolModel):
    query: NonEmptyStr
    decision_time: datetime
    status: EntityResolutionStatus
    candidates: tuple[EntityResolutionCandidate, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @field_validator("decision_time")
    @classmethod
    def decision_time_aware(cls, value: datetime) -> datetime:
        result = _aware(value, "decision_time")
        assert result is not None
        return result


class TemporalEntityRecord(ResearchToolModel):
    resolution_key: NonEmptyStr
    entity_id: NonEmptyStr
    instrument_id: NonEmptyStr | None = None
    instrument_type: NonEmptyStr
    venue: NonEmptyStr | None = None
    ticker: NonEmptyStr | None = None
    aliases: tuple[NonEmptyStr, ...] = ()
    identifiers: dict[str, NonEmptyStr] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    underlying_instrument_id: NonEmptyStr | None = None
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_lineage_ids: tuple[NonEmptyStr, ...] = ()
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    match_methods: tuple[EntityMatchMethod, ...]

    @field_validator("valid_from", "valid_to")
    @classmethod
    def aware_validity(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def interval_valid(self) -> "TemporalEntityRecord":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        return self


class TemporalEntityResolutionIndex(ArtifactEnvelope):
    artifact_name: Literal["temporal_entity_resolution_index"] = (
        "temporal_entity_resolution_index"
    )
    schema_id: Literal["p3.research_tools.temporal_entity_resolution_index.v1"] = (
        "p3.research_tools.temporal_entity_resolution_index.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[TemporalEntityRecord, ...]
    record_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def unique_and_counted(self) -> "TemporalEntityResolutionIndex":
        if self.record_count != len(self.records):
            raise ValueError("record_count must match records")
        keys = [item.resolution_key for item in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("resolution_key must be unique")
        return self


class EntityResolutionPolicy(ArtifactEnvelope):
    artifact_name: Literal["entity_resolution_policy"] = "entity_resolution_policy"
    schema_id: Literal["p3.research_tools.entity_resolution_policy.v1"] = (
        "p3.research_tools.entity_resolution_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    resolution_order: tuple[EntityMatchMethod, ...]
    fuzzy_matching_enabled: bool
    minimum_probabilistic_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    ambiguity_policy: Literal["RETURN_CANDIDATES_NO_SILENT_CHOICE"] = (
        "RETURN_CANDIDATES_NO_SILENT_CHOICE"
    )
    canonical_timezone: NonEmptyStr
    identifier_namespaces: tuple[NonEmptyStr, ...]


class EntityResolutionQualificationReport(ArtifactEnvelope):
    artifact_name: Literal["entity_resolution_qualification_report"] = (
        "entity_resolution_qualification_report"
    )
    schema_id: Literal["p3.research_tools.entity_resolution_qualification.v1"] = (
        "p3.research_tools.entity_resolution_qualification.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    checks: tuple[QualificationCheck, ...]
    resolved_count: Annotated[int, Field(ge=0)]
    ambiguous_key_count: Annotated[int, Field(ge=0)]
    overall_status: QualificationStatus


class BoundaryArtifactRef(ResearchToolModel):
    artifact_name: NonEmptyStr
    artifact_id: NonEmptyStr
    schema_id: NonEmptyStr
    content_hash: Sha256
    status: NonEmptyStr


class BoundaryPortSpec(ResearchToolModel):
    port_id: NonEmptyStr
    port_kind: PortKind
    purpose: NonEmptyStr
    methods: tuple[NonEmptyStr, ...]
    required_artifact_names: tuple[NonEmptyStr, ...]
    read_only: Literal[True] = True
    network_required: Literal[False] = False


class ResearchDataBoundaryBundle(ArtifactEnvelope):
    artifact_name: Literal["research_data_boundary_bundle"] = "research_data_boundary_bundle"
    schema_id: Literal["p3.research_tools.data_boundary_bundle.v1"] = (
        "p3.research_tools.data_boundary_bundle.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    extension_snapshot_hash: Sha256
    decision_time: datetime
    artifact_refs: tuple[BoundaryArtifactRef, ...]
    ports: tuple[BoundaryPortSpec, ...]
    allowed_view_ids: tuple[NonEmptyStr, ...]
    blocked_operation_refs: tuple[NonEmptyStr, ...]

    @field_validator("decision_time")
    @classmethod
    def decision_time_aware(cls, value: datetime) -> datetime:
        result = _aware(value, "decision_time")
        assert result is not None
        return result


class ResearchBoundaryPreflightReport(ArtifactEnvelope):
    artifact_name: Literal["research_boundary_preflight_report"] = (
        "research_boundary_preflight_report"
    )
    schema_id: Literal["p3.research_tools.boundary_preflight.v1"] = (
        "p3.research_tools.boundary_preflight.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    checks: tuple[QualificationCheck, ...]
    overall_status: QualificationStatus
    bundle_hash: Sha256

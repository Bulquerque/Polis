from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        populate_by_name=True,
    )


class ExecutionStatus(StrEnum):
    READY = "READY"
    READY_EMPTY = "READY_EMPTY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class RecordType(StrEnum):
    EVENT = "EVENT"
    DOCUMENT = "DOCUMENT"
    CONTEXT_SOURCE = "CONTEXT_SOURCE"


class StimulusType(StrEnum):
    NEWS_EVENT = "NEWS_EVENT"
    FILING_EVENT = "FILING_EVENT"
    MACRO_RELEASE = "MACRO_RELEASE"
    MARKET_EVENT = "MARKET_EVENT"
    RESEARCH_EVENT = "RESEARCH_EVENT"
    POLICY_EVENT = "POLICY_EVENT"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    OTHER = "OTHER"


class StimulusOrigin(StrEnum):
    EXTERNAL_PIT_CONTEXT = "EXTERNAL_PIT_CONTEXT"


class ResolutionStatus(StrEnum):
    RESOLVED_ONE = "RESOLVED_ONE"
    RESOLVED_MANY = "RESOLVED_MANY"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    INVALID = "INVALID"


class PropositionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    INVALID = "INVALID"


class IdentifierHint(ContractModel):
    id_type: StrictStr = Field(min_length=1, max_length=64)
    id_value: StrictStr = Field(min_length=1, max_length=256)
    mic: StrictStr | None = Field(default=None, min_length=4, max_length=4)
    exchange_code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    currency: StrictStr | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("id_type")
    @classmethod
    def normalize_id_type(cls, value: str) -> str:
        return value.upper()

    @field_validator("mic", "currency")
    @classmethod
    def normalize_upper_optional(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class SalienceFeatures(ContractModel):
    source_quality: StrictFloat = Field(ge=0.0, le=1.0)
    novelty: StrictFloat = Field(ge=0.0, le=1.0)
    subject_relevance: StrictFloat = Field(ge=0.0, le=1.0)
    event_severity: StrictFloat = Field(ge=0.0, le=1.0)
    information_specificity: StrictFloat = Field(ge=0.0, le=1.0)


class PitContextRecord(ContractModel):
    record_id: StrictStr = Field(pattern=ID_PATTERN)
    record_type: RecordType
    source_event_id: StrictStr = Field(pattern=ID_PATTERN)
    subject: StrictStr = Field(min_length=1, max_length=1024)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    event_time: datetime
    available_at: datetime
    evidence_refs: tuple[StrictStr, ...] = Field(min_length=1)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    stimulus_type: StimulusType | None = None
    entity_ids: tuple[StrictStr, ...] = ()
    identifier_hints: tuple[IdentifierHint, ...] = ()
    proposition_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    horizon: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    salience_features: SalienceFeatures | None = None

    _event_time_utc = field_validator("event_time")(_aware_utc)
    _available_at_utc = field_validator("available_at")(_aware_utc)

    @field_validator("evidence_refs", "entity_ids")
    @classmethod
    def unique_nonblank_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("blank identifiers are not allowed")
        if len(values) != len(set(values)):
            raise ValueError("duplicate identifiers are not allowed")
        return values


class PitValidatedContext(ContractModel):
    schema_version: StrictStr
    records: tuple[PitContextRecord, ...]
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)


class GraphEntityNode(ContractModel):
    entity_id: StrictStr = Field(pattern=ID_PATTERN)
    entity_type: StrictStr = Field(min_length=1, max_length=64)
    canonical_name: StrictStr = Field(min_length=1, max_length=512)
    aliases: tuple[StrictStr, ...] = ()
    available_at: datetime
    evidence_refs: tuple[StrictStr, ...] = Field(min_length=1)
    identifier_hints: tuple[IdentifierHint, ...] = ()

    _available_at_utc = field_validator("available_at")(_aware_utc)


class GraphRagArtifact(ContractModel):
    schema_version: StrictStr
    artifact_id: StrictStr = Field(pattern=ID_PATTERN)
    created_at: datetime
    as_of: datetime
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    nodes: tuple[GraphEntityNode, ...] = ()

    _created_at_utc = field_validator("created_at")(_aware_utc)
    _as_of_utc = field_validator("as_of")(_aware_utc)


class Phase3RunSnapshot(ContractModel):
    schema_version: StrictStr
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    snapshot_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime = Field(validation_alias=AliasChoices("as_of", "as_of_time"))
    seed: StrictInt = Field(ge=0)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)

    _as_of_utc = field_validator("as_of")(_aware_utc)

    @model_validator(mode="after")
    def fill_target_cycle(self) -> Self:
        if self.target_cycle_id is None:
            object.__setattr__(self, "target_cycle_id", self.cycle_id)
        return self


class SalienceWeights(ContractModel):
    source_quality: StrictFloat = Field(ge=0.0, le=1.0)
    novelty: StrictFloat = Field(ge=0.0, le=1.0)
    subject_relevance: StrictFloat = Field(ge=0.0, le=1.0)
    event_severity: StrictFloat = Field(ge=0.0, le=1.0)
    information_specificity: StrictFloat = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> Self:
        total = sum(
            (
                self.source_quality,
                self.novelty,
                self.subject_relevance,
                self.event_severity,
                self.information_specificity,
            )
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"salience weights must sum to 1.0, got {total}")
        return self


class StimulusBusConfig(ContractModel):
    config_version: StrictStr
    bus_id: StrictStr = Field(pattern=ID_PATTERN)
    same_cycle_policy: Literal["EXTERNAL_ONLY_CURRENT_ENDOGENOUS_NEXT"]
    stimulus_type_by_record_type: dict[RecordType, StimulusType]
    salience_formula_id: StrictStr = Field(pattern=ID_PATTERN)
    salience_weights: SalienceWeights
    salience_defaults_by_record_type: dict[RecordType, SalienceFeatures]
    allow_exact_subject_graph_match: StrictBool = False
    max_subject_length: StrictInt = Field(default=1024, ge=1, le=4096)

    @model_validator(mode="after")
    def all_record_types_configured(self) -> Self:
        missing_type = set(RecordType) - set(self.stimulus_type_by_record_type)
        missing_defaults = set(RecordType) - set(self.salience_defaults_by_record_type)
        if missing_type or missing_defaults:
            raise ValueError(
                "all record types require stimulus mappings and defaults; "
                f"missing_type={sorted(item.value for item in missing_type)}, "
                f"missing_defaults={sorted(item.value for item in missing_defaults)}"
            )
        return self


class UnderlyingCandidate(ContractModel):
    underlying_id: StrictStr = Field(pattern=ID_PATTERN)
    weight: StrictFloat = Field(gt=0.0, le=1.0)
    mic: StrictStr | None = Field(default=None, min_length=4, max_length=4)
    security_type: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    identifiers: tuple[IdentifierHint, ...] = ()

    @field_validator("underlying_id")
    @classmethod
    def reject_document_identifiers(cls, value: str) -> str:
        lowered = value.casefold()
        if lowered.startswith(("chunk:", "document:", "doc:")):
            raise ValueError("chunk/document IDs cannot be used as underlyings")
        return value


class EntityMapping(ContractModel):
    mapping_id: StrictStr = Field(pattern=ID_PATTERN)
    entity_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    aliases: tuple[StrictStr, ...] = ()
    identifiers: tuple[IdentifierHint, ...] = ()
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    resolutions: tuple[UnderlyingCandidate, ...] = Field(min_length=1)

    @field_validator("valid_from", "valid_to")
    @classmethod
    def optional_aware_utc(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        if self.entity_id is None and not self.aliases and not self.identifiers:
            raise ValueError("mapping needs entity_id, alias, or identifier")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        total = sum(item.weight for item in self.resolutions)
        if len(self.resolutions) > 1 and abs(total - 1.0) > 1e-9:
            raise ValueError("one-to-many resolution weights must sum to 1.0")
        if len(self.resolutions) == 1 and abs(total - 1.0) > 1e-9:
            raise ValueError("single resolution weight must be 1.0")
        return self


class ExternalResolutionPolicy(ContractModel):
    enabled: StrictBool = False
    provider_id: Literal["OPENFIGI_V3"] = "OPENFIGI_V3"
    only_identifier_hints: StrictBool = True
    ambiguous_result_policy: Literal["PRESERVE_AMBIGUOUS"] = "PRESERVE_AMBIGUOUS"


class EntityUnderlyingMapConfig(ContractModel):
    version: StrictStr
    unresolved_policy: Literal["PRESERVE_UNRESOLVED_NEVER_USE_CHUNK_ID"]
    canonical_id_field: Literal["underlying_id"]
    allow_exact_subject_alias_match: StrictBool = False
    one_to_many_policy: Literal["PRESERVE_WEIGHTED"] = "PRESERVE_WEIGHTED"
    external_resolution: ExternalResolutionPolicy = ExternalResolutionPolicy()
    mappings: tuple[EntityMapping, ...] = ()

    @model_validator(mode="after")
    def mapping_ids_unique(self) -> Self:
        mapping_ids = [mapping.mapping_id for mapping in self.mappings]
        if len(mapping_ids) != len(set(mapping_ids)):
            raise ValueError("mapping_id must be unique")
        return self


class PropositionDefinition(ContractModel):
    proposition_id: StrictStr = Field(pattern=ID_PATTERN)
    description: StrictStr = Field(min_length=1, max_length=1024)
    allowed_horizons: tuple[StrictStr, ...] = Field(min_length=1)
    default_horizon: StrictStr | None = None

    @model_validator(mode="after")
    def default_horizon_is_allowed(self) -> Self:
        if self.default_horizon is not None and self.default_horizon not in self.allowed_horizons:
            raise ValueError("default_horizon must be listed in allowed_horizons")
        return self


class PropositionRegistry(ContractModel):
    version: StrictStr
    propositions: tuple[PropositionDefinition, ...]

    @model_validator(mode="after")
    def proposition_ids_unique(self) -> Self:
        ids = [item.proposition_id for item in self.propositions]
        if len(ids) != len(set(ids)):
            raise ValueError("proposition_id must be unique")
        return self


class ModuleMetrics(ContractModel):
    input_record_count: StrictInt = Field(ge=0)
    output_record_count: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(ge=0)
    defaulted_component_count: StrictInt = Field(default=0, ge=0)
    unresolved_count: StrictInt = Field(default=0, ge=0)
    ambiguous_count: StrictInt = Field(default=0, ge=0)


class StimulusRecord(ContractModel):
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    origin_type: Literal[StimulusOrigin.EXTERNAL_PIT_CONTEXT]
    record_id: StrictStr = Field(pattern=ID_PATTERN)
    record_type: RecordType
    source_event_id: StrictStr = Field(pattern=ID_PATTERN)
    causal_parent_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    created_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    event_time: datetime
    available_at: datetime
    subject: StrictStr = Field(min_length=1, max_length=4096)
    stimulus_type: StimulusType
    intensity: StrictFloat = Field(ge=0.0, le=1.0)
    salience: StrictFloat = Field(ge=0.0, le=1.0)
    salience_features: SalienceFeatures
    salience_formula_id: StrictStr = Field(pattern=ID_PATTERN)
    defaulted_components: tuple[StrictStr, ...] = ()
    entity_ids: tuple[StrictStr, ...] = ()
    identifier_hints: tuple[IdentifierHint, ...] = ()
    proposition_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    horizon: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    evidence_refs: tuple[StrictStr, ...] = Field(min_length=1)
    graph_evidence_refs: tuple[StrictStr, ...] = ()
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)

    _event_time_utc = field_validator("event_time")(_aware_utc)
    _available_at_utc = field_validator("available_at")(_aware_utc)


class ExternalStimulusStream(ContractModel):
    schema_version: Literal["external_stimulus_stream.v2"]
    contract_version: Literal["p3.s17.v1"]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    items: tuple[StimulusRecord, ...]
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: ModuleMetrics

    _as_of_utc = field_validator("as_of")(_aware_utc)


class ResolvedStimulusRecord(StimulusRecord):
    resolution_status: ResolutionStatus
    mapping_version: StrictStr
    resolution_method: StrictStr = Field(min_length=1, max_length=128)
    underlying_candidates: tuple[UnderlyingCandidate, ...] = ()
    selected_underlying_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    proposition_status: PropositionStatus
    warnings: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def resolution_shape_matches_status(self) -> Self:
        if self.resolution_status is ResolutionStatus.RESOLVED_ONE:
            if len(self.underlying_candidates) != 1 or self.selected_underlying_id is None:
                raise ValueError("RESOLVED_ONE requires one candidate and selected_underlying_id")
        elif self.selected_underlying_id is not None:
            raise ValueError("selected_underlying_id is only valid for RESOLVED_ONE")
        return self


class ResolvedExternalStimulusStream(ContractModel):
    schema_version: Literal["resolved_external_stimulus_stream.v2"]
    contract_version: Literal["p3.s17.v1"]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    items: tuple[ResolvedStimulusRecord, ...]
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: ModuleMetrics

    _as_of_utc = field_validator("as_of")(_aware_utc)


class OpenFigiAdapterConfig(ContractModel):
    provider_id: Literal["OPENFIGI_V3"] = "OPENFIGI_V3"
    base_url: StrictStr = "https://api.openfigi.com"
    api_version: Literal["v3"] = "v3"
    api_key_env: StrictStr | None = "OPENFIGI_API_KEY"
    timeout_seconds: StrictFloat = Field(default=15.0, gt=0.0, le=120.0)
    max_retries: StrictInt = Field(default=3, ge=0, le=8)
    anonymous_batch_size: StrictInt = Field(default=5, ge=1, le=5)
    authenticated_batch_size: StrictInt = Field(default=100, ge=1, le=100)
    follow_redirects: Literal[False] = False


class OpenFigiMappingJob(ContractModel):
    id_type: StrictStr
    id_value: StrictStr
    mic_code: StrictStr | None = None
    exchange_code: StrictStr | None = None
    currency: StrictStr | None = None


class OpenFigiCandidate(ContractModel):
    figi: StrictStr = Field(pattern=ID_PATTERN)
    ticker: StrictStr | None = None
    name: StrictStr | None = None
    exchange_code: StrictStr | None = None
    composite_figi: StrictStr | None = None
    share_class_figi: StrictStr | None = None
    security_type: StrictStr | None = None
    security_type2: StrictStr | None = None
    market_sector: StrictStr | None = None


class OpenFigiJobResult(ContractModel):
    job: OpenFigiMappingJob
    candidates: tuple[OpenFigiCandidate, ...] = ()
    warning: StrictStr | None = None
    error: StrictStr | None = None

    @model_validator(mode="after")
    def result_is_unambiguous_shape(self) -> Self:
        populated = int(bool(self.candidates)) + int(self.warning is not None) + int(self.error is not None)
        if populated != 1:
            raise ValueError("OpenFIGI result must contain candidates, warning, or error")
        return self

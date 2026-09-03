from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class StrictModel(BaseModel):
    """Strict immutable contract model used at every S30 boundary."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


class QualityStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class FeatureType(StrEnum):
    FLOAT = "FLOAT"
    COUNT = "COUNT"
    RATIO = "RATIO"
    SCORE = "SCORE"


class PrivacyClass(StrEnum):
    PUBLIC_AGGREGATE = "PUBLIC_AGGREGATE"
    INTERNAL_AGGREGATE = "INTERNAL_AGGREGATE"


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class MemoryType(StrEnum):
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    AUDIT = "AUDIT"


class ConsumerBindingStatus(StrEnum):
    BOUND = "BOUND"
    CONSUMER_NOT_YET_BOUND = "CONSUMER_NOT_YET_BOUND"
    INCOMPATIBLE = "INCOMPATIBLE"


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class ExecutionContext(StrictModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    pipeline_version: str = Field(min_length=1)

    @field_validator("as_of_time", "created_at")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def created_at_not_before_as_of(self) -> "ExecutionContext":
        if self.created_at < self.as_of_time:
            raise ValueError("created_at must be greater than or equal to as_of_time")
        return self


class ArtifactBase(StrictModel):
    artifact_id: str = Field(min_length=1)
    created_at: datetime
    lineage_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime

    @field_validator("created_at", "as_of_time")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)


class ArtifactMetadata(ArtifactBase):
    schema_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...] = ()


class SocietyStateRecord(StrictModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    confidence_dispersion: Probability
    evidence_diversity: Probability
    attention_concentration: Probability
    information_asymmetry: Probability
    coverage_ratio: Probability
    source_quality_score: Probability
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...] = ()
    lineage_id: str = Field(min_length=1)

    @field_validator("as_of_time")
    @classmethod
    def aware_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of_time")

    @property
    def grain_key(self) -> tuple[str, str, str, str, str, datetime]:
        return (
            self.run_id,
            self.cycle_id,
            self.underlying_id,
            self.proposition_id,
            self.horizon,
            self.as_of_time,
        )


class ValidatedSocietyStatePanel(ArtifactBase):
    records: tuple[SocietyStateRecord, ...]


class AgentDisagreementRecord(StrictModel):
    date: date
    as_of_date: date
    available_at: datetime
    underlying: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    disagreement_score: Probability | None
    agent_agreement_score: Probability | None
    direction_disagreement_score: Probability
    confidence_disagreement_score: Probability
    evidence_disagreement_score: Probability
    polarization_score: Probability
    belief_variance_score: Probability
    effective_sample_size: NonNegativeFloat
    population_size: NonNegativeInt
    coverage_ratio: Probability
    source_quality_score: Probability
    formula_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    lineage_id: str = Field(min_length=1)

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _aware(value, "available_at")

    @property
    def grain_key(self) -> tuple[str, str, str, date]:
        return self.underlying, self.proposition_id, self.horizon, self.as_of_date


class AgentDisagreementPanel(ArtifactMetadata):
    records: tuple[AgentDisagreementRecord, ...]


class EvidenceTagRecord(StrictModel):
    date: date
    as_of_date: date
    available_at: datetime
    underlying: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    belief_update_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    evidence_tag: str = Field(min_length=1)
    evidence_relation: EvidenceRelation
    evidence_kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    document_id: str | None = None
    chunk_id: str | None = None
    graph_path_id: str | None = None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_quality_score: Probability
    claim_statement_summary: str = Field(min_length=1, max_length=500)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    lineage_id: str = Field(min_length=1)

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _aware(value, "available_at")

    @property
    def grain_key(self) -> tuple[str, str, str, date]:
        return self.underlying, self.proposition_id, self.horizon, self.as_of_date


class EvidenceTagPanel(ArtifactMetadata):
    records: tuple[EvidenceTagRecord, ...]


class MemoryRecord(StrictModel):
    memory_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    memory_type: MemoryType
    created_at: datetime
    available_at: datetime
    confidence: Probability
    importance: Probability
    retrievability: Probability
    source_quality_score: Probability
    evidence_refs: tuple[str, ...] = ()
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)

    @field_validator("created_at", "available_at")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @property
    def grain_key(self) -> tuple[str, str, str]:
        return self.underlying_id, self.proposition_id, self.horizon


class NextMemoryState(ArtifactBase):
    population_size: NonNegativeInt
    records: tuple[MemoryRecord, ...]


class PropositionDefinition(StrictModel):
    proposition_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    statement_template: str = Field(min_length=1, max_length=500)
    falsification_template: str = Field(min_length=1, max_length=500)
    required_observable: str = Field(min_length=1, max_length=200)
    allowed_horizons: tuple[str, ...] = Field(min_length=1)
    maturity_days: Annotated[int, Field(gt=0, le=3650)]
    minimum_evidence_count: NonNegativeInt = 1
    allow_context_only: bool = False

    @model_validator(mode="after")
    def templates_are_specific(self) -> "PropositionDefinition":
        required_tokens = ("{underlying}", "{horizon}")
        if not all(token in self.statement_template for token in required_tokens):
            raise ValueError("statement_template must include {underlying} and {horizon}")
        if "{observable}" not in self.falsification_template:
            raise ValueError("falsification_template must include {observable}")
        return self


class PropositionRegistryConfig(StrictModel):
    registry_id: str = Field(min_length=1)
    registry_version: str = Field(min_length=1)
    propositions: tuple[PropositionDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def proposition_ids_unique(self) -> "PropositionRegistryConfig":
        ids = [item.proposition_id for item in self.propositions]
        if len(ids) != len(set(ids)):
            raise ValueError("proposition_id values must be unique")
        return self


class BeliefCommitmentRecord(StrictModel):
    commitment_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    committed_at: datetime
    matures_at: datetime
    belief_value: Annotated[float, Field(ge=-1.0, le=1.0)]
    confidence: Probability
    evidence_refs: tuple[str, ...] = ()
    commitment_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)

    @field_validator("committed_at", "matures_at")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def maturity_after_commitment(self) -> "BeliefCommitmentRecord":
        if self.matures_at <= self.committed_at:
            raise ValueError("matures_at must be after committed_at")
        return self


class BeliefOutcomeCommitmentLog(ArtifactBase):
    records: tuple[BeliefCommitmentRecord, ...]


class Phase3RunSnapshot(StrictModel):
    snapshot_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    pipeline_version: str = Field(min_length=1)
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_registry_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)

    @field_validator("as_of_time")
    @classmethod
    def aware_as_of(cls, value: datetime) -> datetime:
        return _aware(value, "as_of_time")


class ProjectionDefinition(StrictModel):
    feature_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    feature_name: str = Field(min_length=1)
    source: Literal["society", "disagreement", "evidence", "memory"]
    source_field: str = Field(min_length=1)
    feature_type: FeatureType
    formula_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC_AGGREGATE


class FeatureProjectionConfig(StrictModel):
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    output_precision: Annotated[int, Field(ge=0, le=15)] = 12
    definitions: tuple[ProjectionDefinition, ...] = Field(min_length=1)
    min_memory_population_coverage: Probability = 0.0

    @model_validator(mode="after")
    def feature_ids_unique(self) -> "FeatureProjectionConfig":
        ids = [item.feature_id for item in self.definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("feature_id values must be unique")
        return self


class SocialFeatureRecord(StrictModel):
    date: date
    as_of_date: date
    available_at: datetime
    underlying: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    social_feature_id: str = Field(min_length=1)
    feature_name: str = Field(min_length=1)
    feature_value: float
    feature_type: FeatureType
    source_quality_score: Probability
    evidence_count: NonNegativeInt
    agent_agreement_score: Probability | None
    agent_disagreement_score: Probability | None
    reference_date: date
    formula_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    lineage_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _aware(value, "available_at")


class SocialFeaturePanel(ArtifactMetadata):
    records: tuple[SocialFeatureRecord, ...]


class ContextMemoryFeatureRecord(StrictModel):
    date: date
    as_of_date: date
    available_at: datetime
    underlying: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    context_memory_feature_id: str = Field(min_length=1)
    feature_name: str = Field(min_length=1)
    feature_value: float
    feature_type: FeatureType
    source_quality_score: Probability
    evidence_count: NonNegativeInt
    population_coverage_ratio: Probability
    uncertainty_score: Probability
    privacy_class: PrivacyClass
    formula_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    lineage_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _aware(value, "available_at")


class ContextMemoryFeaturePanel(ArtifactMetadata):
    records: tuple[ContextMemoryFeatureRecord, ...]


class HypothesisRecord(StrictModel):
    hypothesis_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    created_at: datetime
    as_of_time: datetime
    matures_at: datetime
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    hypothesis_text: str = Field(min_length=1, max_length=1000)
    supporting_evidence_refs: tuple[str, ...]
    opposing_evidence_refs: tuple[str, ...]
    context_evidence_refs: tuple[str, ...]
    evidence_count: NonNegativeInt
    source_quality_score: Probability
    falsification_criterion: str = Field(min_length=1, max_length=1000)
    required_observable: str = Field(min_length=1, max_length=200)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    lineage_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)

    @field_validator("created_at", "as_of_time", "matures_at")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def maturity_after_creation(self) -> "HypothesisRecord":
        if self.matures_at <= self.created_at:
            raise ValueError("matures_at must be after created_at")
        return self


class HypothesisRegistry(ArtifactMetadata):
    records: tuple[HypothesisRecord, ...]


class ArtifactManifestEntry(StrictModel):
    artifact_name: Literal[
        "social_feature_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "context_memory_feature_panel",
        "hypothesis_registry",
        "phase4_social_handoff_manifest",
    ]
    artifact_id: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_count: NonNegativeInt
    grain: tuple[str, ...] = Field(min_length=1)
    producer_module_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    available_at: datetime
    quality_status: QualityStatus

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _aware(value, "available_at")


class Phase4SocialHandoffManifest(ArtifactMetadata):
    expected_output_count: Literal[6] = 6
    entries: tuple[ArtifactManifestEntry, ...] = Field(min_length=5, max_length=5)
    complete: Literal[True] = True

    @model_validator(mode="after")
    def five_payload_entries_unique(self) -> "Phase4SocialHandoffManifest":
        names = [entry.artifact_name for entry in self.entries]
        expected = {
            "social_feature_panel",
            "evidence_tag_panel",
            "agent_disagreement_panel",
            "context_memory_feature_panel",
            "hypothesis_registry",
        }
        if set(names) != expected or len(names) != len(set(names)):
            raise ValueError("manifest must contain exactly the five payload artifact entries")
        return self


class VariableEvolutionInputManifest(StrictModel):
    manifest_id: str = Field(min_length=1)
    canonical_society_state_ref: str = Field(min_length=1)
    social_feature_ref: str = Field(min_length=1)
    context_memory_feature_ref: str = Field(min_length=1)
    hypothesis_registry_ref: str = Field(min_length=1)
    belief_commitment_ref: str = Field(min_length=1)
    as_of_time: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

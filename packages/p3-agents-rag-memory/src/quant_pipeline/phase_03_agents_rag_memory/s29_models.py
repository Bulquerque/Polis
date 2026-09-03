from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class StrictModel(BaseModel):
    """Strict immutable contract model used at every S29 boundary."""

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


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class EvidenceKind(StrEnum):
    RAG_CHUNK = "RAG_CHUNK"
    GRAPH_PATH = "GRAPH_PATH"
    TOOL_RESULT = "TOOL_RESULT"
    MEMORY_ITEM = "MEMORY_ITEM"
    DOCUMENT = "DOCUMENT"


def _require_aware(value: datetime, field_name: str) -> datetime:
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
        return _require_aware(value, info.field_name)

    @model_validator(mode="after")
    def creation_not_before_as_of(self) -> "ExecutionContext":
        if self.created_at < self.as_of_time:
            raise ValueError("created_at must be greater than or equal to as_of_time")
        return self


class ArtifactMetadata(StrictModel):
    artifact_id: str = Field(min_length=1)
    created_at: datetime
    lineage_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    schema_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...] = ()

    @field_validator("created_at", "as_of_time")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _require_aware(value, info.field_name)


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
        return _require_aware(value, info.field_name)


class BeliefDistributionRecord(StrictModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    negative_mass: Probability
    neutral_mass: Probability
    positive_mass: Probability
    belief_mean: Annotated[float, Field(ge=-1.0, le=1.0)]
    belief_variance: NonNegativeFloat
    normalized_entropy: Probability
    polarization: Probability
    effective_sample_size: NonNegativeFloat
    population_size: NonNegativeInt
    coverage_ratio: Probability
    source_quality_score: Probability
    formula_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

    @field_validator("as_of_time")
    @classmethod
    def aware_as_of(cls, value: datetime) -> datetime:
        return _require_aware(value, "as_of_time")

    @model_validator(mode="after")
    def masses_sum_to_one(self) -> "BeliefDistributionRecord":
        total = self.negative_mass + self.neutral_mass + self.positive_mass
        if abs(total - 1.0) > 1e-9:
            raise ValueError("direction masses must sum to 1.0")
        return self

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


class BeliefDistributionPanel(ArtifactBase):
    records: tuple[BeliefDistributionRecord, ...]


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
        return _require_aware(value, "as_of_time")

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


class DisagreementWeights(StrictModel):
    direction_entropy: Probability
    belief_variance: Probability
    polarization: Probability
    confidence_dispersion: Probability
    evidence_diversity: Probability

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "DisagreementWeights":
        total = (
            self.direction_entropy
            + self.belief_variance
            + self.polarization
            + self.confidence_dispersion
            + self.evidence_diversity
        )
        if abs(total - 1.0) > 1e-12:
            raise ValueError("disagreement weights must sum to exactly 1.0")
        return self


class DisagreementSemanticsConfig(StrictModel):
    formula_id: Literal["s29.disagreement.composite"]
    formula_version: Literal["1.0.0"]
    variance_cap: Annotated[float, Field(gt=0.0)]
    min_effective_sample_size: NonNegativeFloat
    min_coverage_ratio: Probability
    min_source_quality_score: Probability
    weights: DisagreementWeights
    blocked_quality_statuses: tuple[QualityStatus, ...] = (QualityStatus.BLOCKED,)
    output_precision: Annotated[int, Field(ge=0, le=15)] = 12


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
        return _require_aware(value, "available_at")


class AgentDisagreementPanel(ArtifactMetadata):
    records: tuple[AgentDisagreementRecord, ...]


class EvidenceReference(StrictModel):
    evidence_id: str = Field(min_length=1)
    evidence_kind: EvidenceKind
    source_id: str = Field(min_length=1)
    document_id: str | None = None
    chunk_id: str | None = None
    graph_path_id: str | None = None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_time: datetime | None = None
    available_at: datetime
    source_quality_score: Probability
    lineage_id: str = Field(min_length=1)

    @field_validator("event_time", "available_at")
    @classmethod
    def aware_datetimes(cls, value: datetime | None, info):  # type: ignore[no-untyped-def]
        if value is None:
            return value
        return _require_aware(value, info.field_name)

    @model_validator(mode="after")
    def kind_specific_fields(self) -> "EvidenceReference":
        if self.evidence_kind == EvidenceKind.RAG_CHUNK and not self.chunk_id:
            raise ValueError("RAG_CHUNK evidence requires chunk_id")
        if self.evidence_kind == EvidenceKind.GRAPH_PATH and not self.graph_path_id:
            raise ValueError("GRAPH_PATH evidence requires graph_path_id")
        return self


class RetrievalEvidenceMap(ArtifactBase):
    records: tuple[EvidenceReference, ...]


class GraphEvidenceMap(ArtifactBase):
    records: tuple[EvidenceReference, ...]


class RagIndexEntry(StrictModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    available_at: datetime
    lineage_id: str = Field(min_length=1)

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "available_at")


class RagIndexArtifact(ArtifactBase):
    records: tuple[RagIndexEntry, ...]


class BeliefUpdateRecord(StrictModel):
    belief_update_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    prior_value: Annotated[float, Field(ge=-1.0, le=1.0)]
    new_value: Annotated[float, Field(ge=-1.0, le=1.0)]
    confidence: Probability
    supporting_evidence_refs: tuple[str, ...] = ()
    opposing_evidence_refs: tuple[str, ...] = ()
    context_evidence_refs: tuple[str, ...] = ()
    lineage_id: str = Field(min_length=1)

    @field_validator("as_of_time")
    @classmethod
    def aware_as_of(cls, value: datetime) -> datetime:
        return _require_aware(value, "as_of_time")

    @property
    def all_evidence_refs(self) -> frozenset[str]:
        return frozenset(
            self.supporting_evidence_refs
            + self.opposing_evidence_refs
            + self.context_evidence_refs
        )


class EvidenceBoundBeliefUpdatePanel(ArtifactBase):
    records: tuple[BeliefUpdateRecord, ...]


class ClaimRecord(StrictModel):
    claim_id: str = Field(min_length=1)
    belief_update_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    created_at: datetime
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    claim_type: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    statement_summary: str = Field(min_length=1, max_length=500)
    relation: EvidenceRelation
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware_created_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")


class AgentReadingPanel(ArtifactBase):
    records: tuple[ClaimRecord, ...]


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
    evidence_kind: EvidenceKind
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
        return _require_aware(value, "available_at")


class EvidenceTagPanel(ArtifactMetadata):
    records: tuple[EvidenceTagRecord, ...]

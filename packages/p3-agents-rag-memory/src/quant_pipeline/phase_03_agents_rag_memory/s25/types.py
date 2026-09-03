"""Enums, scalar types and configuration contracts for P3.S25."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from .errors import S25ContractError, S25PolicyError

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
SignedSignal = Annotated[float, Field(ge=-1.0, le=1.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]


def _to_tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError("expected a JSON array")


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("expected an ISO-8601 datetime")
    if parsed.tzinfo is None:
        raise ValueError("datetime must include timezone information")
    return parsed.astimezone(UTC)


AwareDateTime = Annotated[
    datetime,
    BeforeValidator(_parse_datetime),
    AfterValidator(lambda value: value.astimezone(UTC)),
]
StringTuple = Annotated[tuple[NonEmptyStr, ...], BeforeValidator(_to_tuple)]


class StrictModel(BaseModel):
    """Strict immutable model for every S25 boundary."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        use_enum_values=False,
    )


class DeliveryStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    DELIVERED = "DELIVERED"
    SEEN = "SEEN"
    INTERPRETED = "INTERPRETED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class ExperienceType(StrEnum):
    DIRECT_EXPERIENCE = "DIRECT_EXPERIENCE"
    INDIRECT_REPUTATION = "INDIRECT_REPUTATION"
    MATURED_OUTCOME_FEEDBACK = "MATURED_OUTCOME_FEEDBACK"


class FeedbackStatus(StrEnum):
    MATURED = "MATURED"
    NOT_MATURED = "NOT_MATURED"
    REJECTED = "REJECTED"


class EntitlementStatus(StrEnum):
    ENTITLED = "ENTITLED"
    NOT_ENTITLED = "NOT_ENTITLED"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ValidationStatus(StrEnum):
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    DEFERRED_INSUFFICIENT_EVIDENCE = "DEFERRED_INSUFFICIENT_EVIDENCE"
    DEFERRED_CAPACITY = "DEFERRED_CAPACITY"
    REJECTED_POLICY = "REJECTED_POLICY"


class ChangeDecision(StrEnum):
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


class RetroPatchStatus(StrEnum):
    NO_PATCH = "NO_PATCH"
    ACTIVE = "ACTIVE"




def _enum_parser(enum_type: type[StrEnum]):
    def parse(value: Any) -> StrEnum:
        if isinstance(value, enum_type):
            return value
        if isinstance(value, str):
            return enum_type(value)
        raise TypeError(f"expected {enum_type.__name__} string")
    return parse


DeliveryStatusValue = Annotated[DeliveryStatus, BeforeValidator(_enum_parser(DeliveryStatus))]
ExperienceTypeValue = Annotated[ExperienceType, BeforeValidator(_enum_parser(ExperienceType))]
FeedbackStatusValue = Annotated[FeedbackStatus, BeforeValidator(_enum_parser(FeedbackStatus))]
EntitlementStatusValue = Annotated[EntitlementStatus, BeforeValidator(_enum_parser(EntitlementStatus))]
ExecutionStatusValue = Annotated[ExecutionStatus, BeforeValidator(_enum_parser(ExecutionStatus))]
ValidationStatusValue = Annotated[ValidationStatus, BeforeValidator(_enum_parser(ValidationStatus))]
EligibilityStatusValue = Annotated[EligibilityStatus, BeforeValidator(_enum_parser(EligibilityStatus))]
ChangeDecisionValue = Annotated[ChangeDecision, BeforeValidator(_enum_parser(ChangeDecision))]
RetroPatchStatusValue = Annotated[RetroPatchStatus, BeforeValidator(_enum_parser(RetroPatchStatus))]


class ArtifactContext(StrictModel):
    """Identity shared by all artifacts in one cycle."""

    schema_version: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonNegativeInt
    as_of_time: AwareDateTime
    lineage_id: NonEmptyStr


class RelationshipUpdateConfig(StrictModel):
    version: NonEmptyStr
    formula_version: NonEmptyStr
    max_trust_delta_per_cycle: Probability
    learning_rate: Probability
    domain_specific: Literal[True]
    direct_experience_weight: Probability
    indirect_reputation_weight: Probability
    matured_feedback_weight: Probability
    matured_feedback_required_for_accuracy_update: Literal[True]
    new_domain_initial_trust: Probability
    allowed_delivery_statuses: Annotated[
        tuple[DeliveryStatusValue, ...], BeforeValidator(_to_tuple)
    ]
    trust_domains: StringTuple
    domain_weights: dict[NonEmptyStr, Probability]
    allowed_relationship_types: StringTuple

    @model_validator(mode="after")
    def validate_config(self) -> "RelationshipUpdateConfig":
        if self.learning_rate > self.max_trust_delta_per_cycle:
            raise ValueError("learning_rate cannot exceed max_trust_delta_per_cycle")
        if set(self.domain_weights) != set(self.trust_domains):
            raise ValueError("domain_weights must cover exactly trust_domains")
        if sum(self.domain_weights.values()) <= 0:
            raise ValueError("domain_weights must have positive mass")
        return self


class RelationshipFormationConfig(StrictModel):
    version: NonEmptyStr
    minimum_repeated_interactions: PositiveInt
    minimum_mutual_relevance: Probability
    retro_named_edge_forbidden: Literal[True]
    requires_social_tool_entitlement: bool
    max_new_relationships_per_source_cycle: PositiveInt
    allowed_relationship_types: StringTuple
    initial_trust_by_domain: dict[NonEmptyStr, Probability]
    allowed_patch_parameters: StringTuple


class SocialGraphConfig(StrictModel):
    version: NonEmptyStr
    min_degree: NonNegativeInt
    max_degree: PositiveInt
    max_connected_components: PositiveInt
    min_bridge_edges_between_role_families: NonNegativeInt
    max_hub_share: Probability
    domain_trust_range: Annotated[
        tuple[float, float], BeforeValidator(_to_tuple)
    ]
    allowed_relationship_types: StringTuple
    degree_mode: Literal["total_unique_neighbors"]
    enforce_minimums: bool
    allow_parallel_relationship_types: bool

    @model_validator(mode="after")
    def validate_bounds(self) -> "SocialGraphConfig":
        lower, upper = self.domain_trust_range
        if lower < 0 or upper > 1 or lower > upper:
            raise ValueError("domain_trust_range must be ordered within [0, 1]")
        if self.min_degree > self.max_degree:
            raise ValueError("min_degree cannot exceed max_degree")
        return self


def reject_forbidden_policy_keys(parameters: dict[str, object]) -> None:
    """Reject per-person or per-edge Retro instructions."""
    forbidden_fragments = (
        "person_id",
        "source_person",
        "target_person",
        "edge_id",
        "relationship_change_id",
    )
    for key, value in parameters.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in forbidden_fragments):
            raise S25PolicyError(f"forbidden relationship patch key: {key}")
        serialized = str(value).lower()
        if any(fragment in serialized for fragment in forbidden_fragments):
            raise S25PolicyError("Retro patch cannot name a person or edge")

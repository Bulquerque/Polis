"""Strict boundary models for P3.S5.

Pydantic is intentionally confined to artifact and provider boundaries. Every model is
frozen, rejects unknown fields and disables permissive coercion.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]

class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        use_enum_values=False,
    )

class GenerationMode(StrEnum):
    NOVELTY = "NOVELTY"
    DENSITY = "DENSITY"

class ProviderKind(StrEnum):
    NVIDIA_NIM = "NVIDIA_NIM"
    HUGGINGFACE_ROUTER = "HUGGINGFACE_ROUTER"
    FIXTURE = "FIXTURE"

class AttemptStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    NON_RETRYABLE_FAILURE = "NON_RETRYABLE_FAILURE"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"

class CandidateDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"

class RunContext(StrictModel):
    run_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    as_of: datetime
    creator_run_id: str = Field(min_length=1)
    generation_round: NonNegativeInt
    seed: int

    @model_validator(mode="after")
    def timezone_required(self) -> RunContext:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return self

class TagDefinition(StrictModel):
    tag_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)

class TagCategory(StrictModel):
    category_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    tags: tuple[TagDefinition, ...] = Field(min_length=1)

class PersonalityTagRegistry(StrictModel):
    registry_id: str = Field(min_length=1)
    policy: Literal["fixed_registry_no_free_tag_creation"]
    assignment_fields: tuple[Literal["intensity", "confidence"], ...]
    categories: tuple[TagCategory, ...] = Field(min_length=1)
    schema_version: str = "personality_tag_registry.v2"

    @model_validator(mode="after")
    def unique_tags(self) -> PersonalityTagRegistry:
        ids = [tag.tag_id for category in self.categories for tag in category.tags]
        if len(ids) != len(set(ids)):
            raise ValueError("tag_id values must be unique")
        return self

    def tag_ids(self) -> frozenset[str]:
        return frozenset(tag.tag_id for category in self.categories for tag in category.tags)

class RoleDefinition(StrictModel):
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    role_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    allowed_objectives: tuple[str, ...] = Field(min_length=1)
    allowed_occupation_families: tuple[str, ...] = Field(min_length=1)
    required_resource_flags: tuple[str, ...] = ()
    minimum_capabilities: dict[str, UnitFloat] = Field(default_factory=dict)

class ExperienceBand(StrictModel):
    life_stage: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    minimum_years: NonNegativeInt
    maximum_years: NonNegativeInt

    @model_validator(mode="after")
    def valid_range(self) -> ExperienceBand:
        if self.minimum_years > self.maximum_years:
            raise ValueError("minimum_years cannot exceed maximum_years")
        return self

class PersonSchemaPolicy(StrictModel):
    schema_id: str = "person_schema_policy.v2"
    schema_version: str = "v14.1-rc4.1-p3r2"
    personality_tag_registry_id: str = Field(min_length=1)
    allowed_tag_ids: tuple[str, ...] = Field(min_length=1)
    roles: tuple[RoleDefinition, ...] = Field(min_length=1)
    objective_dimensions: tuple[str, ...] = Field(min_length=1)
    experience_bands: tuple[ExperienceBand, ...] = Field(min_length=1)
    education_rank: dict[str, NonNegativeInt] = Field(min_length=1)
    capability_minimum_education_rank: dict[str, dict[str, NonNegativeInt]] = Field(
        default_factory=dict
    )
    objective_sum_tolerance: float = Field(default=1e-9, gt=0.0)

    @model_validator(mode="after")
    def unique_roles_and_objectives(self) -> PersonSchemaPolicy:
        role_ids = [role.role_id for role in self.roles]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("role_id values must be unique")
        if len(self.objective_dimensions) != len(set(self.objective_dimensions)):
            raise ValueError("objective dimensions must be unique")
        if len(self.allowed_tag_ids) != len(set(self.allowed_tag_ids)):
            raise ValueError("allowed_tag_ids must be unique")
        return self

    def role_map(self) -> dict[str, RoleDefinition]:
        return {role.role_id: role for role in self.roles}

    def experience_map(self) -> dict[str, ExperienceBand]:
        return {band.life_stage: band for band in self.experience_bands}

class TagAssignment(StrictModel):
    tag_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    intensity: UnitFloat
    confidence: UnitFloat

class ObjectiveWeight(StrictModel):
    objective_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    weight: UnitFloat

class ResourceProfile(StrictModel):
    flags: tuple[str, ...] = ()
    information_access: UnitFloat
    research_time: UnitFloat
    computational_access: UnitFloat

class CapabilityProfile(StrictModel):
    research: UnitFloat
    quantitative: UnitFloat
    verbal: UnitFloat
    coding: UnitFloat
    tool_use: UnitFloat

class CandidateProposal(StrictModel):
    life_stage: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    years_experience: NonNegativeInt
    occupation_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    economic_role: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    role_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    institution_type: str | None = None
    geography: str = Field(min_length=1)
    education_level: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    resources: ResourceProfile
    capabilities: CapabilityProfile
    objective_weights: tuple[ObjectiveWeight, ...] = Field(min_length=1)
    tags: tuple[TagAssignment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_assignments(self) -> CandidateProposal:
        objective_ids = [item.objective_id for item in self.objective_weights]
        tag_ids = [item.tag_id for item in self.tags]
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("objective weights must have unique objective_id values")
        if len(tag_ids) != len(set(tag_ids)):
            raise ValueError("tags must have unique tag_id values")
        return self

class CandidateBatchProposal(StrictModel):
    candidates: tuple[CandidateProposal, ...] = Field(min_length=1)

class CandidateRecord(StrictModel):
    candidate_id: str = Field(pattern=r"^cand_[0-9a-f]{24}$")
    profile: CandidateProposal
    creator_run_id: str
    generation_round: NonNegativeInt
    generation_mode: GenerationMode
    provider_id: str
    model_id: str
    prompt_id: str
    prompt_version: str
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_id: str = Field(pattern=r"^lin_[0-9a-f]{24}$")

class PersonalityCandidatePool(StrictModel):
    schema_id: Literal["personality_candidate_pool.v2"] = "personality_candidate_pool.v2"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    run_id: str
    snapshot_id: str
    creator_run_id: str
    generation_round: NonNegativeInt
    generation_mode: GenerationMode
    candidates: tuple[CandidateRecord, ...]
    lineage_id: str

class ProviderUsage(StrictModel):
    prompt_tokens: NonNegativeInt | None = None
    completion_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None

class GenerationAttemptAudit(StrictModel):
    attempt_number: PositiveInt
    status: AttemptStatus
    provider_id: str
    provider_kind: ProviderKind
    model_id: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_request_id: str | None = None
    cache_hit: bool
    duration_ms: NonNegativeInt
    error_code: str | None = None
    error_message: str | None = None
    usage: ProviderUsage = Field(default_factory=ProviderUsage)

class PersonalityCreatorGenerationAudit(StrictModel):
    schema_id: Literal["personality_creator_generation_audit.v2"] = (
        "personality_creator_generation_audit.v2"
    )
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    run_id: str
    snapshot_id: str
    creator_run_id: str
    prompt_id: str
    prompt_version: str
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int
    generation_round: NonNegativeInt
    generation_mode: GenerationMode
    attempts: tuple[GenerationAttemptAudit, ...] = Field(min_length=1)
    final_status: AttemptStatus
    generated_candidate_count: NonNegativeInt
    lineage_id: str

class PriorPopulationGenerationState(StrictModel):
    schema_id: Literal["population_generation_state.v2"] = "population_generation_state.v2"
    creator_run_id: str
    generation_round: NonNegativeInt
    mode: GenerationMode
    accepted_candidate_ids: tuple[str, ...] = ()
    missing_coverage_cells: tuple[str, ...] = ()
    density_targets: tuple[str, ...] = ()

class PopulationGenerationConfig(StrictModel):
    config_id: Literal["P3_S5_POPULATION_GENERATION_CONFIG_V2"]
    requested_batch_size: PositiveInt = Field(le=100)
    creator_temperature: float = Field(ge=0.0, le=0.5)
    max_output_tokens: PositiveInt = Field(le=32768)
    prompt_id: str
    prompt_version: str
    no_free_tag_creation: Literal[True]
    structured_output_required: Literal[True]
    # Optional composition guidance for bounded populations. The S6 coverage
    # policy remains authoritative; this only makes its required role families
    # visible to the provider before S5 generation.
    required_role_families: tuple[str, ...] = ()

class ProviderAdapterConfig(StrictModel):
    provider_id: str
    provider_kind: ProviderKind
    base_url: str
    model_id: str
    timeout_seconds: float = Field(gt=0.0, le=300.0)
    max_connections: PositiveInt = Field(le=100)
    supports_strict_json_schema: bool
    api_key_env: str | None = None

class ProviderAdapterRegistryConfig(StrictModel):
    registry_id: str = Field(min_length=1)
    selected_provider_id: str = Field(min_length=1)
    providers: tuple[ProviderAdapterConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def selected_provider_exists(self) -> ProviderAdapterRegistryConfig:
        ids = [provider.provider_id for provider in self.providers]
        if len(ids) != len(set(ids)):
            raise ValueError("provider_id values must be unique")
        if self.selected_provider_id not in ids:
            raise ValueError("selected_provider_id is not registered")
        return self

    def selected_provider(self) -> ProviderAdapterConfig:
        return next(
            provider for provider in self.providers
            if provider.provider_id == self.selected_provider_id
        )

class RetryPolicy(StrictModel):
    max_provider_attempts: PositiveInt = Field(le=10)
    max_schema_repair_attempts: NonNegativeInt = Field(le=2)
    initial_backoff_seconds: float = Field(ge=0.0, le=60.0)
    maximum_backoff_seconds: float = Field(ge=0.0, le=300.0)
    retryable_status_codes: tuple[int, ...]
    failure_policy: Literal["fail_closed_no_fake_candidates"]

class ConsistencyRulesConfig(StrictModel):
    rules_version: str
    enabled_rules: tuple[
        Literal[
            "life_stage_experience",
            "occupation_role",
            "role_resources",
            "institution_tool_access",
            "role_objectives",
            "education_literacy",
        ],
        ...,
    ]
    violation_policy: Literal["reject_candidate_no_silent_repair"]

class GenerationRequest(StrictModel):
    run_context: RunContext
    personality_tag_registry: PersonalityTagRegistry
    person_schema_policy: PersonSchemaPolicy
    population_generation_config: PopulationGenerationConfig
    prior_population_generation_state: PriorPopulationGenerationState
    provider_adapter_registry_config: ProviderAdapterRegistryConfig
    retry_policy: RetryPolicy

class GenerationResult(StrictModel):
    personality_candidate_pool: PersonalityCandidatePool
    personality_creator_generation_audit: PersonalityCreatorGenerationAudit

class RuleViolation(StrictModel):
    rule_id: str
    severity: Severity
    field_path: str
    reason_code: str
    observed_value: str
    expected_constraint: str

class CandidateValidationResult(StrictModel):
    candidate_id: str
    decision: CandidateDecision
    violations: tuple[RuleViolation, ...]

class ValidatedPersonalityCandidatePool(StrictModel):
    schema_id: Literal["validated_personality_candidate_pool.v2"] = (
        "validated_personality_candidate_pool.v2"
    )
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    source_pool_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_candidates: tuple[CandidateRecord, ...]
    rejected_candidate_ids: tuple[str, ...]
    validation_results: tuple[CandidateValidationResult, ...]
    rules_version: str
    lineage_id: str

class ValidationRequest(StrictModel):
    personality_candidate_pool: PersonalityCandidatePool
    person_schema_policy: PersonSchemaPolicy
    consistency_rules_config: ConsistencyRulesConfig

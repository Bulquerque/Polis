"""Strict boundary models for P3.S7.

Upstream classes intentionally mirror P3.S6 v3. P3.S7 outputs are immutable,
closed and content-addressed for downstream foundation and runtime consumption.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Hash64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CandidateId = Annotated[str, Field(pattern=r"^cand_[0-9a-f]{24}$")]
LineageId = Annotated[str, Field(pattern=r"^lin_[0-9a-f]{24}$")]
PersonId = Annotated[str, Field(pattern=r"^person_[0-9a-f]{24}$")]
PopulationId = Annotated[str, Field(pattern=r"^population_[0-9a-f]{24}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        use_enum_values=False,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_json_arrays(cls, value: object) -> object:
        def convert(item: object) -> object:
            if isinstance(item, list):
                return tuple(convert(element) for element in item)
            if isinstance(item, dict):
                return {key: convert(element) for key, element in item.items()}
            return item
        return convert(value)


class GenerationMode(StrEnum):
    NOVELTY = "NOVELTY"
    DENSITY = "DENSITY"


class GenerationStatus(StrEnum):
    FINALIZED_VALID = "FINALIZED_VALID"


class CellType(StrEnum):
    TAG_BIN = "TAG_BIN"
    ROLE_FAMILY = "ROLE_FAMILY"
    PAIRWISE_TAG = "PAIRWISE_TAG"


class ValidationStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class IssueSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ExactClonePolicy(StrEnum):
    FORBID = "FORBID"


class WeightPolicy(StrEnum):
    EQUAL_WITHIN_ROLE_FAMILY_TARGET_SHARE = "EQUAL_WITHIN_ROLE_FAMILY_TARGET_SHARE"


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
    def unique_assignments(self) -> "CandidateProposal":
        objectives = [item.objective_id for item in self.objective_weights]
        tags = [item.tag_id for item in self.tags]
        if len(objectives) != len(set(objectives)):
            raise ValueError("objective weights must have unique objective_id values")
        if len(tags) != len(set(tags)):
            raise ValueError("tags must have unique tag_id values")
        return self


class CandidateRecord(StrictModel):
    candidate_id: CandidateId
    profile: CandidateProposal
    creator_run_id: str = Field(min_length=1)
    generation_round: NonNegativeInt
    generation_mode: GenerationMode
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    prompt_hash: Hash64
    request_hash: Hash64
    response_hash: Hash64
    lineage_id: LineageId


class CoverageCellStatus(StrictModel):
    cell_id: str = Field(min_length=1)
    cell_type: CellType
    covered: bool
    candidate_count: NonNegativeInt
    weighted_mass: UnitFloat


class CandidateDensityMetric(StrictModel):
    candidate_id: CandidateId
    novelty_distance: NonNegativeFloat
    mean_knn_distance: NonNegativeFloat | None
    local_density: NonNegativeFloat
    neighbor_count: NonNegativeInt
    density_sufficient: bool
    is_current_round_candidate: bool


class TagDistributionMetric(StrictModel):
    tag_id: str
    weighted_mean: UnitFloat
    weighted_variance: NonNegativeFloat


class CovarianceEntry(StrictModel):
    left_tag_id: str
    right_tag_id: str
    covariance: float


class CoverageSummary(StrictModel):
    tag_coverage_ratio: UnitFloat
    role_coverage_ratio: UnitFloat
    pairwise_coverage_ratio: UnitFloat
    overall_coverage_ratio: UnitFloat
    prior_coverage_ratio: UnitFloat
    marginal_coverage_gain: UnitFloat
    new_covered_cell_ids: tuple[str, ...]
    missing_cell_ids: tuple[str, ...]


class PersonalityCoverageReport(StrictModel):
    schema_id: Literal["personality_coverage_report.v3"] = "personality_coverage_report.v3"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    formula_id: Literal["p3.population.coverage"] = "p3.population.coverage"
    formula_version: Literal["1.0.0"] = "1.0.0"
    creator_run_id: str
    generation_round: NonNegativeInt
    mode: GenerationMode
    prior_patience_counter: NonNegativeInt
    candidate_count: PositiveInt
    current_round_candidate_ids: tuple[CandidateId, ...]
    candidate_weight_sum: float = Field(ge=0.999999999, le=1.000000001)
    coverage: CoverageSummary
    cells: tuple[CoverageCellStatus, ...]
    candidate_metrics: tuple[CandidateDensityMetric, ...]
    tag_distributions: tuple[TagDistributionMetric, ...]
    covariance_entries: tuple[CovarianceEntry, ...]
    mean_novelty_distance: NonNegativeFloat
    mean_knn_distance: NonNegativeFloat | None
    mean_local_density: NonNegativeFloat
    density_sufficiency_ratio: UnitFloat
    config_hash: Hash64
    accumulator_hash: Hash64
    report_hash: Hash64
    lineage_id: LineageId


class FinalizedPersonalityCandidatePool(StrictModel):
    schema_id: Literal["finalized_personality_candidate_pool.v3"] = "finalized_personality_candidate_pool.v3"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str
    final_generation_round: NonNegativeInt
    finalization_status: Literal[GenerationStatus.FINALIZED_VALID] = GenerationStatus.FINALIZED_VALID
    candidates: tuple[CandidateRecord, ...] = Field(min_length=1)
    coverage_report_hash: Hash64
    accumulator_hash: Hash64
    pool_hash: Hash64
    lineage_id: LineageId


class DistanceWeights(StrictModel):
    categorical: UnitFloat
    resources: UnitFloat
    capabilities: UnitFloat
    objectives: UnitFloat
    tags: UnitFloat

    @model_validator(mode="after")
    def sum_to_one(self) -> "DistanceWeights":
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-12:
            raise ValueError("distance weights must sum to one")
        return self


class PopulationRepresentationConfig(StrictModel):
    config_id: Literal["P3_S7_POPULATION_REPRESENTATION_CONFIG_V2"]
    config_version: Literal["2.0.0"]
    architecture_revision: Literal["P3-FINAL"]
    person_id_algorithm: Literal["sha256_typed_canonical_profile_v1"]
    population_id_algorithm: Literal["sha256_sorted_person_ids_v1"]
    seed_algorithm: Literal["sha256_uint63_v1"]
    weight_policy: Literal[WeightPolicy.EQUAL_WITHIN_ROLE_FAMILY_TARGET_SHARE]
    target_role_family_shares: dict[str, PositiveFloat] = Field(min_length=1)
    role_family_share_tolerance: NonNegativeFloat = 1e-9
    sum_tolerance: NonNegativeFloat = 1e-9
    max_single_person_weight: UnitFloat = 0.08
    min_effective_population: PositiveFloat = 20.0
    minimum_population_size: PositiveInt = 20
    minimum_overall_coverage_ratio: UnitFloat = 1.0
    minimum_tag_coverage_ratio: UnitFloat = 1.0
    minimum_role_coverage_ratio: UnitFloat = 1.0
    minimum_density_sufficiency_ratio: UnitFloat = 0.60
    exact_clone_policy: Literal[ExactClonePolicy.FORBID] = ExactClonePolicy.FORBID
    near_clone_distance_threshold: UnitFloat = 0.025
    max_near_clone_person_share: UnitFloat = 0.10
    distance_weights: DistanceWeights
    objective_weight_sum_tolerance: NonNegativeFloat = 1e-9
    profile_numeric_precision: Annotated[int, Field(ge=6, le=15)] = 12

    @model_validator(mode="after")
    def validate_config(self) -> "PopulationRepresentationConfig":
        if abs(sum(self.target_role_family_shares.values()) - 1.0) > self.sum_tolerance:
            raise ValueError("target role-family shares must sum to one")
        if len(self.target_role_family_shares) != len(set(self.target_role_family_shares)):
            raise ValueError("target role-family IDs must be unique")
        if self.max_single_person_weight <= 0.0:
            raise ValueError("max_single_person_weight must be positive")
        return self


class CreatorProvenance(StrictModel):
    creator_run_id: str
    generation_round: NonNegativeInt
    generation_mode: GenerationMode
    provider_id: str
    model_id: str
    prompt_id: str
    prompt_version: str
    prompt_hash: Hash64
    request_hash: Hash64
    response_hash: Hash64
    candidate_lineage_id: LineageId


class FrozenPerson(StrictModel):
    person_id: PersonId
    candidate_id: CandidateId
    representation_weight: UnitFloat
    profile: CandidateProposal
    creator_provenance: CreatorProvenance
    person_seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    profile_fingerprint: Hash64
    freeze_contract_version: Literal["P3.S7.v2"] = "P3.S7.v2"
    lineage_id: LineageId


class PersonSeedRecord(StrictModel):
    person_id: PersonId
    candidate_id: CandidateId
    person_seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    seed_algorithm: Literal["sha256_uint63_v1"]
    seed_namespace_hash: Hash64
    population_id: PopulationId
    lineage_id: LineageId


class PersonSeedPanel(StrictModel):
    schema_id: Literal["person_seed_panel.v2"] = "person_seed_panel.v2"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str
    population_id: PopulationId
    records: tuple[PersonSeedRecord, ...] = Field(min_length=1)
    panel_hash: Hash64
    lineage_id: LineageId

    @model_validator(mode="after")
    def unique_records(self) -> "PersonSeedPanel":
        for values, label in [
            ([item.person_id for item in self.records], "person_id"),
            ([item.candidate_id for item in self.records], "candidate_id"),
            ([item.person_seed for item in self.records], "person_seed"),
        ]:
            if len(values) != len(set(values)):
                raise ValueError(f"person seed records require unique {label}")
        return self


class PopulationManifest(StrictModel):
    schema_id: Literal["population_manifest.v2"] = "population_manifest.v2"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str
    population_id: PopulationId
    final_generation_round: NonNegativeInt
    person_count: PositiveInt
    persons: tuple[FrozenPerson, ...] = Field(min_length=1)
    target_role_family_shares: dict[str, PositiveFloat]
    realized_role_family_shares: dict[str, UnitFloat]
    weight_sum: float = Field(ge=0.999999999, le=1.000000001)
    max_person_weight: UnitFloat
    effective_population_size: PositiveFloat
    finalized_pool_hash: Hash64
    coverage_report_hash: Hash64
    representation_config_hash: Hash64
    person_seed_panel_hash: Hash64
    manifest_hash: Hash64
    lineage_id: LineageId

    @model_validator(mode="after")
    def count_and_uniqueness(self) -> "PopulationManifest":
        if self.person_count != len(self.persons):
            raise ValueError("person_count must equal persons length")
        for values, label in [
            ([item.person_id for item in self.persons], "person_id"),
            ([item.candidate_id for item in self.persons], "candidate_id"),
            ([item.person_seed for item in self.persons], "person_seed"),
        ]:
            if len(values) != len(set(values)):
                raise ValueError(f"population manifest requires unique {label}")
        return self


class ValidationIssue(StrictModel):
    issue_code: str = Field(pattern=r"^[A-Z0-9_]+$")
    severity: IssueSeverity
    message: str = Field(min_length=1)
    subject_ids: tuple[str, ...] = ()


class ValidationCheck(StrictModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    status: CheckStatus
    observed: str
    expected: str
    issue_codes: tuple[str, ...] = ()


class ExactCloneGroup(StrictModel):
    profile_fingerprint: Hash64
    person_ids: tuple[PersonId, ...] = Field(min_length=2)


class NearClonePair(StrictModel):
    left_person_id: PersonId
    right_person_id: PersonId
    distance: UnitFloat


class ValidatedPopulationManifest(StrictModel):
    schema_id: Literal["validated_population_manifest.v2"] = "validated_population_manifest.v2"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    validation_status: ValidationStatus
    population_manifest: PopulationManifest
    checks: tuple[ValidationCheck, ...]
    issues: tuple[ValidationIssue, ...]
    exact_clone_groups: tuple[ExactCloneGroup, ...]
    near_clone_pairs: tuple[NearClonePair, ...]
    near_clone_person_share: UnitFloat
    validated_manifest_hash: Hash64
    lineage_id: LineageId
    production_promotion_allowed: Literal[False] = False

    @model_validator(mode="after")
    def status_matches_issues(self) -> "ValidatedPopulationManifest":
        has_error = any(issue.severity is IssueSeverity.ERROR for issue in self.issues)
        if has_error != (self.validation_status is ValidationStatus.BLOCKED):
            raise ValueError("validation status must match error issues")
        return self


class FixedPopulationBuildRequest(StrictModel):
    finalized_personality_candidate_pool: FinalizedPersonalityCandidatePool
    personality_coverage_report: PersonalityCoverageReport
    population_representation_config: PopulationRepresentationConfig


class FixedPopulationBuildResult(StrictModel):
    person_seed_panel: PersonSeedPanel
    population_manifest: PopulationManifest


class PopulationValidationRequest(StrictModel):
    person_seed_panel: PersonSeedPanel
    population_manifest: PopulationManifest
    personality_coverage_report: PersonalityCoverageReport
    population_representation_config: PopulationRepresentationConfig


class PopulationValidationResult(StrictModel):
    validated_population_manifest: ValidatedPopulationManifest

"""Strict boundary models for P3.S6.

The upstream candidate models mirror P3.S5 v2. P3.S6 introduces generation state v3,
which carries the immutable accumulator required to recompute metrics without hidden state.
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
        """Convert JSON/YAML arrays to immutable tuples without coercing scalars."""
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

class CandidateDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"

class GenerationStatus(StrEnum):
    CONTINUE = "CONTINUE"
    TRANSITION_TO_DENSITY = "TRANSITION_TO_DENSITY"
    FINALIZED_VALID = "FINALIZED_VALID"
    DEGRADED_MAX_ROUNDS = "DEGRADED_MAX_ROUNDS"
    FAILED_MAX_ROUNDS = "FAILED_MAX_ROUNDS"

class ControlAction(StrEnum):
    GENERATE_NOVELTY = "GENERATE_NOVELTY"
    GENERATE_DENSITY = "GENERATE_DENSITY"
    FINALIZE = "FINALIZE"
    STOP_DEGRADED = "STOP_DEGRADED"
    STOP_FAILED = "STOP_FAILED"

class CellType(StrEnum):
    TAG_BIN = "TAG_BIN"
    ROLE_FAMILY = "ROLE_FAMILY"
    PAIRWISE_TAG = "PAIRWISE_TAG"

class CandidateWeightPolicy(StrEnum):
    UNIFORM = "UNIFORM"

class CovarianceMode(StrEnum):
    WEIGHTED_POPULATION = "WEIGHTED_POPULATION"

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
    def unique_tags(self) -> "PersonalityTagRegistry":
        ids = [tag.tag_id for category in self.categories for tag in category.tags]
        if len(ids) != len(set(ids)):
            raise ValueError("tag_id values must be unique")
        return self

    def tag_ids(self) -> tuple[str, ...]:
        return tuple(sorted(tag.tag_id for category in self.categories for tag in category.tags))

    def category_by_tag(self) -> dict[str, str]:
        return {
            tag.tag_id: category.category_id
            for category in self.categories
            for tag in category.tags
        }

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

class RuleViolation(StrictModel):
    rule_id: str = Field(min_length=1)
    severity: Severity
    field_path: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    observed_value: str
    expected_constraint: str

class CandidateValidationResult(StrictModel):
    candidate_id: str = Field(min_length=1)
    decision: CandidateDecision
    violations: tuple[RuleViolation, ...]

class ValidatedPersonalityCandidatePool(StrictModel):
    schema_id: Literal["validated_personality_candidate_pool.v2"] = (
        "validated_personality_candidate_pool.v2"
    )
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    source_pool_hash: Hash64
    accepted_candidates: tuple[CandidateRecord, ...]
    rejected_candidate_ids: tuple[str, ...]
    validation_results: tuple[CandidateValidationResult, ...]
    rules_version: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

class IntensityBin(StrictModel):
    bin_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    lower: UnitFloat
    upper: UnitFloat
    include_upper: bool = False

    @model_validator(mode="after")
    def valid_interval(self) -> "IntensityBin":
        if self.lower >= self.upper:
            raise ValueError("intensity bin lower must be smaller than upper")
        if self.upper == 1.0 and not self.include_upper:
            raise ValueError("the terminal bin must include 1.0")
        return self

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper if self.include_upper else self.lower <= value < self.upper

class TagCoverageRequirement(StrictModel):
    tag_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    required_bin_ids: tuple[str, ...] = Field(min_length=1)

class PairwiseTagCell(StrictModel):
    cell_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    left_tag_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    right_tag_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    left_min_effective_value: UnitFloat
    right_min_effective_value: UnitFloat

    @model_validator(mode="after")
    def distinct_tags(self) -> "PairwiseTagCell":
        if self.left_tag_id == self.right_tag_id:
            raise ValueError("pairwise cell tags must be distinct")
        return self

class CoverageDensityConfig(StrictModel):
    config_id: Literal["P3_S6_COVERAGE_DENSITY_CONFIG_V2"]
    config_version: Literal["2.0.0"]
    intensity_bins: tuple[IntensityBin, ...] = Field(min_length=1)
    tag_coverage_requirements: tuple[TagCoverageRequirement, ...] = Field(min_length=1)
    required_role_families: tuple[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")], ...] = Field(min_length=1)
    pairwise_tag_cells: tuple[PairwiseTagCell, ...] = ()
    tag_category_weights: dict[str, PositiveFloat] = Field(default_factory=dict)
    default_tag_category_weight: PositiveFloat = 1.0
    candidate_weight_policy: Literal[CandidateWeightPolicy.UNIFORM] = CandidateWeightPolicy.UNIFORM
    covariance_mode: Literal[CovarianceMode.WEIGHTED_POPULATION] = CovarianceMode.WEIGHTED_POPULATION
    knn_k: PositiveInt = 5
    distance_floor: PositiveFloat = 1e-9
    density_radius: PositiveFloat = 0.45
    coverage_epsilon: UnitFloat = 0.01
    patience_rounds: PositiveInt = 5
    minimum_novelty_rounds: PositiveInt = 3
    target_population_size: PositiveInt = 50
    max_generation_rounds: PositiveInt = 100
    minimum_coverage_ratio: UnitFloat = 1.0
    minimum_tag_coverage_ratio: UnitFloat = 1.0
    minimum_role_coverage_ratio: UnitFloat = 1.0
    minimum_density_sufficiency_ratio: UnitFloat = 0.60
    degraded_minimum_coverage_ratio: UnitFloat = 0.80
    output_rounding_digits: NonNegativeInt = Field(default=12, le=15)

    @model_validator(mode="after")
    def validate_config(self) -> "CoverageDensityConfig":
        ordered = sorted(self.intensity_bins, key=lambda item: item.lower)
        if tuple(ordered) != self.intensity_bins:
            raise ValueError("intensity_bins must be ordered by lower bound")
        if self.intensity_bins[0].lower != 0.0 or self.intensity_bins[-1].upper != 1.0:
            raise ValueError("intensity bins must span [0, 1]")
        for left, right in zip(self.intensity_bins, self.intensity_bins[1:]):
            if left.upper != right.lower:
                raise ValueError("intensity bins must be contiguous")
        bin_ids = [item.bin_id for item in self.intensity_bins]
        if len(bin_ids) != len(set(bin_ids)):
            raise ValueError("intensity bin IDs must be unique")
        required_tags = [item.tag_id for item in self.tag_coverage_requirements]
        if len(required_tags) != len(set(required_tags)):
            raise ValueError("tag coverage requirements must be unique by tag_id")
        known_bins = set(bin_ids)
        for requirement in self.tag_coverage_requirements:
            if len(requirement.required_bin_ids) != len(set(requirement.required_bin_ids)):
                raise ValueError("required bin IDs must be unique per tag")
            if not set(requirement.required_bin_ids) <= known_bins:
                raise ValueError("tag coverage requirement references unknown bin")
        pair_ids = [item.cell_id for item in self.pairwise_tag_cells]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("pairwise cell IDs must be unique")
        if len(self.required_role_families) != len(set(self.required_role_families)):
            raise ValueError("required role families must be unique")
        if self.minimum_novelty_rounds > self.max_generation_rounds:
            raise ValueError("minimum_novelty_rounds cannot exceed max_generation_rounds")
        if self.degraded_minimum_coverage_ratio > self.minimum_coverage_ratio:
            raise ValueError("degraded threshold cannot exceed normal threshold")
        return self

    def bin_map(self) -> dict[str, IntensityBin]:
        return {item.bin_id: item for item in self.intensity_bins}

class AccumulatorRecord(StrictModel):
    candidate: CandidateRecord
    first_seen_round: NonNegativeInt
    source_pool_hash: Hash64
    candidate_content_hash: Hash64

class PopulationCandidateAccumulator(StrictModel):
    schema_id: Literal["population_candidate_accumulator.v3"] = (
        "population_candidate_accumulator.v3"
    )
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str = Field(min_length=1)
    current_round: NonNegativeInt
    records: tuple[AccumulatorRecord, ...]
    accumulator_hash: Hash64
    lineage_id: LineageId

class PriorPopulationGenerationStateV2(StrictModel):
    schema_id: Literal["population_generation_state.v2"] = "population_generation_state.v2"
    creator_run_id: str = Field(min_length=1)
    generation_round: NonNegativeInt
    mode: GenerationMode
    accepted_candidate_ids: tuple[str, ...] = ()
    missing_coverage_cells: tuple[str, ...] = ()
    density_targets: tuple[str, ...] = ()

class PopulationGenerationStateV3(StrictModel):
    schema_id: Literal["population_generation_state.v3"] = "population_generation_state.v3"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str = Field(min_length=1)
    generation_round: NonNegativeInt
    mode: GenerationMode
    accepted_candidate_ids: tuple[str, ...]
    covered_cell_ids: tuple[str, ...]
    missing_coverage_cells: tuple[str, ...]
    density_targets: tuple[str, ...]
    patience_counter: NonNegativeInt
    previous_coverage_ratio: UnitFloat
    accumulator: PopulationCandidateAccumulator
    terminal_status: GenerationStatus | None = None
    state_hash: Hash64
    lineage_id: LineageId

class S5CompatiblePriorState(StrictModel):
    schema_id: Literal["population_generation_state.v2"] = "population_generation_state.v2"
    creator_run_id: str
    generation_round: NonNegativeInt
    mode: GenerationMode
    accepted_candidate_ids: tuple[str, ...]
    missing_coverage_cells: tuple[str, ...]
    density_targets: tuple[str, ...]

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

class PopulationGenerationControl(StrictModel):
    schema_id: Literal["population_generation_control.v3"] = "population_generation_control.v3"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str
    generation_round: NonNegativeInt
    current_mode: GenerationMode
    next_mode: GenerationMode | None
    status: GenerationStatus
    action: ControlAction
    stop_reason: str | None
    patience_counter: NonNegativeInt
    required_missing_cell_ids: tuple[str, ...]
    materialize_next_state: bool
    materialize_finalized_pool: bool
    control_hash: Hash64
    lineage_id: LineageId

    @model_validator(mode="after")
    def exclusive_materialization(self) -> "PopulationGenerationControl":
        if self.materialize_next_state == self.materialize_finalized_pool:
            raise ValueError("exactly one downstream artifact must be materialized")
        return self

class FinalizedPersonalityCandidatePool(StrictModel):
    schema_id: Literal["finalized_personality_candidate_pool.v3"] = (
        "finalized_personality_candidate_pool.v3"
    )
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str
    final_generation_round: NonNegativeInt
    finalization_status: Literal[GenerationStatus.FINALIZED_VALID] = GenerationStatus.FINALIZED_VALID
    candidates: tuple[CandidateRecord, ...] = Field(min_length=1)
    coverage_report_hash: Hash64
    accumulator_hash: Hash64
    pool_hash: Hash64
    lineage_id: LineageId

class CoverageCalculationRequest(StrictModel):
    validated_personality_candidate_pool: ValidatedPersonalityCandidatePool
    personality_tag_registry: PersonalityTagRegistry
    coverage_density_config: CoverageDensityConfig
    prior_population_generation_state: PriorPopulationGenerationStateV2 | PopulationGenerationStateV3

class CoverageCalculationResult(StrictModel):
    personality_coverage_report: PersonalityCoverageReport
    population_candidate_accumulator: PopulationCandidateAccumulator

class CoverageControlRequest(StrictModel):
    personality_coverage_report: PersonalityCoverageReport
    population_candidate_accumulator: PopulationCandidateAccumulator
    coverage_density_config: CoverageDensityConfig

class CoverageControlResult(StrictModel):
    population_generation_control: PopulationGenerationControl
    next_population_generation_state: PopulationGenerationStateV3 | None = None
    finalized_personality_candidate_pool: FinalizedPersonalityCandidatePool | None = None

    @model_validator(mode="after")
    def result_matches_control(self) -> "CoverageControlResult":
        control = self.population_generation_control
        if control.materialize_next_state:
            if self.next_population_generation_state is None or self.finalized_personality_candidate_pool is not None:
                raise ValueError("control requires only next_population_generation_state")
        else:
            if self.finalized_personality_candidate_pool is None or self.next_population_generation_state is not None:
                raise ValueError("control requires only finalized_personality_candidate_pool")
        return self

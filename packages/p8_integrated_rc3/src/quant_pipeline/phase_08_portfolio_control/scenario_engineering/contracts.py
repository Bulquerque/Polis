"""Strict public contracts for P8.S3."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class DistributionType(StrEnum):
    PARAMETRIC = "PARAMETRIC"
    MIXTURE = "MIXTURE"
    QUANTILE = "QUANTILE"
    EMPIRICAL = "EMPIRICAL"
    PATH = "PATH"


class ProbabilityMeasure(StrEnum):
    PHYSICAL = "PHYSICAL"
    RISK_NEUTRAL = "RISK_NEUTRAL"
    STRESS_WEIGHT = "STRESS_WEIGHT"


class HorizonUnit(StrEnum):
    HOURS = "HOURS"
    CALENDAR_DAYS = "CALENDAR_DAYS"
    TRADING_SESSIONS = "TRADING_SESSIONS"


class QualityStatus(StrEnum):
    FULLY_QUALIFIED = "FULLY_QUALIFIED"
    QUALIFIED_WITH_HAIRCUT = "QUALIFIED_WITH_HAIRCUT"
    TAIL_INCOMPLETE = "TAIL_INCOMPLETE"
    PATH_INCOMPLETE = "PATH_INCOMPLETE"
    REGIME_INCOMPLETE = "REGIME_INCOMPLETE"
    DECISION_UNSTABLE = "DECISION_UNSTABLE"
    NOT_ACTIONABLE = "NOT_ACTIONABLE"


class ReductionStatus(StrEnum):
    SAFE = "SAFE"
    SCENARIO_REDUCTION_UNSAFE = "SCENARIO_REDUCTION_UNSAFE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


class ActionabilityState(StrEnum):
    NOMINAL_ACTIONABLE = "NOMINAL_ACTIONABLE"
    ROBUST_ONLY = "ROBUST_ONLY"
    DEGRADED_ACTIONABLE = "DEGRADED_ACTIONABLE"
    CLOSE_ONLY = "CLOSE_ONLY"
    NO_NEW_RISK = "NO_NEW_RISK"
    NO_ACTION_VALID = "NO_ACTION_VALID"


class ArtifactRef(StrictModel):
    artifact_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = "1.0.0"
    contract_version: str = "1.0.0"


class HorizonSpec(StrictModel):
    value: int = Field(gt=0)
    unit: HorizonUnit


class ParametricPayload(StrictModel):
    kind: Literal["parametric"] = "parametric"
    family: Literal["NORMAL", "STUDENT_T"]
    mean: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    degrees_freedom: float | None = Field(default=None, gt=2.0)


class MixtureComponent(StrictModel):
    weight: float = Field(gt=0.0, le=1.0)
    family: Literal["NORMAL", "STUDENT_T"]
    mean: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    degrees_freedom: float | None = Field(default=None, gt=2.0)


class MixturePayload(StrictModel):
    kind: Literal["mixture"] = "mixture"
    components: tuple[MixtureComponent, ...] = Field(min_length=2)


class QuantilePayload(StrictModel):
    kind: Literal["quantile"] = "quantile"
    levels: tuple[float, ...]
    values: tuple[tuple[float, ...], ...]
    gaussian_copula_correlation: tuple[tuple[float, ...], ...] | None = None


class EmpiricalPayload(StrictModel):
    kind: Literal["empirical"] = "empirical"
    samples: tuple[tuple[float, ...], ...]
    probabilities: tuple[float, ...] | None = None


class PathPayload(StrictModel):
    kind: Literal["path"] = "path"
    paths: tuple[tuple[tuple[float, ...], ...], ...]
    probabilities: tuple[float, ...] | None = None
    step_labels: tuple[str, ...]


DistributionPayload = Annotated[
    ParametricPayload | MixturePayload | QuantilePayload | EmpiricalPayload | PathPayload,
    Field(discriminator="kind"),
]


class BeliefRecord(StrictModel):
    belief_state_id: str
    target_id: str
    factor_ids: tuple[str, ...] = Field(min_length=1)
    distribution_type: DistributionType
    probability_measure: ProbabilityMeasure
    forecast_horizon: HorizonSpec
    holding_horizon: HorizonSpec
    evaluation_horizon: HorizonSpec
    expiration_horizon: HorizonSpec | None = None
    payload: DistributionPayload
    calibration_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ood_score: float | None = Field(default=None, ge=0.0, le=1.0)
    disagreement_score: float | None = Field(default=None, ge=0.0, le=1.0)
    regime_id: str | None = None
    available_at: datetime
    decision_time: datetime
    source_ref: ArtifactRef

    @model_validator(mode="after")
    def validate_semantics(self) -> "BeliefRecord":
        if self.available_at.tzinfo is None or self.decision_time.tzinfo is None:
            raise ValueError("available_at and decision_time must be timezone-aware")
        if self.available_at.astimezone(timezone.utc) > self.decision_time.astimezone(timezone.utc):
            raise ValueError("available_at must not be after decision_time")
        expected = self.distribution_type.value.lower()
        actual = self.payload.kind
        if expected == "path":
            expected = "path"
        if actual != expected:
            raise ValueError(f"distribution_type {self.distribution_type} conflicts with payload {actual}")
        return self


class HistoricalScenarioPanel(StrictModel):
    factor_ids: tuple[str, ...]
    samples: tuple[tuple[float, ...], ...]
    sample_available_at: tuple[datetime, ...]
    decision_time: datetime
    probabilities: tuple[float, ...] | None = None


class ScenarioPolicy(StrictModel):
    scenario_count: int = Field(default=256, ge=16, le=100_000)
    sampling_method: Literal["PSEUDO_RANDOM", "SOBOL"] = "PSEUDO_RANDOM"
    seed_entropy: int = Field(default=20260803, ge=0)
    historical_weight: float = Field(default=0.0, ge=0.0, lt=1.0)
    probability_tolerance: float = Field(default=1e-10, gt=0.0)
    quantile_epsilon: float = Field(default=1e-8, gt=0.0, lt=0.1)


class QualityPolicy(StrictModel):
    mean_relative_error_max: float = Field(default=0.35, ge=0.0)
    covariance_relative_error_max: float = Field(default=0.50, ge=0.0)
    quantile_absolute_error_max: float = Field(default=0.20, ge=0.0)
    tail_quantile_error_max: float = Field(default=0.35, ge=0.0)
    minimum_realized_samples: int = Field(default=30, ge=5)
    require_paths_for_families: tuple[str, ...] = ("CALENDAR", "PATH_DEPENDENT")


class StressTemplate(StrictModel):
    stress_id: str
    factor_shocks: dict[str, float]
    mode: Literal["ADDITIVE", "MULTIPLICATIVE"] = "ADDITIVE"
    severity: float = Field(default=1.0, gt=0.0)
    tags: tuple[str, ...] = ()


class StressPolicy(StrictModel):
    templates: tuple[StressTemplate, ...] = ()
    reverse_stress_tolerance: float = Field(default=1e-4, gt=0.0)
    reverse_stress_max_multiplier: float = Field(default=64.0, gt=1.0)
    reverse_stress_max_iterations: int = Field(default=64, ge=8, le=512)


class ReductionPolicy(StrictModel):
    target_count: int = Field(default=64, ge=2)
    preserve_tail_count: int = Field(default=4, ge=0)
    mean_error_max: float = Field(default=0.15, ge=0.0)
    covariance_error_max: float = Field(default=0.25, ge=0.0)
    tail_error_max: float = Field(default=0.20, ge=0.0)
    first_action_tolerance: float = Field(default=1e-8, ge=0.0)
    max_pairwise_elements: int = Field(default=4_000_000, ge=10_000)


class ActionabilityPolicy(StrictModel):
    nominal_quality_floor: float = Field(default=0.80, ge=0.0, le=1.0)
    degraded_quality_floor: float = Field(default=0.55, ge=0.0, le=1.0)
    no_new_risk_floor: float = Field(default=0.25, ge=0.0, le=1.0)
    max_ambiguity_radius: float = Field(default=0.35, ge=0.0, le=1.0)
    max_margin_buffer: float = Field(default=0.50, ge=0.0)
    max_liquidity_haircut: float = Field(default=0.75, ge=0.0, le=1.0)


class RealizedSamplePanel(StrictModel):
    factor_ids: tuple[str, ...]
    samples: tuple[tuple[float, ...], ...]
    available_at: datetime
    decision_time: datetime


class S3Request(StrictModel):
    run_id: str
    cycle_id: str
    belief: BeliefRecord
    strategy_families: tuple[str, ...] = ("LINEAR",)
    historical_scenarios: HistoricalScenarioPanel | None = None
    realized_samples: RealizedSamplePanel | None = None
    scenario_policy: ScenarioPolicy = ScenarioPolicy()
    quality_policy: QualityPolicy = QualityPolicy()
    stress_policy: StressPolicy = StressPolicy()
    reduction_policy: ReductionPolicy = ReductionPolicy()
    actionability_policy: ActionabilityPolicy = ActionabilityPolicy()
    ordinal_risk_cap: float | None = Field(default=None, ge=0.0, le=1.0)


class DistributionResolution(StrictModel):
    distribution_type: DistributionType
    probability_measure: ProbabilityMeasure
    factor_ids: tuple[str, ...]
    step_labels: tuple[str, ...]
    path_capability: Literal["TERMINAL_ONLY", "FULL_PATH"]
    content_sha256: str
    warnings: tuple[str, ...] = ()


class ScenarioSetSummary(StrictModel):
    artifact_id: str
    scenario_count: int
    step_count: int
    factor_count: int
    probability_sum: float
    content_sha256: str
    storage_npz: str | None = None


class QualityMetric(StrictModel):
    name: str
    value: float | None
    threshold: float | None
    passed: bool | None
    reason_code: str | None = None


class QualityAssessment(StrictModel):
    status_by_family: dict[str, QualityStatus]
    score: float = Field(ge=0.0, le=1.0)
    metrics: tuple[QualityMetric, ...]
    reason_codes: tuple[str, ...] = ()


class StressResult(StrictModel):
    stress_scenario_count: int
    stress_artifact_id: str
    stress_content_sha256: str
    reverse_stress_status: Literal["COMPUTED", "CAPABILITY_UNAVAILABLE", "NO_FAILURE_WITHIN_BOUND"]
    reverse_stress_multiplier: float | None = None
    failure_states: tuple[str, ...] = ()


class ReductionAssessment(StrictModel):
    status: ReductionStatus
    original_count: int
    output_count: int
    mean_error: float
    covariance_error: float
    tail_error: float
    transport_cost: float
    decision_aware_status: Literal["EVALUATED", "CAPABILITY_UNAVAILABLE"]
    content_sha256: str


class AmbiguityAssessment(StrictModel):
    actionability_state: ActionabilityState
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    ambiguity_radius: float = Field(ge=0.0)
    risk_budget_cap: float = Field(ge=0.0, le=1.0)
    liquidity_haircut: float = Field(ge=0.0, le=1.0)
    margin_buffer: float = Field(ge=0.0)
    probability_lower_bounds: tuple[float, ...]
    probability_upper_bounds: tuple[float, ...]
    reason_codes: tuple[str, ...] = ()


class ModuleReceipt(StrictModel):
    module_id: str
    input_sha256: str
    output_sha256: str
    status: Literal["PASS", "DEGRADED", "CAPABILITY_UNAVAILABLE", "NO_ACTION_VALID"]
    reason_codes: tuple[str, ...] = ()


class S3Result(StrictModel):
    run_id: str
    cycle_id: str
    resolution: DistributionResolution
    full_scenarios: ScenarioSetSummary
    quality: QualityAssessment
    stress: StressResult
    reduced_scenarios: ScenarioSetSummary
    reduction: ReductionAssessment
    ambiguity: AmbiguityAssessment
    receipts: tuple[ModuleReceipt, ...]
    result_sha256: str

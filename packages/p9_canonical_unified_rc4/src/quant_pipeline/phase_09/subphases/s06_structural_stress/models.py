from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    AmbiguityFamily,
    BreachDirection,
    CapabilityState,
    EvidenceClass,
    EvidenceReference,
    FiniteFloat,
    ModuleReceipt,
    NonEmptyStr,
    NonNegativeFloat,
    OutputSemantics,
    PositiveInt,
    Probability,
    ReplayMode,
    RunContext,
    S5QualificationReference,
    S6State,
    ScenarioClass,
    SeedPolicy,
    StrictModel,
    utc_datetime,
    content_sha256,
)
from .policies import (
    AmbiguitySetPolicy,
    CapacityStressPolicy,
    EVTPolicy,
    HistoricalReplayPolicy,
    ReverseStressPolicy,
    ScenarioGovernancePolicy,
    SensitivityPolicy,
    StressValidationPolicy,
)


class FactorShock(StrictModel):
    factor_id: NonEmptyStr
    value: FiniteFloat
    unit: NonEmptyStr


class ScenarioProposal(StrictModel):
    scenario_id: NonEmptyStr
    name: NonEmptyStr
    scenario_class: ScenarioClass
    created_at: datetime
    purpose: NonEmptyStr
    approved_uses: tuple[NonEmptyStr, ...]
    prohibited_uses: tuple[NonEmptyStr, ...] = ()
    shocks: tuple[FactorShock, ...]
    horizon_days: PositiveInt
    severity_label: NonEmptyStr
    plausibility_label: NonEmptyStr

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)

    @model_validator(mode="after")
    def validate_scenario(self) -> Self:
        if not self.approved_uses:
            raise ValueError("approved_uses must not be empty")
        if not self.shocks:
            raise ValueError("shocks must not be empty")
        ids = [shock.factor_id for shock in self.shocks]
        if len(ids) != len(set(ids)):
            raise ValueError("factor shocks must be unique within a scenario")
        if set(self.approved_uses) & set(self.prohibited_uses):
            raise ValueError("approved_uses and prohibited_uses must be disjoint")
        return self


class MaterialRiskDefinition(StrictModel):
    risk_id: NonEmptyStr
    factor_ids: tuple[NonEmptyStr, ...]
    materiality_weight: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_factors(self) -> Self:
        if not self.factor_ids:
            raise ValueError("factor_ids must not be empty")
        if len(self.factor_ids) != len(set(self.factor_ids)):
            raise ValueError("factor_ids must be unique")
        return self


class MaterialRiskCoverage(StrictModel):
    risk_id: NonEmptyStr
    covered: bool
    covering_scenario_ids: tuple[NonEmptyStr, ...]
    materiality_weight: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class CommittedScenario(StrictModel):
    scenario: ScenarioProposal
    semantic_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ScenarioRegistryRequest(StrictModel):
    context: RunContext
    s5_qualification: S5QualificationReference
    proposals: tuple[ScenarioProposal, ...]
    material_risks: tuple[MaterialRiskDefinition, ...]
    outcome_results_observed_at: datetime | None = None
    policy: ScenarioGovernancePolicy = ScenarioGovernancePolicy()

    @field_validator("outcome_results_observed_at")
    @classmethod
    def normalize_optional_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc_datetime(value)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not self.proposals:
            raise ValueError("proposals must not be empty")
        ids = [proposal.scenario_id for proposal in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario_ids must be unique")
        risk_ids = [risk.risk_id for risk in self.material_risks]
        if len(risk_ids) != len(set(risk_ids)):
            raise ValueError("material risk ids must be unique")
        return self


class StressScenarioRegistrySnapshot(StrictModel):
    status: S6State
    registry_id: NonEmptyStr
    scenarios: tuple[CommittedScenario, ...]
    duplicate_scenario_ids: tuple[NonEmptyStr, ...]
    risk_coverage: tuple[MaterialRiskCoverage, ...]
    weighted_material_risk_coverage: Probability
    commitment_time: datetime
    registry_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()

    @field_validator("commitment_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)


class FactorPath(StrictModel):
    path_id: NonEmptyStr
    timestamps: tuple[datetime, ...]
    factor_ids: tuple[NonEmptyStr, ...]
    values: tuple[tuple[FiniteFloat, ...], ...]
    units: tuple[NonEmptyStr, ...]
    evidence_classes: tuple[EvidenceClass, ...]

    @field_validator("timestamps")
    @classmethod
    def normalize_timestamps(cls, values: tuple[datetime, ...]) -> tuple[datetime, ...]:
        return tuple(utc_datetime(value) for value in values)

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        n = len(self.timestamps)
        k = len(self.factor_ids)
        if n < 2 or k < 1:
            raise ValueError("factor path requires at least two timestamps and one factor")
        if any(right <= left for left, right in zip(self.timestamps, self.timestamps[1:])):
            raise ValueError("timestamps must be strictly increasing")
        if len(set(self.factor_ids)) != k:
            raise ValueError("factor_ids must be unique")
        if len(self.units) != k or len(self.evidence_classes) != k:
            raise ValueError("factor metadata lengths must match factor_ids")
        if len(self.values) != n or any(len(row) != k for row in self.values):
            raise ValueError("values must be rectangular and match timestamps/factors")
        return self


class ExposureRecord(StrictModel):
    exposure_id: NonEmptyStr
    position_id: NonEmptyStr
    current_factor_id: NonEmptyStr
    notional: FiniteFloat
    linear_sensitivity: FiniteFloat
    quadratic_sensitivity: FiniteFloat = 0.0
    evidence_class: EvidenceClass


class FactorMapping(StrictModel):
    current_factor_id: NonEmptyStr
    historical_factor_id: NonEmptyStr
    scale: FiniteFloat = 1.0
    evidence_class: EvidenceClass


class HistoricalReplayRequest(StrictModel):
    context: RunContext
    registry: StressScenarioRegistrySnapshot
    scenario_id: NonEmptyStr
    factor_path: FactorPath
    exposures: tuple[ExposureRecord, ...]
    mappings: tuple[FactorMapping, ...] = ()
    replay_mode: ReplayMode = ReplayMode.STATIC_EXPOSURE
    frozen_exposure_scales: tuple[FiniteFloat, ...] | None = None
    policy: HistoricalReplayPolicy = HistoricalReplayPolicy()

    @model_validator(mode="after")
    def validate_replay(self) -> Self:
        if not self.exposures:
            raise ValueError("exposures must not be empty")
        if self.replay_mode is ReplayMode.FROZEN_DYNAMIC_POLICY:
            if self.frozen_exposure_scales is None:
                raise ValueError("dynamic replay requires frozen_exposure_scales")
            if len(self.frozen_exposure_scales) != len(self.factor_path.timestamps):
                raise ValueError("frozen_exposure_scales must match factor-path timestamps")
        elif self.frozen_exposure_scales is not None:
            raise ValueError("static replay must not receive frozen_exposure_scales")
        return self


class ExposureMappingResult(StrictModel):
    exposure_id: NonEmptyStr
    current_factor_id: NonEmptyStr
    historical_factor_id: NonEmptyStr | None
    mapping_scale: FiniteFloat | None
    evidence_class: EvidenceClass
    mapped: bool
    notional: FiniteFloat


class ReplayPoint(StrictModel):
    timestamp: datetime
    pnl: FiniteFloat
    cumulative_pnl: FiniteFloat
    mapped_pnl: FiniteFloat
    modelled_pnl: FiniteFloat
    unmapped_notional: NonNegativeFloat

    @field_validator("timestamp")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)


class HistoricalCrisisReplayResult(StrictModel):
    status: S6State
    scenario_id: NonEmptyStr
    replay_mode: ReplayMode
    mappings: tuple[ExposureMappingResult, ...]
    path: tuple[ReplayPoint, ...]
    mapped_exposure_share: Probability
    modelled_pnl_share: Probability
    unmapped_notional: NonNegativeFloat
    worst_cumulative_pnl: FiniteFloat
    recovery_included: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class QuadraticResponseModel(StrictModel):
    model_id: NonEmptyStr
    factor_ids: tuple[NonEmptyStr, ...]
    units: tuple[NonEmptyStr, ...]
    baseline_value: FiniteFloat
    linear_coefficients: tuple[FiniteFloat, ...]
    quadratic_matrix: tuple[tuple[FiniteFloat, ...], ...]
    semantics: OutputSemantics
    model_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        n = len(self.factor_ids)
        if n < 1 or len(set(self.factor_ids)) != n:
            raise ValueError("factor_ids must be non-empty and unique")
        if len(self.units) != n or len(self.linear_coefficients) != n:
            raise ValueError("model vectors must match factor_ids")
        if len(self.quadratic_matrix) != n or any(len(row) != n for row in self.quadratic_matrix):
            raise ValueError("quadratic_matrix must be square")
        for i in range(n):
            for j in range(n):
                if abs(self.quadratic_matrix[i][j] - self.quadratic_matrix[j][i]) > 1e-12:
                    raise ValueError("quadratic_matrix must be symmetric")
        return self


class FactorAxis(StrictModel):
    factor_id: NonEmptyStr
    grid_values: tuple[FiniteFloat, ...]
    observed_min: FiniteFloat | None = None
    observed_max: FiniteFloat | None = None

    @model_validator(mode="after")
    def validate_grid(self) -> Self:
        if len(self.grid_values) < 2:
            raise ValueError("grid_values requires at least two points")
        if tuple(sorted(set(self.grid_values))) != self.grid_values:
            raise ValueError("grid_values must be unique and increasing")
        if (self.observed_min is None) != (self.observed_max is None):
            raise ValueError("observed range requires both endpoints")
        if self.observed_min is not None and self.observed_min > self.observed_max:
            raise ValueError("observed_min must not exceed observed_max")
        return self


class ConstraintDefinition(StrictModel):
    constraint_id: NonEmptyStr
    threshold: FiniteFloat
    breach_direction: BreachDirection


class SensitivitySurfaceRequest(StrictModel):
    context: RunContext
    registry: StressScenarioRegistrySnapshot
    response_model: QuadraticResponseModel
    axes: tuple[FactorAxis, ...]
    constraints: tuple[ConstraintDefinition, ...] = ()
    policy: SensitivityPolicy = SensitivityPolicy()

    @model_validator(mode="after")
    def validate_axes(self) -> Self:
        if not self.axes:
            raise ValueError("axes must not be empty")
        axis_ids = [axis.factor_id for axis in self.axes]
        if len(axis_ids) != len(set(axis_ids)):
            raise ValueError("axis factor ids must be unique")
        if not set(axis_ids).issubset(self.response_model.factor_ids):
            raise ValueError("all axis factors must exist in response model")
        return self


class SurfacePoint(StrictModel):
    shocks: tuple[tuple[NonEmptyStr, FiniteFloat], ...]
    output_value: FiniteFloat
    extrapolated: bool
    breached_constraint_ids: tuple[NonEmptyStr, ...]


class FactorSensitivity(StrictModel):
    factor_id: NonEmptyStr
    local_gradient: FiniteFloat
    curvature: FiniteFloat
    main_effect_range: NonNegativeFloat


class InteractionSensitivity(StrictModel):
    factor_id_left: NonEmptyStr
    factor_id_right: NonEmptyStr
    interaction_coefficient: FiniteFloat


class ConstraintCliff(StrictModel):
    factor_id: NonEmptyStr
    left_shock: FiniteFloat
    right_shock: FiniteFloat
    relative_jump: NonNegativeFloat
    constraint_ids: tuple[NonEmptyStr, ...]


class SensitivitySurfaceResult(StrictModel):
    status: S6State
    model_id: NonEmptyStr
    points: tuple[SurfacePoint, ...]
    factor_sensitivities: tuple[FactorSensitivity, ...]
    interactions: tuple[InteractionSensitivity, ...]
    cliffs: tuple[ConstraintCliff, ...]
    evaluation_count: PositiveInt
    extrapolated_point_fraction: Probability
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class EVTRequest(StrictModel):
    context: RunContext
    loss_series_id: NonEmptyStr
    losses: tuple[FiniteFloat, ...]
    conditional_scales: tuple[Annotated[float, Field(gt=0, allow_inf_nan=False)], ...] | None = None
    seed_policy: SeedPolicy
    policy: EVTPolicy = EVTPolicy()

    @model_validator(mode="after")
    def validate_series(self) -> Self:
        if len(self.losses) < 20:
            raise ValueError("losses requires at least 20 observations")
        if self.conditional_scales is not None and len(self.conditional_scales) != len(self.losses):
            raise ValueError("conditional_scales must match losses")
        return self


class EVTParameterInterval(StrictModel):
    parameter: NonEmptyStr
    estimate: FiniteFloat
    low: FiniteFloat | None
    high: FiniteFloat | None


class ConditionalEVTResult(StrictModel):
    status: S6State
    loss_series_id: NonEmptyStr
    threshold: FiniteFloat | None
    exceedance_count: int = Field(ge=0)
    tail_index: FiniteFloat | None
    scale_parameter: FiniteFloat | None = Field(default=None, gt=0)
    conditional_var: FiniteFloat | None
    conditional_expected_shortfall: FiniteFloat | None
    residual_lag1_autocorrelation: FiniteFloat | None
    threshold_tail_index_range: NonNegativeFloat | None
    ks_statistic: NonNegativeFloat | None
    parameter_intervals: tuple[EVTParameterInterval, ...] = ()
    capability_state: CapabilityState
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class EmpiricalScenarioDistribution(StrictModel):
    distribution_id: NonEmptyStr
    scenario_ids: tuple[NonEmptyStr, ...]
    state_vectors: tuple[tuple[FiniteFloat, ...], ...]
    losses: tuple[FiniteFloat, ...]
    scores: tuple[FiniteFloat, ...] | None = None

    @model_validator(mode="after")
    def validate_distribution(self) -> Self:
        n = len(self.scenario_ids)
        if n < 2 or len(set(self.scenario_ids)) != n:
            raise ValueError("scenario_ids must be unique with at least two scenarios")
        if len(self.state_vectors) != n or len(self.losses) != n:
            raise ValueError("state_vectors/losses must match scenario_ids")
        widths = {len(row) for row in self.state_vectors}
        if len(widths) != 1 or next(iter(widths)) < 1:
            raise ValueError("state_vectors must be rectangular and non-empty")
        if self.scores is not None and len(self.scores) != n:
            raise ValueError("scores must match scenario_ids")
        return self


class DRORequest(StrictModel):
    context: RunContext
    distribution: EmpiricalScenarioDistribution
    policy: AmbiguitySetPolicy


class DROFrontierPoint(StrictModel):
    radius: NonNegativeFloat
    worst_case_mean_loss: FiniteFloat
    worst_case_cvar: FiniteFloat
    worst_case_score: FiniteFloat | None
    transport_cost: NonNegativeFloat
    solver_status: NonEmptyStr
    target_probabilities: tuple[Probability, ...]


class DistributionalRobustnessResult(StrictModel):
    status: S6State
    family: AmbiguityFamily
    empirical_mean_loss: FiniteFloat
    empirical_cvar: FiniteFloat
    empirical_mean_score: FiniteFloat | None
    frontier: tuple[DROFrontierPoint, ...]
    capability_state: CapabilityState
    radius_calibrated: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class ExecutionLeg(StrictModel):
    instrument_id: NonEmptyStr
    trade_weight: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    gross_exposure_multiple: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    average_daily_volume: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    spread_bps: NonNegativeFloat
    impact_coefficient_bps: NonNegativeFloat
    impact_exponent: Annotated[float, Field(gt=1.0, allow_inf_nan=False)] = 1.5
    max_participation_rate: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 0.1
    borrow_bps: NonNegativeFloat = 0.0
    funding_bps: NonNegativeFloat = 0.0
    margin_rate: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    evidence_class: EvidenceClass


class NetworkStressInput(StrictModel):
    overlap_matrix: tuple[tuple[NonNegativeFloat, ...], ...]
    initial_forced_sale: tuple[NonNegativeFloat, ...]

    @model_validator(mode="after")
    def validate_network(self) -> Self:
        n = len(self.initial_forced_sale)
        invalid_shape = (
            n < 1
            or len(self.overlap_matrix) != n
            or any(len(row) != n for row in self.overlap_matrix)
        )
        if invalid_shape:
            raise ValueError("network matrix must be square and match initial_forced_sale")
        return self


class CapacityRequest(StrictModel):
    context: RunContext
    base_aum: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    annual_gross_return: FiniteFloat
    annual_turnover_ratio: NonNegativeFloat
    aum_grid: tuple[Annotated[float, Field(gt=0, allow_inf_nan=False)], ...]
    legs: tuple[ExecutionLeg, ...]
    network_stress: NetworkStressInput | None = None
    policy: CapacityStressPolicy = CapacityStressPolicy()

    @model_validator(mode="after")
    def validate_capacity(self) -> Self:
        if tuple(sorted(set(self.aum_grid))) != self.aum_grid:
            raise ValueError("aum_grid must be unique and increasing")
        if not self.legs:
            raise ValueError("legs must not be empty")
        total_weight = sum(leg.trade_weight for leg in self.legs)
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("trade weights must sum to one")
        return self


class CapacityPoint(StrictModel):
    aum: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    net_return: FiniteFloat
    annual_cost_fraction: NonNegativeFloat
    maximum_participation_rate: NonNegativeFloat
    liquidation_horizon_days: NonNegativeFloat
    margin_usage_fraction: NonNegativeFloat
    evidence_class: EvidenceClass
    feasible: bool


class CapacityResult(StrictModel):
    status: S6State
    points: tuple[CapacityPoint, ...]
    break_even_aum: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    capacity_limit_aum: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    maximum_liquidation_horizon_days: NonNegativeFloat
    minimum_margin_buffer: FiniteFloat
    network_spectral_radius: NonNegativeFloat | None
    network_loss_amplification: NonNegativeFloat | None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class FactorBound(StrictModel):
    factor_id: NonEmptyStr
    lower: FiniteFloat
    upper: FiniteFloat
    norm_weight: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1.0

    @model_validator(mode="after")
    def validate_bound(self) -> Self:
        if self.lower >= self.upper:
            raise ValueError("lower must be less than upper")
        if not self.lower <= 0.0 <= self.upper:
            raise ValueError("factor bounds must include the baseline zero shock")
        return self


class FailureCondition(StrictModel):
    condition_id: NonEmptyStr
    threshold: FiniteFloat
    breach_direction: BreachDirection


class ReverseStressRequest(StrictModel):
    context: RunContext
    response_model: QuadraticResponseModel
    bounds: tuple[FactorBound, ...]
    failure_condition: FailureCondition
    seed_policy: SeedPolicy
    policy: ReverseStressPolicy = ReverseStressPolicy()

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        ids = [bound.factor_id for bound in self.bounds]
        if len(ids) != len(set(ids)):
            raise ValueError("factor bounds must be unique")
        if set(ids) != set(self.response_model.factor_ids):
            raise ValueError("bounds must cover every response-model factor exactly")
        return self


class ReverseStressResult(StrictModel):
    status: S6State
    condition_id: NonEmptyStr
    distance_to_failure: NonNegativeFloat | None
    shock_vector: tuple[tuple[NonEmptyStr, FiniteFloat], ...]
    stressed_value: FiniteFloat | None
    binding_condition: NonEmptyStr | None
    verification_error: NonNegativeFloat | None
    solution_count: int = Field(ge=0)
    safe_axis_distances: tuple[tuple[NonEmptyStr, FiniteFloat | None], ...]
    solver_messages: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class StressValidationRequest(StrictModel):
    context: RunContext
    registry: StressScenarioRegistrySnapshot
    historical_replay: HistoricalCrisisReplayResult
    sensitivity: SensitivitySurfaceResult
    evt: ConditionalEVTResult | None
    dro: DistributionalRobustnessResult | None
    capacity: CapacityResult
    reverse_stress: ReverseStressResult
    policy: StressValidationPolicy = StressValidationPolicy()


class StressCheck(StrictModel):
    check_id: NonEmptyStr
    passed: bool
    detail: NonEmptyStr


class ApprovedUseDecision(StrictModel):
    use_id: NonEmptyStr
    approved: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()


class StressModelValidationResult(StrictModel):
    status: S6State
    checks: tuple[StressCheck, ...]
    approved_uses: tuple[ApprovedUseDecision, ...]
    material_risk_coverage: Probability
    failed_check_count: int = Field(ge=0)
    specialist_capability_states: tuple[tuple[NonEmptyStr, CapabilityState], ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class S6RunRequest(StrictModel):
    scenario_registry: ScenarioRegistryRequest
    crisis_factor_path: FactorPath
    crisis_exposures: tuple[ExposureRecord, ...]
    crisis_mappings: tuple[FactorMapping, ...] = ()
    crisis_scenario_id: NonEmptyStr
    crisis_replay_mode: ReplayMode = ReplayMode.STATIC_EXPOSURE
    crisis_frozen_exposure_scales: tuple[FiniteFloat, ...] | None = None
    historical_replay_policy: HistoricalReplayPolicy = HistoricalReplayPolicy()
    sensitivity_response_model: QuadraticResponseModel
    sensitivity_axes: tuple[FactorAxis, ...]
    sensitivity_constraints: tuple[ConstraintDefinition, ...] = ()
    sensitivity_policy: SensitivityPolicy = SensitivityPolicy()
    evt: EVTRequest | None = None
    dro: DRORequest | None = None
    capacity: CapacityRequest
    reverse_bounds: tuple[FactorBound, ...]
    reverse_failure_condition: FailureCondition
    reverse_seed_policy: SeedPolicy
    reverse_policy: ReverseStressPolicy = ReverseStressPolicy()
    validation_policy: StressValidationPolicy = StressValidationPolicy()

    @model_validator(mode="after")
    def validate_contexts(self) -> Self:
        base = self.scenario_registry.context
        contexts = [self.capacity.context]
        if self.evt is not None:
            contexts.append(self.evt.context)
        if self.dro is not None:
            contexts.append(self.dro.context)
        if any(context != base for context in contexts):
            raise ValueError("all S6 requests must share the same RunContext")
        return self


class S6OutputBundle(StrictModel):
    bundle_id: NonEmptyStr
    context: RunContext
    scenario_registry: StressScenarioRegistrySnapshot
    historical_replay: HistoricalCrisisReplayResult
    sensitivity: SensitivitySurfaceResult
    evt: ConditionalEVTResult | None
    dro: DistributionalRobustnessResult | None
    capacity: CapacityResult
    reverse_stress: ReverseStressResult
    validation: StressModelValidationResult
    module_receipts: tuple[ModuleReceipt, ...]
    bundle_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    def hash_preimage(self) -> dict[str, object]:
        return {
            "context": self.context.model_dump(mode="json"),
            "registry": content_sha256(self.scenario_registry),
            "historical": content_sha256(self.historical_replay),
            "sensitivity": content_sha256(self.sensitivity),
            "evt": content_sha256(self.evt),
            "dro": content_sha256(self.dro),
            "capacity": content_sha256(self.capacity),
            "reverse": content_sha256(self.reverse_stress),
            "validation": content_sha256(self.validation),
            "receipts": [content_sha256(receipt) for receipt in self.module_receipts],
        }

    @model_validator(mode="after")
    def validate_receipts_and_hash(self) -> Self:
        expected = {f"P9.S6.M0{i}" for i in range(1, 9)}
        actual = {receipt.module_id for receipt in self.module_receipts}
        if actual != expected or len(self.module_receipts) != 8:
            raise ValueError("module receipts must cover P9.S6.M01-M08 exactly")
        if content_sha256(self.hash_preimage()) != self.bundle_sha256:
            raise ValueError("S6 bundle hash mismatch")
        return self


class RobustnessStressBundleManifest(StrictModel):
    manifest_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    s5_bundle_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    s6_bundle_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    s5_qualification_status: NonEmptyStr
    s6_validation_status: S6State
    manifest_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        preimage = {
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "s5_bundle_sha256": self.s5_bundle_sha256,
            "s6_bundle_sha256": self.s6_bundle_sha256,
            "s5_qualification_status": self.s5_qualification_status,
            "s6_validation_status": self.s6_validation_status,
        }
        if content_sha256(preimage) != self.manifest_sha256:
            raise ValueError("robustness-stress manifest hash mismatch")
        return self

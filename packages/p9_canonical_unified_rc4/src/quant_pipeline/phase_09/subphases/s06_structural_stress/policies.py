from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from .contracts import (
    AmbiguityFamily,
    FiniteFloat,
    NonEmptyStr,
    PositiveInt,
    Probability,
    ReverseNorm,
    StrictModel,
)


class ScenarioGovernancePolicy(StrictModel):
    minimum_material_risk_coverage: Probability = 0.9
    reject_post_outcome_commitment: bool = True
    duplicate_semantic_hash_rejected: bool = True


class HistoricalReplayPolicy(StrictModel):
    minimum_mapped_exposure_share: Probability = 0.9
    maximum_modelled_pnl_share: Probability = 0.35
    require_recovery_path: bool = True


class SensitivityPolicy(StrictModel):
    maximum_evaluations: PositiveInt = 20_000
    cliff_relative_threshold: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.25
    extrapolation_margin: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    interaction_tolerance: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 1e-10


class EVTPolicy(StrictModel):
    threshold_quantile: Annotated[float, Field(gt=0.5, lt=1.0, allow_inf_nan=False)] = 0.95
    threshold_sensitivity_step: Annotated[float, Field(gt=0, lt=0.1, allow_inf_nan=False)] = 0.01
    minimum_exceedances: PositiveInt = 40
    confidence_level: Annotated[float, Field(gt=0.5, lt=1.0, allow_inf_nan=False)] = 0.99
    parameter_bootstrap_replicates: PositiveInt = 200
    ewma_lambda: Annotated[float, Field(gt=0, lt=1.0, allow_inf_nan=False)] = 0.94
    maximum_absolute_residual_autocorrelation: Probability = 0.15
    maximum_tail_index_range: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.35
    minimum_scale: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1e-12


class AmbiguitySetPolicy(StrictModel):
    family: AmbiguityFamily = AmbiguityFamily.DISCRETE_SUPPORT_WASSERSTEIN_1
    radius_grid: tuple[Annotated[float, Field(ge=0, allow_inf_nan=False)], ...]
    cvar_confidence_level: Annotated[float, Field(gt=0.5, lt=1.0, allow_inf_nan=False)] = 0.95
    radius_calibration_id: NonEmptyStr | None = None
    solver_method: NonEmptyStr = "highs"
    maximum_scenarios: PositiveInt = 80

    @model_validator(mode="after")
    def validate_radii(self) -> "AmbiguitySetPolicy":
        if not self.radius_grid:
            raise ValueError("radius_grid must not be empty")
        if tuple(sorted(set(self.radius_grid))) != self.radius_grid:
            raise ValueError("radius_grid must be unique and increasing")
        if self.radius_grid[0] != 0.0:
            raise ValueError("radius_grid must begin at zero")
        return self


class CapacityStressPolicy(StrictModel):
    trading_days_per_year: PositiveInt = 252
    margin_limit_fraction: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1.0
    break_even_tolerance: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1e-10
    allow_extrapolation: bool = True
    network_spectral_radius_limit: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.98


class ReverseStressPolicy(StrictModel):
    norm: ReverseNorm = ReverseNorm.WEIGHTED_L2
    maximum_iterations: PositiveInt = 500
    solver_tolerance: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1e-9
    verification_tolerance: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1e-7
    minimum_safe_distance: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.25
    multi_start_points: PositiveInt = 16


class StressValidationPolicy(StrictModel):
    minimum_material_risk_coverage: Probability = 0.9
    minimum_mapped_exposure_share: Probability = 0.9
    maximum_modelled_pnl_share: Probability = 0.35
    require_evt: bool = False
    require_dro: bool = False
    require_capacity: bool = True
    require_reverse_stress: bool = True
    maximum_reverse_verification_error: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 1e-6
    minimum_reverse_distance: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.25
    monotonicity_tolerance: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 1e-10

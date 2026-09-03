"""Strong V2 contracts for scenario, ambiguity, dependence and regime artifacts."""
from __future__ import annotations

from datetime import datetime

import numpy as np
from pydantic import Field, model_validator

from .core import FrozenModel
from .v2_base import ScenarioType, V2ArtifactIdentity, ValidityStatus


class ScenarioPathRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    decision_time: datetime
    horizon: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    scenario_type: ScenarioType
    probability: float | None = Field(default=None, gt=0.0, le=1.0)
    path_step: int = Field(ge=0)
    path_timestamp: datetime
    future_spot: float | None = Field(default=None, gt=0.0)
    future_return: float | None = None
    realized_volatility_state: float | None = Field(default=None, ge=0.0)
    implied_volatility_state: float | None = Field(default=None, ge=0.0)
    skew_state: float | None = None
    term_structure_state: float | None = None
    liquidity_state: float | None = None
    regime_state: str | None = None
    jump_state: bool | None = None
    stress_flags: tuple[str, ...] = ()
    seed: int
    generator_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scenario(self) -> "ScenarioPathRecord":
        if self.scenario_type is ScenarioType.NOMINAL and self.probability is None:
            raise ValueError("nominal scenarios require probability")
        if self.scenario_type is ScenarioType.STRESS and self.probability is not None:
            raise ValueError("deterministic stress scenarios cannot claim statistical probability")
        if self.future_spot is None and self.future_return is None:
            raise ValueError("scenario requires future_spot or future_return")
        return self


class ScenarioPathPanel(V2ArtifactIdentity):
    records: tuple[ScenarioPathRecord, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_mass(self) -> "ScenarioPathPanel":
        terminal: dict[tuple[str, str], ScenarioPathRecord] = {}
        for row in self.records:
            key = (row.underlying, row.scenario_id)
            previous = terminal.get(key)
            if previous is None or row.path_step > previous.path_step:
                terminal[key] = row
        by_underlying: dict[str, dict[str, float]] = {}
        for row in terminal.values():
            if row.scenario_type is ScenarioType.NOMINAL and row.probability is not None:
                by_underlying.setdefault(row.underlying, {})[row.scenario_id] = row.probability
        for probabilities in by_underlying.values():
            if abs(sum(probabilities.values()) - 1.0) > 1e-8:
                raise ValueError("terminal nominal scenario probability mass must equal one")
        return self


class AmbiguitySetRecord(FrozenModel):
    nominal_distribution_id: str = Field(min_length=1)
    ambiguity_method: str = Field(min_length=1)
    radius_or_band: float | tuple[float, float]
    calibration_sample_size: int = Field(ge=1)
    coverage_target: float = Field(gt=0.0, lt=1.0)
    plausible_distribution_ids: tuple[str, ...] = Field(min_length=1)
    stress_distribution_ids: tuple[str, ...] = ()
    scope: dict[str, str] = Field(min_length=1)
    validity_status: ValidityStatus
    lineage_id: str = Field(min_length=1)


class AmbiguitySet(V2ArtifactIdentity):
    records: tuple[AmbiguitySetRecord, ...] = Field(min_length=1)


class DependenceStateRecord(FrozenModel):
    covariance_type: str = Field(min_length=1)
    covariance_matrix: tuple[tuple[float, ...], ...] = Field(min_length=2)
    correlation_matrix: tuple[tuple[float, ...], ...] = Field(min_length=2)
    effective_rank: float = Field(gt=0.0)
    condition_number: float = Field(ge=1.0)
    psd_status: str = Field(min_length=1)
    repair_magnitude: float = Field(ge=0.0)
    estimation_window: tuple[datetime, datetime]
    underlying_order: tuple[str, ...] = Field(min_length=2)
    horizon: str = Field(min_length=1)
    champion_status: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_matrices(self) -> "DependenceStateRecord":
        size = len(self.underlying_order)
        covariance = np.asarray(self.covariance_matrix, dtype=float)
        correlation = np.asarray(self.correlation_matrix, dtype=float)
        if covariance.shape != (size, size) or correlation.shape != (size, size):
            raise ValueError("dependence matrices must align with underlying_order")
        if not np.allclose(covariance, covariance.T, atol=1e-8):
            raise ValueError("covariance matrix must be symmetric")
        if not np.allclose(correlation, correlation.T, atol=1e-8):
            raise ValueError("correlation matrix must be symmetric")
        if not np.allclose(np.diag(correlation), 1.0, atol=1e-6):
            raise ValueError("correlation matrix diagonal must equal one")
        return self


class DependenceState(V2ArtifactIdentity):
    records: tuple[DependenceStateRecord, ...] = Field(min_length=1)


class RegimeOODStateRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    regime_probabilities: dict[str, float] = Field(min_length=1)
    transition_probabilities: dict[str, dict[str, float]] = Field(default_factory=dict)
    expected_duration: dict[str, float] = Field(default_factory=dict)
    change_point_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    feature_ood: float | None = Field(default=None, ge=0.0)
    model_ood: float | None = Field(default=None, ge=0.0)
    market_state_ood: float | None = Field(default=None, ge=0.0)
    dependence_ood: float | None = Field(default=None, ge=0.0)
    severity: str = Field(min_length=1)
    validity_status: ValidityStatus = ValidityStatus.VALID
    reason_codes: tuple[str, ...] = ()
    lineage_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_regimes(self) -> "RegimeOODStateRecord":
        if abs(sum(self.regime_probabilities.values()) - 1.0) > 1e-8:
            raise ValueError("regime probabilities must sum to one")
        return self


class RegimeOODState(V2ArtifactIdentity):
    records: tuple[RegimeOODStateRecord, ...] = Field(min_length=1)

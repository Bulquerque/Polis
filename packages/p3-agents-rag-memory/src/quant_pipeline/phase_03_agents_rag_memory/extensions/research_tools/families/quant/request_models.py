"""Strict request contracts for the quantitative diagnostic operations."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr, utc

from .model_base import (
    BinningPolicy,
    CorrelationMethod,
    EntropyMethod,
    EventAdjustment,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    Probability,
    QuantMode,
    ReturnKind,
    VolatilityEstimator,
)


class TimeBoundRequest(ContractModel):
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def aware_times(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def ordered_window(self) -> "TimeBoundRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not be after end_time")
        return self


class ReturnStatisticsRequest(TimeBoundRequest):
    instrument_id: NonEmptyStr
    view_id: NonEmptyStr = "market_prices"
    research_mode: QuantMode = QuantMode.BASIC
    return_kind: ReturnKind = ReturnKind.SIMPLE
    quantiles: tuple[Annotated[float, Field(gt=0.0, lt=1.0)], ...] = (0.05, 0.5, 0.95)
    trim_fraction: Annotated[float, Field(ge=0.0, lt=0.5)] = 0.1
    annualization_factor: PositiveFloat = 252.0

    @model_validator(mode="after")
    def quantiles_unique_and_sorted(self) -> "ReturnStatisticsRequest":
        if not self.quantiles:
            raise ValueError("at least one quantile is required")
        if tuple(sorted(set(self.quantiles))) != self.quantiles:
            raise ValueError("quantiles must be unique and sorted")
        return self


class RealizedVolatilityRequest(TimeBoundRequest):
    instrument_id: NonEmptyStr
    view_id: NonEmptyStr = "market_prices"
    research_mode: QuantMode = QuantMode.BASIC
    estimators: tuple[VolatilityEstimator, ...] = (VolatilityEstimator.CLOSE_TO_CLOSE,)
    annualization_factor: PositiveFloat = 252.0
    bootstrap_samples: Annotated[int, Field(ge=0, le=2000)] = 0
    bootstrap_confidence: Annotated[float, Field(gt=0.5, lt=1.0)] = 0.95
    block_length: PositiveInt = 5

    @model_validator(mode="after")
    def estimators_unique(self) -> "RealizedVolatilityRequest":
        if not self.estimators:
            raise ValueError("at least one estimator is required")
        if len(set(self.estimators)) != len(self.estimators):
            raise ValueError("estimators must be unique")
        return self


class DrawdownRequest(TimeBoundRequest):
    instrument_id: NonEmptyStr
    view_id: NonEmptyStr = "market_prices"
    research_mode: QuantMode = QuantMode.BASIC
    wealth_start: PositiveFloat = 1.0


class CorrelationRequest(TimeBoundRequest):
    left_instrument_id: NonEmptyStr
    right_instrument_id: NonEmptyStr
    view_id: NonEmptyStr = "market_prices"
    research_mode: QuantMode = QuantMode.BASIC
    method: CorrelationMethod = CorrelationMethod.PEARSON
    return_kind: ReturnKind = ReturnKind.SIMPLE
    min_observations: Annotated[int, Field(ge=3, le=100000)] = 3
    bootstrap_samples: Annotated[int, Field(ge=0, le=2000)] = 0
    bootstrap_confidence: Annotated[float, Field(gt=0.5, lt=1.0)] = 0.95
    block_length: PositiveInt = 5

    @model_validator(mode="after")
    def different_instruments(self) -> "CorrelationRequest":
        if self.left_instrument_id == self.right_instrument_id:
            raise ValueError("left and right instruments must differ")
        return self


class EntropyRequest(TimeBoundRequest):
    instrument_id: NonEmptyStr
    view_id: NonEmptyStr = "market_prices"
    research_mode: QuantMode = QuantMode.BASIC
    method: EntropyMethod = EntropyMethod.SHANNON
    input_return_kind: ReturnKind = ReturnKind.SIMPLE
    binning_policy: BinningPolicy = BinningPolicy.EQUAL_WIDTH
    bins: Annotated[int, Field(ge=2, le=64)] = 8
    fixed_edges: tuple[float, ...] = ()
    embedding_dimension: Annotated[int, Field(ge=2, le=7)] = 3
    delay: Annotated[int, Field(ge=1, le=10)] = 1
    normalize: bool = True
    bootstrap_samples: Annotated[int, Field(ge=0, le=1000)] = 0
    bootstrap_confidence: Annotated[float, Field(gt=0.5, lt=1.0)] = 0.95
    block_length: PositiveInt = 5

    @model_validator(mode="after")
    def fixed_edges_consistent(self) -> "EntropyRequest":
        if self.binning_policy is BinningPolicy.FIXED_EDGES:
            if len(self.fixed_edges) < 3:
                raise ValueError("FIXED_EDGES requires at least three ordered edges")
            if tuple(sorted(set(self.fixed_edges))) != self.fixed_edges:
                raise ValueError("fixed_edges must be unique and sorted")
        elif self.fixed_edges:
            raise ValueError("fixed_edges are allowed only with FIXED_EDGES")
        return self


class EventWindowRequest(ContractModel):
    event_id: NonEmptyStr
    instrument_id: NonEmptyStr
    event_view_id: NonEmptyStr = "events"
    market_view_id: NonEmptyStr = "market_prices"
    benchmark_id: str | None = None
    benchmark_view_id: NonEmptyStr = "market_prices"
    research_mode: QuantMode = QuantMode.BASIC
    adjustment: EventAdjustment = EventAdjustment.NONE
    pre_window: NonNegativeInt = 1
    post_window: NonNegativeInt = 1
    return_kind: ReturnKind = ReturnKind.SIMPLE
    placebo_offsets: tuple[int, ...] = ()

    @model_validator(mode="after")
    def benchmark_required_for_adjustment(self) -> "EventWindowRequest":
        if self.adjustment is EventAdjustment.BENCHMARK and not self.benchmark_id:
            raise ValueError("benchmark_id is required for BENCHMARK adjustment")
        if len(set(self.placebo_offsets)) != len(self.placebo_offsets):
            raise ValueError("placebo_offsets must be unique")
        return self


class QuadraticExposure(ContractModel):
    left_factor: NonEmptyStr
    right_factor: NonEmptyStr
    coefficient: float


class ScenarioShockRequest(ContractModel):
    scenario_id: NonEmptyStr
    research_mode: QuantMode = QuantMode.BASIC
    baseline_value: float = 0.0
    factor_shocks: dict[NonEmptyStr, float]
    linear_exposures: dict[NonEmptyStr, float]
    quadratic_exposures: tuple[QuadraticExposure, ...] = ()
    sensitivity_multipliers: tuple[PositiveFloat, ...] = (0.5, 1.0, 1.5)

    @model_validator(mode="after")
    def factors_are_declared(self) -> "ScenarioShockRequest":
        factors = set(self.factor_shocks)
        if not factors:
            raise ValueError("factor_shocks cannot be empty")
        undeclared = set(self.linear_exposures) - factors
        for term in self.quadratic_exposures:
            undeclared.update({term.left_factor, term.right_factor} - factors)
        if undeclared:
            raise ValueError(f"exposures reference undeclared factors: {sorted(undeclared)}")
        if tuple(sorted(set(self.sensitivity_multipliers))) != self.sensitivity_multipliers:
            raise ValueError("sensitivity_multipliers must be unique and sorted")
        return self

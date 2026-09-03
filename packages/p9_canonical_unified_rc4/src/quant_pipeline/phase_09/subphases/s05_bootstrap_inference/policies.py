from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from .contracts import (
    BootstrapMethod,
    ConfidenceIntervalMethod,
    FiniteFloat,
    NonEmptyStr,
    PositiveInt,
    Probability,
    StrictModel,
)


class DependencePolicy(StrictModel):
    minimum_observations: PositiveInt = 40
    maximum_lag: PositiveInt = 20
    portmanteau_lags: tuple[PositiveInt, ...] = (5, 10, 20)
    significance_level: Probability = 0.05
    irregularity_tolerance_seconds: FiniteFloat = Field(default=0.0, ge=0)
    cross_sectional_high_correlation: Probability = 0.75

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if not 0.0 < self.significance_level < 1.0:
            raise ValueError("significance_level must be strictly between 0 and 1")
        if any(lag > self.maximum_lag for lag in self.portmanteau_lags):
            raise ValueError("portmanteau_lags must not exceed maximum_lag")
        return self


class BlockLengthPolicy(StrictModel):
    minimum_block_length: PositiveInt = 1
    maximum_fraction: Probability = 1.0 / 3.0
    fallback_dependence_multiplier: FiniteFloat = Field(default=2.0, ge=1.0)
    joint_aggregation: NonEmptyStr = "MAX"

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if not 0.0 < self.maximum_fraction <= 0.5:
            raise ValueError("maximum_fraction must be in (0, 0.5]")
        if self.joint_aggregation not in {"MAX", "MEDIAN"}:
            raise ValueError("joint_aggregation must be MAX or MEDIAN")
        return self


class BootstrapPolicy(StrictModel):
    method: BootstrapMethod = BootstrapMethod.STATIONARY
    replicate_count: PositiveInt = 1000
    materialize_indices: bool = True
    maximum_materialized_elements: PositiveInt = 20_000_000


class HierarchicalBootstrapPolicy(StrictModel):
    minimum_regime_coverage: Probability = 0.5
    covariance_distance_warning: FiniteFloat = Field(default=1.0, ge=0)
    record_replicate_diagnostics: PositiveInt = 100


class TradeResamplingPolicy(StrictModel):
    replicate_count: PositiveInt = 1000
    cluster_block_length: PositiveInt = 1
    minimum_trade_count: PositiveInt = 10
    concentration_warning_hhi: Probability = 0.25


class MetricDistributionPolicy(StrictModel):
    interval_method: ConfidenceIntervalMethod = ConfidenceIntervalMethod.PERCENTILE
    confidence_level: Probability = 0.95
    worst_quantile: Probability = 0.05
    invalid_replicate_limit: Probability = 0.20

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be strictly between 0 and 1")
        if not 0.0 < self.worst_quantile < 0.5:
            raise ValueError("worst_quantile must be between 0 and 0.5")
        return self


class SharpeInferencePolicy(StrictModel):
    benchmark_annualized_sharpe: FiniteFloat = 0.0
    confidence_level: Probability = 0.95
    autocorrelation_lags: PositiveInt = 20
    minimum_observations: PositiveInt = 30
    effective_trial_method: NonEmptyStr = "EIGEN_PARTICIPATION_RATIO"

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be strictly between 0 and 1")
        if self.effective_trial_method not in {
            "EIGEN_PARTICIPATION_RATIO",
            "ECONOMIC_CLUSTER_COUNT",
            "MINIMUM_OF_BOTH",
        }:
            raise ValueError("unsupported effective_trial_method")
        return self


class MultipleTestingPolicy(StrictModel):
    cscv_slices: PositiveInt = 8
    maximum_cscv_combinations: PositiveInt = 5000
    reality_check_replicates: PositiveInt = 1000
    reality_check_block_length: PositiveInt = 5
    significance_level: Probability = 0.05

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.cscv_slices < 4 or self.cscv_slices % 2 != 0:
            raise ValueError("cscv_slices must be even and at least 4")
        if not 0.0 < self.significance_level < 1.0:
            raise ValueError("significance_level must be strictly between 0 and 1")
        return self


class QualificationThresholdPolicy(StrictModel):
    minimum_dsr: Probability = 0.95
    maximum_pbo: Probability = 0.20
    minimum_bootstrap_probability_above_threshold: Probability = 0.80
    minimum_worst_fold_score: FiniteFloat = 0.0
    maximum_reality_check_pvalue: Probability = 0.10
    minimum_rank_stability: Probability = 0.50

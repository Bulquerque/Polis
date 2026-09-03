from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quant_pipeline.phase_09.contracts.integrity import payload_sha256 as boundary_payload_sha256

HEX64 = r"^[a-f0-9]{64}$"
NonEmptyStr = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(ge=1)]


class StrictModel(BaseModel):
    """Strict and immutable boundary model."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        populate_by_name=True,
    )


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def canonical_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()




class UpstreamBacktestMetricsReference(StrictModel):
    contract_name: NonEmptyStr = "P9_S4_TO_S5_EVIDENCE_V2"
    contract_version: NonEmptyStr = "2.0.0"
    canonicalization_version: NonEmptyStr = "P9-C14N-JSON-1"
    bundle_id: NonEmptyStr
    bundle_sha256: Annotated[str, Field(pattern=HEX64)]
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    configuration_id: NonEmptyStr
    metric_panel_id: NonEmptyStr
    metric_panel_sha256: Annotated[str, Field(pattern=HEX64)]
    quality_receipt_sha256: Annotated[str, Field(pattern=HEX64)]
    statistical_input_sha256: Annotated[str, Field(pattern=HEX64)]
    consumer_receipt_sha256: Annotated[str, Field(pattern=HEX64)]
    boundary_sha256: Annotated[str, Field(pattern=HEX64)]

    @model_validator(mode="after")
    def validate_boundary_hash(self) -> "UpstreamBacktestMetricsReference":
        expected = boundary_payload_sha256(
            self.model_dump(mode="python", exclude={"boundary_sha256"})
        )
        if expected != self.boundary_sha256:
            raise ValueError("S4-S5 boundary reference hash mismatch")
        return self

class GrossNet(StrEnum):
    GROSS = "GROSS"
    NET = "NET"


class TrialState(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EARLY_STOPPED = "EARLY_STOPPED"
    ABANDONED = "ABANDONED"


class BootstrapMethod(StrEnum):
    MOVING = "MOVING"
    CIRCULAR = "CIRCULAR"
    STATIONARY = "STATIONARY"


class ConfidenceIntervalMethod(StrEnum):
    PERCENTILE = "PERCENTILE"
    BASIC = "BASIC"


class MetricName(StrEnum):
    ANNUALIZED_RETURN = "ANNUALIZED_RETURN"
    VOLATILITY = "VOLATILITY"
    SHARPE = "SHARPE"
    CUMULATIVE_RETURN = "CUMULATIVE_RETURN"
    CAGR = "CAGR"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    SORTINO = "SORTINO"
    CALMAR = "CALMAR"
    EXPECTED_SHORTFALL = "EXPECTED_SHORTFALL"
    ALPHA = "ALPHA"
    BETA = "BETA"
    INFORMATION_RATIO = "INFORMATION_RATIO"
    COMPETITION_SCORE = "COMPETITION_SCORE"


class SamplingUnit(StrEnum):
    TIME_BLOCK = "TIME_BLOCK"
    HIERARCHICAL_TIME_CROSS_SECTION = "HIERARCHICAL_TIME_CROSS_SECTION"
    TRADE_EPISODE_CLUSTER = "TRADE_EPISODE_CLUSTER"


class S5State(StrEnum):
    SUCCESS = "SUCCESS"
    QUALIFIED = "QUALIFIED"
    QUALIFIED_WITH_LIMITATIONS = "QUALIFIED_WITH_LIMITATIONS"
    PARTIAL_METRIC_COVERAGE = "PARTIAL_METRIC_COVERAGE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    INSUFFICIENT_VALID_REPLICATES = "INSUFFICIENT_VALID_REPLICATES"
    IRREGULAR_TIME_UNSUPPORTED = "IRREGULAR_TIME_UNSUPPORTED"
    TRIAL_FAMILY_INCOMPLETE = "TRIAL_FAMILY_INCOMPLETE"
    EFFECTIVE_TRIAL_COUNT_UNRESOLVED = "EFFECTIVE_TRIAL_COUNT_UNRESOLVED"
    METRIC_VERSION_MISMATCH = "METRIC_VERSION_MISMATCH"
    ROBUST = "ROBUST"
    PROVISIONALLY_ROBUST = "PROVISIONALLY_ROBUST"
    FRAGILE = "FRAGILE"
    BACKTEST_OVERFIT_RISK = "BACKTEST_OVERFIT_RISK"
    REGIME_DEPENDENT = "REGIME_DEPENDENT"
    SELECTION_BIAS_UNRESOLVED = "SELECTION_BIAS_UNRESOLVED"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID = "INVALID"


class RunContext(StrictModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    experiment_id: NonEmptyStr
    configuration_id: NonEmptyStr
    decision_time: datetime
    available_at: datetime
    code_sha256: Annotated[str, Field(pattern=HEX64)]
    data_sha256: Annotated[str, Field(pattern=HEX64)]

    @field_validator("decision_time", "available_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)

    @model_validator(mode="after")
    def enforce_point_in_time(self) -> Self:
        if self.available_at > self.decision_time:
            raise ValueError("available_at must not exceed decision_time")
        return self


class TimeSeriesPanel(StrictModel):
    panel_id: NonEmptyStr
    timestamps: tuple[datetime, ...]
    series_ids: tuple[NonEmptyStr, ...]
    values: tuple[tuple[FiniteFloat, ...], ...]
    periods_per_year: FiniteFloat = Field(gt=0)
    gross_or_net: GrossNet
    benchmark_series_id: NonEmptyStr | None = None
    risk_free_series_id: NonEmptyStr | None = None
    fold_ids: tuple[NonEmptyStr, ...] | None = None
    regime_ids: tuple[NonEmptyStr, ...] | None = None
    metric_registry_version: NonEmptyStr = "1.0.0"

    @field_validator("timestamps")
    @classmethod
    def normalize_timestamps(cls, values: tuple[datetime, ...]) -> tuple[datetime, ...]:
        return tuple(utc_datetime(value) for value in values)

    def _validate_dimensions(self, n_rows: int, n_cols: int) -> None:
        if n_rows < 2:
            raise ValueError("at least two observations are required")
        if n_cols < 1:
            raise ValueError("at least one series is required")
        if len(set(self.series_ids)) != n_cols:
            raise ValueError("series_ids must be unique")
        if len(self.values) != n_rows:
            raise ValueError("values row count must match timestamps")
        if any(len(row) != n_cols for row in self.values):
            raise ValueError("values must be rectangular")

    def _validate_time_axes(self, n_rows: int) -> None:
        if any(right <= left for left, right in zip(self.timestamps, self.timestamps[1:])):
            raise ValueError("timestamps must be strictly increasing")
        if self.fold_ids is not None and len(self.fold_ids) != n_rows:
            raise ValueError("fold_ids length must match timestamps")
        if self.regime_ids is not None and len(self.regime_ids) != n_rows:
            raise ValueError("regime_ids length must match timestamps")

    def _validate_optional_series_ids(self) -> None:
        for optional_id in (self.benchmark_series_id, self.risk_free_series_id):
            if optional_id is not None and optional_id not in self.series_ids:
                raise ValueError(f"unknown series id: {optional_id}")

    @model_validator(mode="after")
    def validate_panel(self) -> Self:
        n_rows = len(self.timestamps)
        n_cols = len(self.series_ids)
        self._validate_dimensions(n_rows, n_cols)
        self._validate_time_axes(n_rows)
        self._validate_optional_series_ids()
        return self


class TradeEpisode(StrictModel):
    trade_id: NonEmptyStr
    candidate_id: NonEmptyStr
    opened_at: datetime
    closed_at: datetime
    instrument_ids: tuple[NonEmptyStr, ...]
    gross_pnl: FiniteFloat
    net_pnl: FiniteFloat
    total_cost: FiniteFloat = Field(ge=0)

    @field_validator("opened_at", "closed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)

    @model_validator(mode="after")
    def validate_episode(self) -> Self:
        if self.closed_at < self.opened_at:
            raise ValueError("closed_at must not precede opened_at")
        if not self.instrument_ids:
            raise ValueError("instrument_ids must not be empty")
        if len(set(self.instrument_ids)) != len(self.instrument_ids):
            raise ValueError("instrument_ids must be unique")
        return self


class TradeEpisodePanel(StrictModel):
    panel_id: NonEmptyStr
    episodes: tuple[TradeEpisode, ...]

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        ids = [episode.trade_id for episode in self.episodes]
        if len(set(ids)) != len(ids):
            raise ValueError("trade_ids must be unique")
        return self


class TrialPerformancePanel(StrictModel):
    panel_id: NonEmptyStr
    timestamps: tuple[datetime, ...]
    trial_ids: tuple[NonEmptyStr, ...]
    configuration_ids: tuple[NonEmptyStr, ...]
    states: tuple[TrialState, ...]
    performance_values: tuple[tuple[FiniteFloat, ...], ...]
    family_complete: bool
    economic_cluster_ids: tuple[NonEmptyStr, ...] | None = None

    @field_validator("timestamps")
    @classmethod
    def normalize_timestamps(cls, values: tuple[datetime, ...]) -> tuple[datetime, ...]:
        return tuple(utc_datetime(value) for value in values)

    @model_validator(mode="after")
    def validate_panel(self) -> Self:
        n_trials = len(self.trial_ids)
        if n_trials < 1:
            raise ValueError("at least one trial is required")
        if len(set(self.trial_ids)) != n_trials:
            raise ValueError("trial_ids must be unique")
        if len(self.configuration_ids) != n_trials or len(self.states) != n_trials:
            raise ValueError("trial metadata lengths must match trial_ids")
        if self.economic_cluster_ids is not None and len(self.economic_cluster_ids) != n_trials:
            raise ValueError("economic_cluster_ids length must match trial_ids")
        if len(self.performance_values) != len(self.timestamps):
            raise ValueError("performance row count must match timestamps")
        if any(len(row) != n_trials for row in self.performance_values):
            raise ValueError("performance_values must be rectangular")
        return self


class FoldScore(StrictModel):
    fold_id: NonEmptyStr
    score: FiniteFloat
    observation_count: PositiveInt


class FoldScorePanel(StrictModel):
    configuration_id: NonEmptyStr
    scores: tuple[FoldScore, ...]

    @model_validator(mode="after")
    def validate_folds(self) -> Self:
        ids = [score.fold_id for score in self.scores]
        if len(set(ids)) != len(ids):
            raise ValueError("fold_ids must be unique")
        return self


class MetricDefinition(StrictModel):
    metric_id: NonEmptyStr
    metric_name: MetricName
    target_series_id: NonEmptyStr
    metric_version: NonEmptyStr = "1.0.0"
    threshold: FiniteFloat | None = None
    confidence_level: Probability = 0.95
    tail_probability: Probability = 0.05
    minimum_valid_replicates: PositiveInt = 100
    benchmark_series_id: NonEmptyStr | None = None
    risk_free_series_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_probabilities(self) -> Self:
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be strictly between 0 and 1")
        if not 0.0 < self.tail_probability < 0.5:
            raise ValueError("tail_probability must be between 0 and 0.5")
        return self


class SeedPolicy(StrictModel):
    root_entropy: Annotated[int, Field(ge=0)]
    algorithm: NonEmptyStr = "PCG64"
    derivation_version: NonEmptyStr = "seedsequence-v1"


class EvidenceReference(StrictModel):
    evidence_id: NonEmptyStr
    evidence_type: NonEmptyStr
    content_sha256: Annotated[str, Field(pattern=HEX64)]


class ModuleReceipt(StrictModel):
    module_id: NonEmptyStr
    status: S5State
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    output_sha256: Annotated[str, Field(pattern=HEX64)]
    started_at: datetime
    completed_at: datetime

    @field_validator("started_at", "completed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


def ensure_finite_array(values: object, *, name: str) -> None:
    """Raise if nested numeric values contain NaN or infinity."""

    def walk(value: object) -> None:
        if isinstance(value, (tuple, list)):
            for item in value:
                walk(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{name} contains a non-finite value")

    walk(values)

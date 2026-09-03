from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, model_validator

from .contracts import (
    BootstrapMethod,
    EvidenceReference,
    FiniteFloat,
    FoldScorePanel,
    MetricDefinition,
    MetricName,
    ModuleReceipt,
    NonEmptyStr,
    PositiveInt,
    Probability,
    RunContext,
    S5State,
    SamplingUnit,
    SeedPolicy,
    StrictModel,
    TimeSeriesPanel,
    TradeEpisodePanel,
    TrialPerformancePanel,
    UpstreamBacktestMetricsReference,
    content_sha256,
)
from .policies import (
    BlockLengthPolicy,
    BootstrapPolicy,
    DependencePolicy,
    HierarchicalBootstrapPolicy,
    MetricDistributionPolicy,
    MultipleTestingPolicy,
    QualificationThresholdPolicy,
    SharpeInferencePolicy,
    TradeResamplingPolicy,
)


class LjungBoxDiagnostic(StrictModel):
    lag: PositiveInt
    statistic: FiniteFloat = Field(ge=0)
    pvalue: Probability


class SeriesDependenceDiagnostic(StrictModel):
    series_id: NonEmptyStr
    observation_count: PositiveInt
    effective_sample_size: FiniteFloat = Field(gt=0)
    dependence_horizon: PositiveInt
    autocorrelations: tuple[FiniteFloat, ...]
    ljung_box: tuple[LjungBoxDiagnostic, ...]
    variance: FiniteFloat = Field(ge=0)


class TradeOverlapDiagnostic(StrictModel):
    trade_count: int = Field(ge=0)
    cluster_count: int = Field(ge=0)
    maximum_concurrency: int = Field(ge=0)
    overlap_fraction: Probability
    cluster_ids_by_trade: tuple[tuple[NonEmptyStr, PositiveInt], ...]


class DependenceDiagnosticsRequest(StrictModel):
    context: RunContext
    series: TimeSeriesPanel
    trades: TradeEpisodePanel | None = None
    policy: DependencePolicy = DependencePolicy()


class DependenceDiagnosticsResult(StrictModel):
    status: S5State
    series_diagnostics: tuple[SeriesDependenceDiagnostic, ...]
    cross_sectional_correlation: tuple[tuple[FiniteFloat, ...], ...]
    average_absolute_cross_correlation: Probability
    trade_overlap: TradeOverlapDiagnostic | None
    recommended_sampling_units: tuple[SamplingUnit, ...]
    regular_interval_seconds: FiniteFloat | None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()


class BlockLengthEstimate(StrictModel):
    series_id: NonEmptyStr
    stationary_raw: FiniteFloat = Field(ge=0)
    circular_raw: FiniteFloat = Field(ge=0)
    moving_selected: PositiveInt
    stationary_selected: PositiveInt
    circular_selected: PositiveInt
    dependence_horizon: PositiveInt
    used_fallback: bool


class BlockLengthSelectionRequest(StrictModel):
    context: RunContext
    series: TimeSeriesPanel
    diagnostics: DependenceDiagnosticsResult
    policy: BlockLengthPolicy = BlockLengthPolicy()


class BlockLengthSelectionResult(StrictModel):
    status: S5State
    estimates: tuple[BlockLengthEstimate, ...]
    joint_moving_block_length: PositiveInt
    joint_stationary_block_length: PositiveInt
    joint_circular_block_length: PositiveInt
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class BootstrapIndexManifest(StrictModel):
    manifest_id: NonEmptyStr
    method: BootstrapMethod
    observation_count: PositiveInt
    replicate_count: PositiveInt
    block_length: PositiveInt
    seed_lineage: NonEmptyStr
    indices: tuple[tuple[int, ...], ...]
    replicate_sha256: tuple[Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")], ...]
    manifest_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if len(self.indices) != self.replicate_count:
            raise ValueError("indices length must match replicate_count")
        if len(self.replicate_sha256) != self.replicate_count:
            raise ValueError("replicate_sha256 length must match replicate_count")
        if any(len(row) != self.observation_count for row in self.indices):
            raise ValueError("each replicate must contain observation_count indices")
        if any(
            index < 0 or index >= self.observation_count
            for row in self.indices
            for index in row
        ):
            raise ValueError("bootstrap index outside observation range")
        return self


class BlockBootstrapRequest(StrictModel):
    context: RunContext
    observation_count: PositiveInt
    block_length: PositiveInt
    seed_policy: SeedPolicy
    policy: BootstrapPolicy = BootstrapPolicy()


class BlockBootstrapResult(StrictModel):
    status: S5State
    manifest: BootstrapIndexManifest | None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class ReplicateCovarianceDiagnostic(StrictModel):
    replicate_id: PositiveInt
    covariance_distance: FiniteFloat = Field(ge=0)
    regime_coverage: Probability | None = None


class HierarchicalBootstrapRequest(StrictModel):
    context: RunContext
    series: TimeSeriesPanel
    indices: BootstrapIndexManifest
    policy: HierarchicalBootstrapPolicy = HierarchicalBootstrapPolicy()


class HierarchicalBootstrapResult(StrictModel):
    status: S5State
    original_covariance: tuple[tuple[FiniteFloat, ...], ...]
    diagnostics: tuple[ReplicateCovarianceDiagnostic, ...]
    average_covariance_distance: FiniteFloat = Field(ge=0)
    minimum_regime_coverage: Probability | None = None
    joint_resampling_verified: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class TradeCluster(StrictModel):
    cluster_id: PositiveInt
    trade_ids: tuple[NonEmptyStr, ...]
    opened_at: datetime
    closed_at: datetime
    gross_pnl: FiniteFloat
    net_pnl: FiniteFloat
    total_cost: FiniteFloat = Field(ge=0)


class TradeReplicateSummary(StrictModel):
    replicate_id: PositiveInt
    sampled_cluster_ids: tuple[PositiveInt, ...]
    trade_count: int = Field(ge=0)
    gross_pnl: FiniteFloat
    net_pnl: FiniteFloat
    total_cost: FiniteFloat = Field(ge=0)


class TradeResamplingRequest(StrictModel):
    context: RunContext
    trades: TradeEpisodePanel
    seed_policy: SeedPolicy
    policy: TradeResamplingPolicy = TradeResamplingPolicy()


class TradeResamplingResult(StrictModel):
    status: S5State
    clusters: tuple[TradeCluster, ...]
    replicates: tuple[TradeReplicateSummary, ...]
    pnl_hhi: Probability
    cost_hhi: Probability
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class MetricEstimate(StrictModel):
    metric_id: NonEmptyStr
    metric_name: MetricName
    observed_value: FiniteFloat | None
    bootstrap_mean: FiniteFloat | None
    bootstrap_median: FiniteFloat | None
    standard_error: FiniteFloat | None = Field(default=None, ge=0)
    confidence_interval_low: FiniteFloat | None
    confidence_interval_high: FiniteFloat | None
    lower_confidence_bound: FiniteFloat | None
    worst_quantile: FiniteFloat | None
    probability_above_threshold: Probability | None
    valid_replicates: int = Field(ge=0)
    invalid_replicates: int = Field(ge=0)
    status: S5State
    reason_codes: tuple[NonEmptyStr, ...] = ()


class MetricDistributionRequest(StrictModel):
    context: RunContext
    series: TimeSeriesPanel
    indices: BootstrapIndexManifest
    metric_definitions: tuple[MetricDefinition, ...]
    policy: MetricDistributionPolicy = MetricDistributionPolicy()


class MetricDistributionResult(StrictModel):
    status: S5State
    metric_registry_version: NonEmptyStr
    estimates: tuple[MetricEstimate, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class SharpeInferenceRequest(StrictModel):
    context: RunContext
    series: TimeSeriesPanel
    target_series_id: NonEmptyStr
    target_configuration_id: NonEmptyStr | None = None
    trial_performance: TrialPerformancePanel
    metric_distributions: MetricDistributionResult
    policy: SharpeInferencePolicy = SharpeInferencePolicy()

    @model_validator(mode="after")
    def validate_target_binding(self) -> Self:
        if self.target_configuration_id is None:
            return self
        if self.target_configuration_id != self.context.configuration_id:
            raise ValueError("Sharpe target configuration differs from run context")
        if self.target_configuration_id not in self.trial_performance.configuration_ids:
            raise ValueError("Sharpe target configuration is absent from trial family")
        return self


class SharpeInferenceResult(StrictModel):
    status: S5State
    target_series_id: NonEmptyStr
    target_configuration_id: NonEmptyStr | None = None
    observation_count: PositiveInt
    observed_annualized_sharpe: FiniteFloat | None
    autocorrelation_adjusted_annualized_sharpe: FiniteFloat | None
    probabilistic_sharpe_ratio: Probability | None
    deflated_sharpe_ratio: Probability | None
    benchmark_annualized_sharpe: FiniteFloat
    effective_trial_count: FiniteFloat | None = Field(default=None, ge=1)
    expected_max_annualized_sharpe: FiniteFloat | None
    minimum_track_record_observations: FiniteFloat | None = Field(default=None, ge=1)
    skewness: FiniteFloat | None
    pearson_kurtosis: FiniteFloat | None = Field(default=None, ge=1)
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class PBOResult(StrictModel):
    applicable: bool
    pbo: Probability | None
    combination_count: int = Field(ge=0)
    logits: tuple[FiniteFloat, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()


class MultipleTestingResult(StrictModel):
    applicable: bool
    reality_check_statistic: FiniteFloat | None
    reality_check_pvalue: Probability | None
    tested_trial_count: int = Field(ge=0)
    reason_codes: tuple[NonEmptyStr, ...] = ()


class RobustnessQualificationRequest(StrictModel):
    context: RunContext
    target_configuration_id: NonEmptyStr
    target_metric_id: NonEmptyStr
    trial_performance: TrialPerformancePanel
    fold_scores: FoldScorePanel
    metric_distributions: MetricDistributionResult
    sharpe_inference: SharpeInferenceResult
    seed_policy: SeedPolicy
    multiple_testing_policy: MultipleTestingPolicy = MultipleTestingPolicy()
    threshold_policy: QualificationThresholdPolicy = QualificationThresholdPolicy()




class BacktestRobustnessQualificationReport(StrictModel):
    status: S5State
    target_configuration_id: NonEmptyStr
    target_metric_id: NonEmptyStr
    pbo: PBOResult
    multiple_testing: MultipleTestingResult
    dsr: Probability | None
    bootstrap_lower_bound: FiniteFloat | None
    probability_above_threshold: Probability | None
    worst_fold_score: FiniteFloat | None
    rank_stability: Probability | None
    favorable_evidence: tuple[NonEmptyStr, ...]
    contrary_evidence: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    limitations: tuple[NonEmptyStr, ...]


class S5RunRequest(StrictModel):
    dependence: DependenceDiagnosticsRequest
    upstream_metrics: UpstreamBacktestMetricsReference | None = None
    block_length_policy: BlockLengthPolicy = BlockLengthPolicy()
    bootstrap_policy: BootstrapPolicy = BootstrapPolicy()
    seed_policy: SeedPolicy
    hierarchical_policy: HierarchicalBootstrapPolicy = HierarchicalBootstrapPolicy()
    trade_policy: TradeResamplingPolicy = TradeResamplingPolicy()
    metric_definitions: tuple[MetricDefinition, ...]
    metric_policy: MetricDistributionPolicy = MetricDistributionPolicy()
    sharpe_target_series_id: NonEmptyStr
    trial_performance: TrialPerformancePanel
    sharpe_policy: SharpeInferencePolicy = SharpeInferencePolicy()
    fold_scores: FoldScorePanel
    target_metric_id: NonEmptyStr
    multiple_testing_policy: MultipleTestingPolicy = MultipleTestingPolicy()
    qualification_policy: QualificationThresholdPolicy = QualificationThresholdPolicy()


class S5OutputBundle(StrictModel):
    bundle_id: NonEmptyStr
    context: RunContext
    upstream_metrics: UpstreamBacktestMetricsReference | None = None
    dependence: DependenceDiagnosticsResult
    block_lengths: BlockLengthSelectionResult
    bootstrap: BlockBootstrapResult
    hierarchical: HierarchicalBootstrapResult
    trade_resampling: TradeResamplingResult | None
    metric_distributions: MetricDistributionResult
    sharpe_inference: SharpeInferenceResult
    qualification: BacktestRobustnessQualificationReport
    module_receipts: tuple[ModuleReceipt, ...]
    bundle_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    def hash_preimage(self) -> dict[str, object]:
        return {
            "context": self.context.model_dump(mode="json"),
            "upstream_metrics": (
                None
                if self.upstream_metrics is None
                else self.upstream_metrics.model_dump(mode="json")
            ),
            "dependence_sha256": content_sha256(self.dependence),
            "block_lengths_sha256": content_sha256(self.block_lengths),
            "bootstrap_sha256": content_sha256(self.bootstrap),
            "hierarchical_sha256": content_sha256(self.hierarchical),
            "trade_resampling_sha256": content_sha256(self.trade_resampling),
            "metric_distributions_sha256": content_sha256(self.metric_distributions),
            "sharpe_inference_sha256": content_sha256(self.sharpe_inference),
            "qualification_sha256": content_sha256(self.qualification),
            "receipt_sha256": [content_sha256(receipt) for receipt in self.module_receipts],
        }

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        expected_modules = {f"P9.S5.M0{i}" for i in range(1, 9)}
        actual_modules = {receipt.module_id for receipt in self.module_receipts}
        if actual_modules != expected_modules or len(self.module_receipts) != 8:
            raise ValueError("module receipts must cover P9.S5.M01-M08 exactly")
        if self.upstream_metrics is not None:
            if (
                self.upstream_metrics.run_id != self.context.run_id
                or self.upstream_metrics.cycle_id != self.context.cycle_id
                or self.upstream_metrics.configuration_id != self.context.configuration_id
            ):
                raise ValueError("S5 upstream metrics identity differs from run context")
        if content_sha256(self.hash_preimage()) != self.bundle_sha256:
            raise ValueError("S5 bundle hash mismatch")
        return self

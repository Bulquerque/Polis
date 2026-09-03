"""Boundary models and clock for the P9.S7 orchestration shell."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from pydantic import Field, model_validator

from .canonical import payload_sha256
from .contracts import (
    BundleHeader,
    IntegrityEnvelope,
    ModuleExecutionReceipt,
    NonEmptyStr,
    S7MaterializationReceipt,
    S7SubphaseExecutionReceipt,
    S7UpstreamReferences,
    StrictModel,
)
from .m01_prequential import (
    OutcomeEvent,
    PredictionEvent,
    PrequentialRecord,
    PrequentialStreamResult,
)
from .m02_shadow import (
    PolicyExecutionOutput,
    PolicySpecification,
    ShadowComparabilityReceipt,
    ShadowExecutionPlan,
)
from .m03_scoring import OnlineScoringResult, ScoringPolicy
from .m04_conformal import ConformalMonitoringResult, ConformalObservation, ConformalPolicy
from .m05_drift import DriftChannelPolicy, DriftObservation, DriftQualificationResult
from .m06_sequential import PairedLossObservation, SequentialComparisonPolicy, SequentialModelSet
from .m07_rollback import (
    LiveExecutionMetrics,
    RollbackPolicy,
    RollbackRecommendation,
    StressCapacityQualification,
)
from .m08_reality_gap import RealityGapPolicy, RealityGapResult, StageExecutionRecord


_MATERIALIZED_INPUT_DEFAULTS: dict[str, object] = {
    "existing_records": (),
    "allowed_policy_ids": None,
    "conformal_observations": (),
    "minimum_confirming_drift_channels": 2,
    "offline_model_set": None,
}


_MATERIALIZED_INPUT_FIELDS = (
    "predictions",
    "outcomes",
    "existing_records",
    "champion_policy",
    "challenger_policies",
    "policy_execution_outputs",
    "allowed_policy_ids",
    "scoring_policy",
    "conformal_policy",
    "conformal_observations",
    "drift_observations",
    "drift_policies",
    "minimum_confirming_drift_channels",
    "paired_loss_observations",
    "sequential_comparison_policy",
    "offline_model_set",
    "live_execution_metrics",
    "stress_capacity_qualification",
    "rollback_policy",
    "stage_execution_records",
    "reality_gap_policy",
)


def materialized_inputs_sha256(values: Mapping[str, object]) -> str:
    materialized: dict[str, object] = {}
    for name in _MATERIALIZED_INPUT_FIELDS:
        if name in values:
            materialized[name] = values[name]
        elif name in _MATERIALIZED_INPUT_DEFAULTS:
            materialized[name] = _MATERIALIZED_INPUT_DEFAULTS[name]
        else:
            raise ValueError(f"missing required materialized S7 input: {name}")
    return payload_sha256(materialized)


def validate_materialization_receipt(request: "S7ExecutionRequest") -> None:
    expected_sources = (
        request.upstream.foundation_bundle.content_sha256,
        request.upstream.backtest_metrics_bundle.content_sha256,
        request.upstream.robustness_stress_bundle.content_sha256,
    )
    receipt = request.materialization_receipt
    if receipt.run_id != request.header.run_id or receipt.cycle_id != request.header.cycle_id:
        raise ValueError("materialization receipt run/cycle mismatch")
    if receipt.source_bundle_sha256s != expected_sources:
        raise ValueError("materialization receipt source bundle mismatch")
    observed = materialized_inputs_sha256(
        {name: getattr(request, name) for name in _MATERIALIZED_INPUT_FIELDS}
    )
    if receipt.materialized_payload_sha256 != observed:
        raise ValueError("materialized S7 input payload hash mismatch")


class S7ExecutionRequest(StrictModel):
    header: BundleHeader
    upstream: S7UpstreamReferences
    materialization_receipt: S7MaterializationReceipt
    predictions: tuple[PredictionEvent, ...]
    outcomes: tuple[OutcomeEvent, ...]
    existing_records: tuple[PrequentialRecord, ...] = ()
    champion_policy: PolicySpecification
    challenger_policies: tuple[PolicySpecification, ...]
    policy_execution_outputs: tuple[PolicyExecutionOutput, ...]
    allowed_policy_ids: frozenset[NonEmptyStr] | None = None
    scoring_policy: ScoringPolicy
    conformal_policy: ConformalPolicy
    conformal_observations: tuple[ConformalObservation, ...] = ()
    drift_observations: tuple[DriftObservation, ...]
    drift_policies: tuple[DriftChannelPolicy, ...]
    minimum_confirming_drift_channels: int = Field(default=2, ge=1)
    paired_loss_observations: tuple[PairedLossObservation, ...]
    sequential_comparison_policy: SequentialComparisonPolicy
    offline_model_set: frozenset[NonEmptyStr] | None = None
    live_execution_metrics: LiveExecutionMetrics
    stress_capacity_qualification: StressCapacityQualification
    rollback_policy: RollbackPolicy
    stage_execution_records: tuple[StageExecutionRecord, ...]
    reality_gap_policy: RealityGapPolicy

    @model_validator(mode="after")
    def validate_run_cycle(self) -> "S7ExecutionRequest":
        refs = (
            self.upstream.foundation_bundle,
            self.upstream.backtest_metrics_bundle,
            self.upstream.robustness_stress_bundle,
        )
        mismatched_scope = any(
            ref.run_id != self.header.run_id or ref.cycle_id != self.header.cycle_id
            for ref in refs
        )
        if mismatched_scope:
            raise ValueError("upstream run_id/cycle_id must match the S7 bundle header")
        validate_materialization_receipt(self)
        return self


class ProspectiveMonitoringPayload(StrictModel):
    header: BundleHeader
    upstream_bundle_sha256s: tuple[str, str, str]
    prequential_stream: PrequentialStreamResult
    shadow_plan: ShadowExecutionPlan
    shadow_comparability: ShadowComparabilityReceipt
    online_scoring: OnlineScoringResult
    conformal_monitoring: ConformalMonitoringResult
    drift_qualification: DriftQualificationResult
    sequential_model_set: SequentialModelSet
    rollback_recommendation: RollbackRecommendation
    reality_gap: RealityGapResult
    module_receipts: tuple[ModuleExecutionReceipt, ...]
    subphase_receipt: S7SubphaseExecutionReceipt
    limitations: tuple[NonEmptyStr, ...] = ()


class ProspectiveMonitoringBundle(StrictModel):
    payload: ProspectiveMonitoringPayload
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def verify_integrity(self) -> "ProspectiveMonitoringBundle":
        if payload_sha256(self.payload) != self.integrity.payload_sha256:
            raise ValueError("bundle integrity mismatch")
        return self


class Clock:
    """Small callable clock wrapper used by the imperative shell."""

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def __call__(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("clock must return UTC datetime")
        return value

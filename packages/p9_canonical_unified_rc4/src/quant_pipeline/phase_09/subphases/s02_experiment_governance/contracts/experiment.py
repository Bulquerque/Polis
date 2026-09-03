from __future__ import annotations

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.cohort import FrozenEvaluationCohort

from .base import (
    CapabilityId,
    CapabilityState,
    DatasetId,
    ExperimentId,
    ExperimentValidationState,
    MetricDirection,
    MetricId,
    ModuleId,
    NonEmptyStr,
    ReasonCode,
    SearchStrategy,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)


class MetricBinding(StrictModel):
    metric_id: MetricId
    metric_version: NonEmptyStr
    direction: MetricDirection
    minimum_observations: int = Field(ge=1)
    allowed_for_tuning: bool
    hard_guardrail_eligible: bool = False


class MetricRegistrySnapshot(StrictModel):
    registry_version: NonEmptyStr
    registry_sha256: Sha256Hex
    metrics: tuple[MetricBinding, ...]

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> "MetricRegistrySnapshot":
        ids = [metric.metric_id for metric in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("metric IDs must be unique")
        return self

    def metric(self, metric_id: str) -> MetricBinding | None:
        return next((metric for metric in self.metrics if metric.metric_id == metric_id), None)


class CapabilityBinding(StrictModel):
    capability_id: CapabilityId
    owner_module_id: ModuleId
    state: CapabilityState
    supported_strategy_ids: tuple[SearchStrategy, ...] = ()
    limitation: NonEmptyStr | None = None


class PhaseCapabilityRegistry(StrictModel):
    registry_version: NonEmptyStr
    registry_sha256: Sha256Hex
    capabilities: tuple[CapabilityBinding, ...]

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> "PhaseCapabilityRegistry":
        ids = [capability.capability_id for capability in self.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("capability IDs must be unique")
        return self

    def capability(self, capability_id: str) -> CapabilityBinding | None:
        return next(
            (
                capability
                for capability in self.capabilities
                if capability.capability_id == capability_id
            ),
            None,
        )


class TemporalEvaluationRequest(StrictModel):
    outer_fold_count: int = Field(ge=1, le=64)
    inner_fold_count: int = Field(ge=1, le=64)
    purge_required: bool = True
    embargo_required: bool = True
    final_holdout_required: bool = True


class ExperimentSpecification(StrictModel):
    experiment_id: ExperimentId
    created_at: UtcDateTime
    activated_at: UtcDateTime
    hypothesis: NonEmptyStr
    primary_metric_id: MetricId
    hard_guardrail_metric_ids: tuple[MetricId, ...]
    diagnostic_metric_ids: tuple[MetricId, ...] = ()
    target_module_ids: tuple[ModuleId, ...]
    required_capability_ids: tuple[CapabilityId, ...] = ()
    development_dataset_ids: tuple[DatasetId, ...]
    evaluation_dataset_ids: tuple[DatasetId, ...]
    final_holdout_dataset_ids: tuple[DatasetId, ...]
    search_strategy: SearchStrategy
    requested_max_configurations: int = Field(ge=1)
    requested_seed_count: int = Field(ge=1, le=128)
    temporal_evaluation: TemporalEvaluationRequest
    non_goals: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_structure(self) -> "ExperimentSpecification":
        if self.activated_at < self.created_at:
            raise ValueError("activated_at must be >= created_at")
        for field_name in (
            "hard_guardrail_metric_ids",
            "target_module_ids",
            "development_dataset_ids",
            "evaluation_dataset_ids",
            "final_holdout_dataset_ids",
        ):
            values = getattr(self, field_name)
            if not values:
                raise ValueError(f"{field_name} must not be empty")
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        all_metrics = (
            (self.primary_metric_id,)
            + self.hard_guardrail_metric_ids
            + self.diagnostic_metric_ids
        )
        if len(all_metrics) != len(set(all_metrics)):
            raise ValueError("primary, guardrail and diagnostic metrics must be disjoint")
        return self


class PromotionPolicyReference(StrictModel):
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    policy_sha256: Sha256Hex
    hard_guardrails_non_compensable: bool = True


class ValidatedExperimentSpecification(StrictModel):
    specification: ExperimentSpecification
    cohort_id: NonEmptyStr
    cohort_sha256: Sha256Hex
    metric_registry_sha256: Sha256Hex
    capability_registry_sha256: Sha256Hex
    promotion_policy: PromotionPolicyReference
    specification_sha256: Sha256Hex


class ExperimentValidationReport(StrictModel):
    state: ExperimentValidationState
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    checked_metric_ids: tuple[MetricId, ...] = ()
    checked_capability_ids: tuple[CapabilityId, ...] = ()
    checked_target_module_ids: tuple[ModuleId, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> "ExperimentValidationReport":
        blocking = {
            ExperimentValidationState.SPEC_INVALID,
            ExperimentValidationState.CAPABILITY_UNAVAILABLE,
            ExperimentValidationState.HOLDOUT_POLICY_INVALID,
        }
        if self.state in blocking and not self.reason_codes:
            raise ValueError("blocking experiment state requires reason codes")
        if self.state is ExperimentValidationState.SPEC_VALID and self.reason_codes:
            raise ValueError("SPEC_VALID cannot contain blocking reason codes")
        return self


class ExperimentValidationInput(StrictModel):
    specification: ExperimentSpecification
    frozen_cohort: FrozenEvaluationCohort
    metric_registry: MetricRegistrySnapshot
    capability_registry: PhaseCapabilityRegistry
    promotion_policy: PromotionPolicyReference


class ExperimentValidationOutcome(StrictModel):
    validated: ValidatedExperimentSpecification | None
    report: ExperimentValidationReport

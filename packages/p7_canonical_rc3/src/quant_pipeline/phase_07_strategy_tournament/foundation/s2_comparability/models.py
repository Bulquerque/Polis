"""Typed policies and record models for P7.S2."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

Version = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
Direction = Literal["MAXIMIZE", "MINIMIZE", "NEUTRAL"]
MissingnessPolicy = Literal["BLOCK", "ALLOW_UNAVAILABLE", "OMIT"]
TransformationPolicy = Literal["IDENTITY", "ABSOLUTE", "LOG1P_POSITIVE", "NEGATE"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class EligibilityPolicy(StrictModel):
    policy_id: str
    version: Version
    allowed_objective_families: tuple[str, ...]
    disabled_strategy_classes: tuple[str, ...] = ()
    required_sections: tuple[str, ...] = (
        "candidate",
        "legs",
        "payoffs",
        "scenario_evaluations",
        "risk",
        "cost_liquidity",
        "lineage",
        "market_snapshot",
        "generation_trace",
    )
    required_candidate_paths: tuple[str, ...] = (
        "candidate.candidate_id",
        "candidate.currency",
    )
    required_metric_paths_by_objective: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    defined_risk_required: bool = True
    require_maximum_loss_proven: bool = True
    min_scenario_count: int = Field(default=1, ge=0)
    max_snapshot_age_seconds: int = Field(default=86_400, ge=0)
    allowed_currencies: tuple[str, ...] = ()
    allowed_calendars: tuple[str, ...] = ()
    require_calendar_id: bool = False
    representative_only: bool = True
    feedback_mutable_parameters: tuple[str, ...] = (
        "min_scenario_count",
        "max_snapshot_age_seconds",
    )

    @field_validator("allowed_objective_families")
    @classmethod
    def nonempty_objectives(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("allowed objective families must be non-empty and unique")
        return value


class EligibilityPolicyRegistry(StrictModel):
    registry_id: str
    registry_version: Version
    active_policy_id: str
    policies: tuple[EligibilityPolicy, ...]

    @model_validator(mode="after")
    def active_policy_exists(self) -> "EligibilityPolicyRegistry":
        ids = [item.policy_id for item in self.policies]
        if len(ids) != len(set(ids)):
            raise ValueError("eligibility policy IDs must be unique")
        if self.active_policy_id not in ids:
            raise ValueError("active eligibility policy does not exist")
        return self

    def active(self) -> EligibilityPolicy:
        return next(item for item in self.policies if item.policy_id == self.active_policy_id)


class RiskBucket(StrictModel):
    bucket_id: str
    lower_inclusive: float = Field(ge=0)
    upper_exclusive: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_interval(self) -> "RiskBucket":
        if self.upper_exclusive is not None and self.upper_exclusive <= self.lower_inclusive:
            raise ValueError("risk bucket upper bound must exceed lower bound")
        return self


class ComparisonGroupPolicy(StrictModel):
    policy_id: str
    version: Version
    dimensions: tuple[str, ...] = (
        "cycle_id",
        "decision_time",
        "underlying_id",
        "horizon",
        "objective_family",
        "capital_at_risk_bucket",
        "currency",
    )
    capital_at_risk_sources: tuple[str, ...] = (
        "risk.maximum_loss",
        "risk.margin_estimate",
        "cost_liquidity.entry_cost",
    )
    currency_sources: tuple[str, ...] = (
        "candidate.currency",
        "cost_liquidity.currency",
        "market_snapshot.currency",
    )
    supported_horizons: tuple[str, ...] = ()
    allow_structured_horizons: bool = True
    risk_buckets: tuple[RiskBucket, ...]

    @model_validator(mode="after")
    def validate_policy(self) -> "ComparisonGroupPolicy":
        expected = (
            "cycle_id",
            "decision_time",
            "underlying_id",
            "horizon",
            "objective_family",
            "capital_at_risk_bucket",
            "currency",
        )
        if self.dimensions != expected:
            raise ValueError("comparison dimensions cannot silently change the canonical grain")
        if not self.risk_buckets:
            raise ValueError("at least one risk bucket is required")
        ordered = sorted(self.risk_buckets, key=lambda item: item.lower_inclusive)
        if tuple(ordered) != self.risk_buckets:
            raise ValueError("risk buckets must be ordered")
        for left, right in zip(ordered, ordered[1:]):
            if left.upper_exclusive is None or left.upper_exclusive != right.lower_inclusive:
                raise ValueError("risk buckets must be contiguous and non-overlapping")
        if ordered[-1].upper_exclusive is not None:
            raise ValueError("last risk bucket must be open-ended")
        return self


class ComparisonGroupPolicyRegistry(StrictModel):
    registry_id: str
    registry_version: Version
    active_policy_id: str
    policies: tuple[ComparisonGroupPolicy, ...]

    @model_validator(mode="after")
    def active_policy_exists(self) -> "ComparisonGroupPolicyRegistry":
        ids = [item.policy_id for item in self.policies]
        if len(ids) != len(set(ids)) or self.active_policy_id not in ids:
            raise ValueError("comparison group registry is inconsistent")
        return self

    def active(self) -> ComparisonGroupPolicy:
        return next(item for item in self.policies if item.policy_id == self.active_policy_id)


class MetricDefinition(StrictModel):
    metric_id: str
    semantic_version: Version
    source_paths: tuple[str, ...]
    units: str
    direction: Direction
    transformation_policy: TransformationPolicy = "IDENTITY"
    missingness_policy: MissingnessPolicy = "BLOCK"
    value_type: Literal["NUMBER", "INTEGER", "BOOLEAN", "STRING"] = "NUMBER"

    @field_validator("source_paths")
    @classmethod
    def paths_nonempty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("metric definition requires at least one source path")
        return value


class MetricSemanticsRegistry(StrictModel):
    registry_id: str
    registry_version: Version
    metrics: tuple[MetricDefinition, ...]

    @model_validator(mode="after")
    def unique_metrics(self) -> "MetricSemanticsRegistry":
        ids = [item.metric_id for item in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("metric IDs must be unique")
        return self

    def mapping(self) -> dict[str, MetricDefinition]:
        return {item.metric_id: item for item in self.metrics}


class ObjectiveFamilyDefinition(StrictModel):
    objective_family: str
    required_metric_ids: tuple[str, ...]
    optional_metric_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_metric_overlap(self) -> "ObjectiveFamilyDefinition":
        if set(self.required_metric_ids) & set(self.optional_metric_ids):
            raise ValueError("required and optional metrics must not overlap")
        return self


class ObjectiveFamilyRegistry(StrictModel):
    registry_id: str
    registry_version: Version
    families: tuple[ObjectiveFamilyDefinition, ...]

    @model_validator(mode="after")
    def unique_families(self) -> "ObjectiveFamilyRegistry":
        ids = [item.objective_family for item in self.families]
        if len(ids) != len(set(ids)):
            raise ValueError("objective family IDs must be unique")
        return self

    def mapping(self) -> dict[str, ObjectiveFamilyDefinition]:
        return {item.objective_family: item for item in self.families}


class CandidateBundleRecord(StrictModel):
    candidate_id: str
    cycle_id: str
    decision_time: AwareDatetime
    underlying_id: str
    horizon: str
    objective_family: str
    market_snapshot_id: str
    lineage_id: str
    candidate: dict[str, JsonValue]
    legs: tuple[dict[str, JsonValue], ...]
    payoffs: tuple[dict[str, JsonValue], ...]
    scenario_evaluations: tuple[dict[str, JsonValue], ...]
    generation_trace: tuple[dict[str, JsonValue], ...]
    risk: dict[str, JsonValue]
    cost_liquidity: dict[str, JsonValue]
    lineage: dict[str, JsonValue]
    market_snapshot: dict[str, JsonValue]
    ambiguity_evaluations: tuple[dict[str, JsonValue], ...] = ()
    greeks: tuple[dict[str, JsonValue], ...] = ()
    equivalence: tuple[dict[str, JsonValue], ...] = ()
    quality_diversity: tuple[dict[str, JsonValue], ...] = ()
    feature_base: dict[str, JsonValue] = {}


class EligibilityCandidateRecord(CandidateBundleRecord):
    eligibility_status: Literal["ELIGIBLE", "BLOCKED"]
    eligibility_decision_id: str


class EligibilityDecisionRecord(StrictModel):
    decision_id: str
    candidate_id: str
    status: Literal["ELIGIBLE", "BLOCKED"]
    reason_codes: tuple[str, ...]
    evidence: tuple[dict[str, JsonValue], ...]
    policy_id: str
    policy_version: Version


class ComparisonGroupRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    query_id: str
    cycle_id: str
    decision_time: AwareDatetime
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk: float = Field(ge=0)
    capital_at_risk_source: str
    capital_at_risk_bucket: str
    currency: str
    group_size: int = Field(ge=1)
    policy_id: str
    policy_version: Version


class MetricRouteRecord(StrictModel):
    metric_route_id: str
    candidate_id: str
    comparison_group_id: str
    metric_id: str
    source_artifact_name: str
    source_path: str
    units: str
    direction: Direction
    required: bool
    transformation_policy: TransformationPolicy
    missingness_policy: MissingnessPolicy
    semantic_version: Version
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    raw_value: JsonValue | None = None


class HandoffArtifactReference(StrictModel):
    artifact_name: str
    artifact_id: str
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    schema_version: Version
    record_count: int = Field(ge=0)
    grain: str
    producer_module_id: str


class FoundationHandoffRecord(StrictModel):
    handoff_id: str
    contract_version: Version
    semantic_version: Version
    producer_stage: Literal["FOUNDATION"]
    consumer_stages: tuple[Literal["TOURNAMENT", "LEARNING"], ...]
    artifacts: tuple[HandoffArtifactReference, ...]

    @field_validator("artifacts")
    @classmethod
    def unique_artifacts(cls, value: tuple[HandoffArtifactReference, ...]) -> tuple[HandoffArtifactReference, ...]:
        names = [item.artifact_name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("handoff artifact names must be unique")
        return value

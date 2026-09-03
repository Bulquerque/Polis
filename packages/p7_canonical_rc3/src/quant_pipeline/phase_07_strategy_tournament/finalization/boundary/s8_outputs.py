"""Strict S8 output record models."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .base import ArtifactReference, FrozenModel, _aware


class RankedStrategyRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    underlying_id: str
    horizon: str
    objective_family: str
    risk_bucket: str
    candidate_id: str
    rank_position: int = Field(ge=1)
    economic_tie_id: str | None = None
    pareto_tier: int = Field(ge=0)
    hybrid_score: float
    diversity_penalty: float = Field(ge=0)
    diversity_adjusted_score: float
    score_confidence: float = Field(ge=0, le=1)
    robustness_stage: float
    execution_quality_stage: float
    leg_count: int = Field(ge=1)
    diversity_cluster_id: str
    model_id: str
    score_semantics_version: str
    calibration_status: str
    calibration_version: str
    ood_severity: str
    model_disagreement: float | None = Field(default=None, ge=0)
    ranking_policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class RankingTieRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    economic_tie_id: str
    candidate_ids: tuple[str, ...]
    deterministic_order: tuple[str, ...]
    tie_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)

    @model_validator(mode="after")
    def tie_cardinality(self) -> "RankingTieRecord":
        if len(self.candidate_ids) < 2 or set(self.candidate_ids) != set(self.deterministic_order):
            raise ValueError("tie record must contain the same two or more candidates")
        return self


class RankingGroupSummaryRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_count: int = Field(ge=0)
    tie_count: int = Field(ge=0)
    top_candidate_id: str | None
    minimum_score: float | None
    maximum_score: float | None
    ranking_policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class SortComponent(FrozenModel):
    name: str
    value: str | int | float
    direction: str


class ThesisCardRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    rank_position: int = Field(ge=1)
    belief_reference_ids: tuple[str, ...]
    objective_family: str
    origin_template: str | None
    mutation_trace: tuple[str, ...]
    payoff_shape_reference: str
    profit_regions: tuple[str, ...]
    failure_regions: tuple[str, ...]
    score_contributions: dict[str, float]
    confidence_state: dict[str, str | float | None]
    ood_state: str
    nearest_alternative_ids: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    section_availability: dict[str, str]
    evidence_artifact_ids: tuple[str, ...]
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class RankingTraceRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    rank_position: int = Field(ge=1)
    sort_stages: tuple[SortComponent, ...]
    economic_tie_id: str | None
    policy_versions: dict[str, str]
    model_id: str
    evidence_artifact_ids: tuple[str, ...]
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class RankingAuditRecord(FrozenModel):
    run_id: str
    cycle_id: str
    decision_time: datetime
    received_count: int = Field(ge=0)
    ranked_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    candidate_conservation_pass: bool
    group_count: int = Field(ge=0)
    tie_count: int = Field(ge=0)
    policy_versions: dict[str, str]
    model_versions: tuple[str, ...]
    input_artifact_hashes: dict[str, str]
    output_artifact_hashes: dict[str, str]
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)

    @model_validator(mode="after")
    def conservation(self) -> "RankingAuditRecord":
        if self.received_count != self.ranked_count + self.abstained_count + self.blocked_count:
            raise ValueError("candidate counts do not conserve")
        if not self.candidate_conservation_pass:
            raise ValueError("candidate conservation must pass")
        return self


class ExecutionContextSnapshotRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    rank_position: int = Field(ge=1)
    comparison_group_id: str
    strategy_candidate_reference: ArtifactReference
    strategy_legs_reference: ArtifactReference
    payoff_evaluation_reference: ArtifactReference
    scenario_evaluation_reference: ArtifactReference
    risk_reference: ArtifactReference
    cost_liquidity_reference: ArtifactReference
    greeks_reference: ArtifactReference
    generation_trace_reference: ArtifactReference
    thesis_card_reference: ArtifactReference
    score_decomposition_reference: ArtifactReference
    leg_ids: tuple[str, ...]
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class LegacyProjectionRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    projection_status: str
    reason_code: str | None
    represented_leg_count: int = Field(ge=1)
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class Phase8ManifestRecord(FrozenModel):
    contract_id: str
    contract_version: str
    semantic_version: str
    producer_phase: str
    consumer_phase: str
    artifact_references: tuple[ArtifactReference, ...]
    candidate_count: int = Field(ge=0)
    candidate_conservation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    lineage_id: str

    _created_aware = field_validator("created_at")(_aware)

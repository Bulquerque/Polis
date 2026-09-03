"""S7 output record models."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from .base import FrozenModel, _aware


class SimilarityEdgeRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id_left: str
    candidate_id_right: str
    similarity_score: float = Field(ge=0, le=1)
    stage_scores: dict[str, float]
    evidence_weight_coverage: float = Field(ge=0, le=1)
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class SimilaritySummaryRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    retained_neighbor_count: int = Field(ge=0)
    evaluated_pair_count: int = Field(ge=0)
    insufficient_evidence_pair_count: int = Field(ge=0)
    top_similarity: float = Field(ge=0, le=1)
    mean_top_k_similarity: float = Field(ge=0, le=1)
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class DiversityClusterRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    diversity_cluster_id: str
    local_density: float = Field(ge=0, le=1)
    novelty_score: float = Field(ge=0, le=1)
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class DiversityAdjustmentRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    local_density: float = Field(ge=0, le=1)
    raw_penalty: float = Field(ge=0)
    applied_penalty: float = Field(ge=0)
    penalty_cap: float = Field(ge=0)
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class DiversityAdjustedScoreRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    hybrid_score: float | None
    diversity_penalty: float = Field(ge=0)
    diversity_adjusted_score: float | None
    score_confidence: float | None = Field(default=None, ge=0, le=1)
    score_status: str
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class DecisionRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    decision: str
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class RankableRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    hybrid_score: float
    diversity_penalty: float = Field(ge=0)
    diversity_adjusted_score: float
    score_confidence: float = Field(ge=0, le=1)
    robustness_stage: float
    execution_quality_stage: float
    leg_count: int = Field(ge=1)
    pareto_tier: int = Field(ge=0)
    model_id: str
    score_semantics_version: str
    calibration_status: str
    calibration_version: str
    ood_severity: str
    model_disagreement: float | None = Field(default=None, ge=0)
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)

class AbstainedRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    reason_codes: tuple[str, ...]
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: tuple[str, ...]
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class BlockedRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    candidate_id: str
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class GroupRankabilityRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    comparison_group_id: str
    received_count: int = Field(ge=0)
    rankable_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    group_reason_codes: tuple[str, ...]
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class AuditRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    module_id: str
    counts: dict[str, int]
    reason_code_distribution: dict[str, int]
    policy_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)

"""Immutable candidate domain model used by S7."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candidate:
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    comparison_group_id: str
    hybrid_score: float | None
    robust_score: float | None
    execution_quality: float | None
    complexity_score: float | None
    score_confidence: float | None
    interval_lower: float | None
    interval_upper: float | None
    model_disagreement: float | None
    calibration_status: str
    calibration_version: str
    ood_severity: str
    model_id: str
    model_promotion_status: str
    model_compatibility_status: str
    score_semantics_version: str
    payoff_shape: tuple[float, ...]
    scenario_payoff: tuple[float, ...]
    greek_vector: tuple[float, ...]
    leg_ids: frozenset[str]
    origin_template: str | None
    expiration_ids: frozenset[str]
    defined_risk_status: str
    execution_context_time: datetime
    context_available: bool
    candidate_identity_hash: str
    strategy_artifact_id: str
    strategy_content_sha256: str
    strategy_schema_version: str
    lineage_id: str
    pareto_tier: int | None = None


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    score: float | None
    stage_scores: tuple[tuple[str, float], ...]
    evidence_weight_coverage: float


@dataclass(frozen=True, slots=True)
class SafetyOutcome:
    candidate_id: str
    blocked: bool
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]

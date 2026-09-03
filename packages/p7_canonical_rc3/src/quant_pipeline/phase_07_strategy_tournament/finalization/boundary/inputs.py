"""Learning input record models."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .base import ArtifactReference, FrozenModel, _aware


class HybridScoreRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    comparison_group_id: str
    hybrid_score: float | None
    robust_score: float | None = None
    execution_quality: float | None = None
    complexity_score: float | None = None
    model_id: str
    model_promotion_status: str
    model_compatibility_status: str
    score_semantics_version: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class ConfidenceRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    score_confidence: float | None = Field(default=None, ge=0, le=1)
    score_interval_lower: float | None = None
    score_interval_upper: float | None = None
    model_disagreement: float | None = Field(default=None, ge=0)
    calibration_status: str
    calibration_version: str
    ood_severity: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)

    @model_validator(mode="after")
    def interval_order(self) -> "ConfidenceRecord":
        if self.score_interval_lower is not None and self.score_interval_upper is not None:
            if self.score_interval_lower > self.score_interval_upper:
                raise ValueError("score interval lower exceeds upper")
        return self


class ComparisonGroupRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    comparison_group_id: str
    underlying_id: str
    horizon: str
    objective_family: str
    risk_bucket: str
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)


class StrategyReferenceRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    comparison_group_id: str
    candidate_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    strategy_artifact_id: str
    strategy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    strategy_schema_version: str
    strategy_lineage_id: str
    payoff_shape: tuple[float, ...] = ()
    scenario_payoff: tuple[float, ...] = ()
    greek_vector: tuple[float, ...] = ()
    leg_ids: tuple[str, ...] = ()
    origin_template: str | None = None
    expiration_ids: tuple[str, ...] = ()
    defined_risk_status: str
    execution_context_time: datetime
    context_available: bool = True
    pareto_tier: int | None = Field(default=None, ge=0)
    belief_reference_ids: tuple[str, ...] = ()
    mutation_trace: tuple[str, ...] = ()
    profit_regions: tuple[str, ...] = ()
    failure_regions: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    strategy_candidate_reference: ArtifactReference | None = None
    strategy_legs_reference: ArtifactReference | None = None
    payoff_evaluation_reference: ArtifactReference | None = None
    scenario_evaluation_reference: ArtifactReference | None = None
    risk_reference: ArtifactReference | None = None
    cost_liquidity_reference: ArtifactReference | None = None
    greeks_reference: ArtifactReference | None = None
    generation_trace_reference: ArtifactReference | None = None
    legacy_underlying: str | None = None
    legacy_instrument_type: str | None = None
    legacy_action_type: str | None = None
    legacy_reference_price: float | None = None
    legacy_contract_key: str | None = None
    legacy_expiration_date: str | None = None
    legacy_strike: float | None = None
    legacy_dte: int | None = Field(default=None, ge=0)
    legacy_cost_estimate: float | None = None
    legacy_liquidity_score: float | None = Field(default=None, ge=0, le=1)

    _decision_aware = field_validator("decision_time")(_aware)
    _context_aware = field_validator("execution_context_time")(_aware)

class PreFinalBlockedRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)

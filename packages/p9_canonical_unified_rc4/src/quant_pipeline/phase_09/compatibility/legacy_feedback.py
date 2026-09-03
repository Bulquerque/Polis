from __future__ import annotations

from typing import Any

from pydantic import Field

from quant_pipeline.phase_09.contracts.base import NonEmptyStr, StrictModel

from .models import LegacyFeedbackHeader


class SignalFeedbackReport(StrictModel):
    header: LegacyFeedbackHeader
    target_module: NonEmptyStr
    forecast_error_summary: dict[str, Any]
    calibration_error: dict[str, Any]
    regime_performance_breakdown: dict[str, Any]
    ood_failure_summary: dict[str, Any]
    drift_failure_summary: dict[str, Any]
    model_stability_score: float

    def to_wire(self) -> dict[str, Any]:
        return {**self.header.model_dump(mode="json"), **self.model_dump(mode="json", exclude={"header"})}


class RankingFeedbackReport(StrictModel):
    header: LegacyFeedbackHeader
    rank_ic_summary: dict[str, Any]
    ndcg_at_k_summary: dict[str, Any]
    top_k_hit_rate: float = Field(ge=0, le=1)
    blocked_candidate_review: dict[str, Any]
    bad_candidate_accepted_review: dict[str, Any]
    score_head_ablation_summary: dict[str, Any]
    safety_gate_effectiveness: dict[str, Any]

    def to_wire(self) -> dict[str, Any]:
        return {**self.header.model_dump(mode="json"), **self.model_dump(mode="json", exclude={"header"})}


class PortfolioFeedbackReport(StrictModel):
    header: LegacyFeedbackHeader
    sizing_stability_summary: dict[str, Any]
    execution_quality_summary: dict[str, Any]
    cost_slippage_error_summary: dict[str, Any]
    risk_limit_breach_summary: dict[str, Any]
    entropy_effectiveness_summary: dict[str, Any]
    margin_usage_summary: dict[str, Any]
    short_option_policy_review: dict[str, Any]

    def to_wire(self) -> dict[str, Any]:
        return {**self.header.model_dump(mode="json"), **self.model_dump(mode="json", exclude={"header"})}

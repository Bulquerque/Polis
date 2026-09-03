"""Runtime and versioned policies for P7.S8."""
from __future__ import annotations

from pydantic import Field, model_validator

from .base import FrozenModel
from .config import RuntimeConfig


class RankingPolicy(FrozenModel):
    policy_id: str
    score_round_digits: int = Field(ge=0, le=15)
    max_group_size: int = Field(ge=1)
    sort_keys: tuple[str, ...]

    @model_validator(mode="after")
    def exact_sort_registry(self) -> "RankingPolicy":
        expected = (
            "pareto_tier",
            "diversity_adjusted_score",
            "score_confidence",
            "robustness_stage",
            "execution_quality_stage",
            "leg_count",
            "candidate_id",
        )
        if self.sort_keys != expected:
            raise ValueError("ranking sort key registry does not match frozen contract")
        return self


class ThesisPolicy(FrozenModel):
    policy_id: str
    max_nearest_alternatives: int = Field(ge=0, le=20)
    structured_evidence_only: bool
    llm_authoritative: bool

    @model_validator(mode="after")
    def no_authoritative_llm(self) -> "ThesisPolicy":
        if not self.structured_evidence_only or self.llm_authoritative:
            raise ValueError("thesis cards require structured evidence and non-authoritative LLM use")
        return self


class PublicationPolicy(FrozenModel):
    policy_id: str
    contract_version: str
    semantic_version: str
    consumer_phase: str
    legacy_projection_mode: str
    required_reference_fields: tuple[str, ...]

    @model_validator(mode="after")
    def publication_invariants(self) -> "PublicationPolicy":
        expected = {
            "strategy_candidate_reference",
            "strategy_legs_reference",
            "payoff_evaluation_reference",
            "scenario_evaluation_reference",
            "risk_reference",
            "cost_liquidity_reference",
            "greeks_reference",
            "generation_trace_reference",
        }
        if set(self.required_reference_fields) != expected:
            raise ValueError("publication reference registry is incomplete")
        if self.consumer_phase != "P8":
            raise ValueError("P7.S8 publication consumer must be P8")
        return self


class S8Config(FrozenModel):
    runtime: RuntimeConfig
    ranking: RankingPolicy
    thesis: ThesisPolicy
    publication: PublicationPolicy
    forbidden_fields: tuple[str, ...]

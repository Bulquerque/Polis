from __future__ import annotations

from pydantic import Field, model_validator

from ..enums import ChallengerQualificationState, ContaminationState
from .common import ConfigId, EvidenceReference, NonEmptyStr, StrictModel


class PairwiseComparisonEvidence(StrictModel):
    champion_configuration_id: ConfigId
    challenger_configuration_id: ConfigId
    cohort_id: NonEmptyStr
    effect_size: float
    effect_lower_bound: float
    effect_upper_bound: float
    probability_of_superiority: float = Field(ge=0.0, le=1.0)
    paired_bootstrap_available: bool
    anytime_valid_state: NonEmptyStr | None = None
    live_comparison_available: bool = False
    live_effect_size: float | None = None
    live_degradation_detected: bool = False
    evidence_refs: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_intervals(self) -> "PairwiseComparisonEvidence":
        if self.effect_lower_bound > self.effect_upper_bound:
            raise ValueError("comparison lower bound cannot exceed upper bound")
        if not (self.effect_lower_bound <= self.effect_size <= self.effect_upper_bound):
            raise ValueError("effect size must lie inside its interval")
        if self.live_effect_size is not None and not self.live_comparison_available:
            raise ValueError("live_effect_size requires live comparison evidence")
        return self


class ChallengerQualification(StrictModel):
    challenger_configuration_id: ConfigId
    state: ChallengerQualificationState
    effect_size: float | None
    probability_of_superiority: float | None
    contamination_state: ContaminationState
    blocking_reasons: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    evidence_refs: tuple[EvidenceReference, ...] = ()


class ChampionChallengerQualificationReport(StrictModel):
    champion_configuration_id: ConfigId
    cohort_id: NonEmptyStr
    qualifications: tuple[ChallengerQualification, ...]
    recommended_challenger_id: ConfigId | None
    report_state: ChallengerQualificationState
    warnings: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_recommended_challenger(self) -> "ChampionChallengerQualificationReport":
        ids = {item.challenger_configuration_id for item in self.qualifications}
        if self.recommended_challenger_id is not None and self.recommended_challenger_id not in ids:
            raise ValueError("recommended challenger must be present in qualifications")
        return self

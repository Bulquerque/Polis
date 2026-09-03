"""P5 belief evidence bundle contract resolved through P6 lineage."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from .base import AwareDatetime, NonEmptyStr, StrictModel
from .common import ArtifactReference
from .enums import HorizonUnit, ProbabilityMeasure


class HorizonSpec(StrictModel):
    value: int = Field(gt=0, strict=True)
    unit: HorizonUnit


class P5BeliefEvidenceBundleV1(StrictModel):
    belief_state_id: NonEmptyStr
    target_id: NonEmptyStr
    underlying_or_factor_id: NonEmptyStr
    forecast_horizon: HorizonSpec
    as_of_time: AwareDatetime
    decision_time: AwareDatetime
    resolver_id: NonEmptyStr
    model_artifact_id: NonEmptyStr
    probability_measure: ProbabilityMeasure
    forecast_distribution_ref: ArtifactReference | None = None
    quantile_panel_ref: ArtifactReference | None = None
    scenario_set_ref: ArtifactReference | None = None
    path_scenario_ref: ArtifactReference | None = None
    covariance_dependence_ref: ArtifactReference | None = None
    regime_state_ref: ArtifactReference | None = None
    ood_state_ref: ArtifactReference | None = None
    disagreement_ref: ArtifactReference | None = None
    calibration_ref: ArtifactReference | None = None
    ambiguity_evidence_ref: ArtifactReference | None = None
    ensemble_weights_ref: ArtifactReference | None = None
    view_refs: tuple[ArtifactReference, ...] = Field(default_factory=tuple)
    lineage_refs: tuple[ArtifactReference, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_predictive_evidence(self) -> Self:
        predictive = (
            self.forecast_distribution_ref,
            self.quantile_panel_ref,
            self.scenario_set_ref,
            self.path_scenario_ref,
        )
        if not any(reference is not None for reference in predictive):
            raise ValueError("at least one predictive evidence reference is required")
        if self.as_of_time > self.decision_time:
            raise ValueError("as_of_time must not be after P5 decision_time")
        return self

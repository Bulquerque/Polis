"""Strong V2 contracts for confidence and the P5-to-P6 publication manifest."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .core import ArtifactReference, FrozenModel
from .v2_base import CalibrationStatus, V2ArtifactIdentity


class ForecastConfidenceRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    calibration_component: float | None = Field(default=None, ge=0.0, le=1.0)
    data_quality_component: float | None = Field(default=None, ge=0.0, le=1.0)
    model_stability_component: float | None = Field(default=None, ge=0.0, le=1.0)
    ensemble_disagreement_component: float | None = Field(default=None, ge=0.0, le=1.0)
    ood_component: float | None = Field(default=None, ge=0.0, le=1.0)
    regime_uncertainty_component: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    confidence_method: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    calibration_status: CalibrationStatus
    abstained: bool
    lineage_id: str = Field(min_length=1)


class ForecastConfidence(V2ArtifactIdentity):
    records: tuple[ForecastConfidenceRecord, ...] = Field(min_length=1)


class Phase6StrategyScenarioManifest(V2ArtifactIdentity):
    market_belief_state: ArtifactReference
    return_distributions: ArtifactReference
    volatility_distributions: ArtifactReference
    path_risk_forecasts: ArtifactReference
    scenario_paths: ArtifactReference
    ambiguity_sets: ArtifactReference
    dependence_states: ArtifactReference
    regime_ood_states: ArtifactReference
    forecast_confidence: ArtifactReference
    availability_report: ArtifactReference
    lineage_report: ArtifactReference
    scenario_capability: str = Field(min_length=1)
    surface_capability: str = Field(min_length=1)
    ambiguity_capability: str = Field(min_length=1)
    extended_scenario_path_capability: str = Field(min_length=1)
    extended_ambiguity_capability: str = Field(min_length=1)
    producer_contract_version: Literal["P5-P6-V2"] = "P5-P6-V2"
    handoff_mode: Literal["FULL_V2", "DEGRADED_V2"]
    published_artifacts: tuple[str, ...] = Field(min_length=11, max_length=11)
    published_capabilities: dict[str, str] = Field(min_length=1)
    production_promotion_allowed: Literal[False] = False

    @model_validator(mode="after")
    def unique_references(self) -> "Phase6StrategyScenarioManifest":
        references = [
            self.market_belief_state,
            self.return_distributions,
            self.volatility_distributions,
            self.path_risk_forecasts,
            self.scenario_paths,
            self.ambiguity_sets,
            self.dependence_states,
            self.regime_ood_states,
            self.forecast_confidence,
            self.availability_report,
            self.lineage_report,
        ]
        identifiers = [item.artifact_id for item in references]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("manifest references must use unique artifact IDs")
        expected_artifacts = (
            "market_belief_state", "return_distributions", "volatility_distributions",
            "path_risk_forecasts", "scenario_paths", "ambiguity_sets",
            "dependence_states", "regime_ood_states", "forecast_confidence",
            "availability_report", "lineage_report",
        )
        if self.published_artifacts != expected_artifacts:
            raise ValueError("published_artifacts must enumerate the canonical P5 V2 artifact set")
        return self

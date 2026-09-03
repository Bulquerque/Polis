"""P5 RC34 compatibility contracts owned by the P6 boundary."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc


class P5ArtifactReference(FrozenModel):
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    storage_uri: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1)
    row_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class P5Phase6StrategyScenarioManifest(FrozenModel):
    artifact_id: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1)
    producer_phase: Literal["P5"] = "P5"
    producer_module_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    decision_time: datetime
    created_at: datetime
    available_at: datetime
    lineage_id: str = Field(min_length=1)
    market_belief_state: P5ArtifactReference
    return_distributions: P5ArtifactReference
    volatility_distributions: P5ArtifactReference
    path_risk_forecasts: P5ArtifactReference
    scenario_paths: P5ArtifactReference
    ambiguity_sets: P5ArtifactReference
    dependence_states: P5ArtifactReference
    regime_ood_states: P5ArtifactReference
    forecast_confidence: P5ArtifactReference
    availability_report: P5ArtifactReference
    lineage_report: P5ArtifactReference
    scenario_capability: str = Field(min_length=1)
    surface_capability: str = Field(min_length=1)
    ambiguity_capability: str = Field(min_length=1)
    extended_scenario_path_capability: str = Field(min_length=1)
    extended_ambiguity_capability: str = Field(min_length=1)
    producer_contract_version: str | None = Field(default=None, min_length=1)
    handoff_mode: str | None = Field(default=None, min_length=1)
    published_artifacts: tuple[str, ...] = ()
    published_capabilities: dict[str, str] = Field(default_factory=dict)
    # Deprecated RC34 fields are accepted only to preserve deterministic replay
    # of previously signed fixtures. New P5 publications do not emit them.
    p6_native_contract_version: str | None = Field(default=None, min_length=1)
    p6_native_consumed_artifacts: tuple[str, ...] = ()
    full_v2_manifest_consumption_status: str | None = Field(default=None, min_length=1)
    production_promotion_allowed: Literal[False] = False


    @model_validator(mode="after")
    def validate_contract_descriptor(self) -> "P5Phase6StrategyScenarioManifest":
        canonical = self.producer_contract_version is not None
        legacy = self.p6_native_contract_version is not None
        if canonical == legacy:
            raise ValueError("manifest must use exactly one canonical or legacy contract descriptor")
        if canonical:
            expected = tuple(self.references())
            if self.producer_contract_version != "P5-P6-V2":
                raise ValueError("unsupported P5 producer contract version")
            if self.handoff_mode not in {"FULL_V2", "DEGRADED_V2"}:
                raise ValueError("canonical P5 manifest requires an explicit handoff_mode")
            if self.published_artifacts != expected:
                raise ValueError("published_artifacts do not match the canonical manifest references")
        return self

    @property
    def contract_version_for_receipt(self) -> str:
        return self.producer_contract_version or str(self.p6_native_contract_version)

    @property
    def is_legacy_descriptor(self) -> bool:
        return self.producer_contract_version is None

    @field_validator("decision_time", "created_at", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return utc(value)

    def references(self) -> dict[str, P5ArtifactReference]:
        return {
            "market_belief_state": self.market_belief_state,
            "return_distributions": self.return_distributions,
            "volatility_distributions": self.volatility_distributions,
            "path_risk_forecasts": self.path_risk_forecasts,
            "scenario_paths": self.scenario_paths,
            "ambiguity_sets": self.ambiguity_sets,
            "dependence_states": self.dependence_states,
            "regime_ood_states": self.regime_ood_states,
            "forecast_confidence": self.forecast_confidence,
            "availability_report": self.availability_report,
            "lineage_report": self.lineage_report,
        }


class P5ScenarioPathRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    decision_time: datetime
    horizon: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    scenario_type: str = Field(min_length=1)
    probability: Decimal | None = Field(default=None, ge=0, le=1)
    path_step: int = Field(ge=1)
    path_timestamp: datetime
    future_return: Decimal
    future_spot: Decimal | None = Field(default=None, ge=0)
    realized_volatility_state: Decimal | None = Field(default=None, ge=0)
    implied_volatility_state: Decimal | None = Field(default=None, ge=0)
    skew_state: Decimal | None = None
    term_structure_state: Decimal | None = None
    liquidity_state: Decimal | None = None
    regime_state: str | None = None
    jump_state: bool
    stress_flags: tuple[str, ...] = ()
    seed: int
    generator_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

    @field_validator("decision_time", "path_timestamp")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return utc(value)


class P5ReturnDistributionRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    decision_time: datetime
    distribution: dict[str, JsonValue]
    distribution_family: str = Field(min_length=1)
    distribution_version: str = Field(min_length=1)
    calibration_status: str = Field(min_length=1)
    confidence: Decimal = Field(ge=0, le=1)
    lineage_id: str = Field(min_length=1)
    units: str = Field(min_length=1)
    mean: Decimal | None = None
    median: Decimal | None = None
    mode: Decimal | None = None
    mode_method: str | None = None
    quantiles: tuple[dict[str, JsonValue], ...] = ()
    probability_negative: Decimal | None = Field(default=None, ge=0, le=1)
    probability_positive: Decimal | None = Field(default=None, ge=0, le=1)
    support: tuple[Decimal | None, Decimal | None] | None = None
    tail_probabilities: dict[str, JsonValue] = Field(default_factory=dict)
    tail_probability_semantics: str | None = None
    model_member_ids: tuple[str, ...] = ()

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


class P5ForecastConfidenceRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    calibration_component: Decimal | None = Field(default=None, ge=0, le=1)
    data_quality_component: Decimal | None = Field(default=None, ge=0, le=1)
    model_stability_component: Decimal | None = Field(default=None, ge=0, le=1)
    ensemble_disagreement_component: Decimal | None = Field(default=None, ge=0, le=1)
    ood_component: Decimal | None = Field(default=None, ge=0, le=1)
    regime_uncertainty_component: Decimal | None = Field(default=None, ge=0, le=1)
    overall_confidence: Decimal = Field(ge=0, le=1)
    confidence_method: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    calibration_status: str = Field(min_length=1)
    abstained: bool
    lineage_id: str = Field(min_length=1)


class P5RegimeOODRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    validity_status: str = Field(min_length=1)
    regime_probabilities: dict[str, Decimal] = Field(default_factory=dict)
    transition_probabilities: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    expected_duration: dict[str, Decimal] = Field(default_factory=dict)
    feature_ood: Decimal | None = None
    market_state_ood: Decimal | None = None
    model_ood: Decimal | None = None
    dependence_ood: Decimal | None = None
    change_point_probability: Decimal | None = None
    reason_codes: tuple[str, ...] = ()
    lineage_id: str = Field(min_length=1)


class P5AmbiguitySetRecord(FrozenModel):
    nominal_distribution_id: str = Field(min_length=1)
    ambiguity_method: str = Field(min_length=1)
    radius_or_band: Decimal = Field(ge=0)
    calibration_sample_size: int = Field(ge=0)
    coverage_target: Decimal = Field(ge=0, le=1)
    plausible_distribution_ids: tuple[str, ...] = ()
    stress_distribution_ids: tuple[str, ...] = ()
    scope: dict[str, JsonValue]
    validity_status: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)


class P5ArtifactReceipt(FrozenModel):
    artifact_name: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1)
    row_count: int | None = Field(default=None, ge=0)
    availability: str
    reason_code: str | None = None


class P5CompatibilityReport(FrozenModel):
    manifest_id: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    upstream_run_id: str = Field(min_length=1)
    upstream_cycle_id: str = Field(min_length=1)
    upstream_lineage_id: str = Field(min_length=1)
    p5_contract_version: str = Field(min_length=1)
    validation_status: str = Field(min_length=1)
    full_manifest_consumed: bool
    receipts: tuple[P5ArtifactReceipt, ...]
    scenario_sources: dict[str, str] = Field(default_factory=dict)
    artifact_usage: dict[str, str] = Field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()

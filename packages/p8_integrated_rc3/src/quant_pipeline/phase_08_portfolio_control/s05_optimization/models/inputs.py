from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .base import Identifier, Sha256, TimeAwareModel
from .enums import ActionabilityState, ScoreSemantics
from .policies import ApprovedPolicyContext


class ArtifactEnvelope(TimeAwareModel):
    artifact_id: Identifier
    artifact_type: Identifier
    schema_version: Identifier
    contract_version: Identifier
    producer_phase: Identifier
    producer_module: Identifier
    producer_release: Identifier
    pipeline_version: Identifier
    run_id: Identifier
    cycle_id: int = Field(ge=0)
    decision_time: datetime
    market_cutoff_at: datetime
    computed_at: datetime
    recorded_at: datetime
    available_at: datetime
    content_sha256: Sha256
    lineage_id: Identifier

    @model_validator(mode="after")
    def valid_clocks(self) -> "ArtifactEnvelope":
        if self.market_cutoff_at > self.decision_time:
            raise ValueError("market cutoff after decision time")
        if self.computed_at < self.market_cutoff_at:
            raise ValueError("computed_at before market cutoff")
        if self.recorded_at < self.computed_at:
            raise ValueError("recorded_at before computed_at")
        if self.available_at < self.computed_at:
            raise ValueError("available_at before computed_at")
        return self


class Horizon(TimeAwareModel):
    horizon_id: Identifier
    step: int = Field(ge=0)
    duration_seconds: int = Field(gt=0)


class GreekExposure(TimeAwareModel):
    greek_name: Identifier
    value_per_unit: float


class CandidateRiskInput(TimeAwareModel):
    candidate_id: Identifier
    canonical_candidate_id: Identifier
    comparison_group_id: Identifier
    actionability: ActionabilityState
    score_semantics: ScoreSemantics = ScoreSemantics.ORDINAL
    current_quantity: float
    minimum_quantity: float
    maximum_quantity: float
    quantity_increment: float = Field(gt=0)
    lot_size: float = Field(gt=0)
    capital_per_unit: float | None = Field(default=None, ge=0)
    margin_per_unit: float | None = Field(default=None, ge=0)
    maximum_loss_per_unit: float | None = Field(default=None, ge=0)
    risk_economics_status: Literal["QUALIFIED", "DEGRADED", "UNAVAILABLE"] = "QUALIFIED"
    transaction_cost_per_unit: float = Field(ge=0)
    funding_cost_per_unit_by_horizon: tuple[float, ...]
    liquidity_trade_cap_by_horizon: tuple[float | None, ...]
    liquidity_status: Literal["QUALIFIED", "DEGRADED", "UNAVAILABLE"] = "QUALIFIED"
    underlying_bucket: Identifier
    expiration_bucket: Identifier
    greeks: tuple[GreekExposure, ...] = ()

    @model_validator(mode="after")
    def valid_bounds(self) -> "CandidateRiskInput":
        if self.minimum_quantity > self.maximum_quantity:
            raise ValueError("candidate minimum exceeds maximum")
        if not self.minimum_quantity <= self.current_quantity <= self.maximum_quantity:
            raise ValueError("current quantity outside candidate bounds")
        if any(x < 0 for x in self.funding_cost_per_unit_by_horizon):
            raise ValueError("funding costs must be non-negative")
        if any(x is not None and x < 0 for x in self.liquidity_trade_cap_by_horizon):
            raise ValueError("liquidity caps must be non-negative")
        economics = (self.capital_per_unit, self.margin_per_unit, self.maximum_loss_per_unit)
        if self.risk_economics_status in {"QUALIFIED", "DEGRADED"} and any(
            value is None for value in economics
        ):
            raise ValueError("qualified/degraded risk economics require all numeric values")
        if self.risk_economics_status == "UNAVAILABLE" and any(
            value is not None for value in economics
        ):
            raise ValueError("unavailable risk economics cannot carry numeric values")
        if self.liquidity_status in {"QUALIFIED", "DEGRADED"} and any(
            value is None for value in self.liquidity_trade_cap_by_horizon
        ):
            raise ValueError("qualified/degraded liquidity requires all horizon caps")
        if self.liquidity_status == "UNAVAILABLE" and any(
            value is not None for value in self.liquidity_trade_cap_by_horizon
        ):
            raise ValueError("unavailable liquidity cannot carry numeric caps")
        names = [g.greek_name for g in self.greeks]
        if len(names) != len(set(names)):
            raise ValueError("duplicate greek names")
        return self


class ScenarioCandidatePnL(TimeAwareModel):
    candidate_id: Identifier
    incremental_pnl_by_horizon: tuple[float, ...]


class ScenarioPath(TimeAwareModel):
    scenario_id: Identifier
    probability: float = Field(gt=0, le=1)
    candidate_pnl: tuple[ScenarioCandidatePnL, ...]


class StressPath(TimeAwareModel):
    stress_id: Identifier
    portfolio_loss_limit: float = Field(ge=0)
    candidate_pnl: tuple[ScenarioCandidatePnL, ...]


class GreekLimit(TimeAwareModel):
    greek_name: Identifier
    minimum_by_horizon: tuple[float, ...]
    maximum_by_horizon: tuple[float, ...]


class ConcentrationLimit(TimeAwareModel):
    bucket_id: Identifier
    maximum_capital_by_horizon: tuple[float, ...]


class RiskLimits(TimeAwareModel):
    maximum_capital_by_horizon: tuple[float, ...]
    maximum_margin_by_horizon: tuple[float, ...]
    maximum_loss_by_horizon: tuple[float, ...]
    maximum_turnover: float = Field(ge=0)
    cvar_alpha: float = Field(gt=0, lt=1)
    maximum_cvar: float | None = Field(default=None, ge=0)
    greek_limits: tuple[GreekLimit, ...] = ()
    underlying_concentration: tuple[ConcentrationLimit, ...] = ()
    expiration_concentration: tuple[ConcentrationLimit, ...] = ()


class OrdinalPreference(TimeAwareModel):
    preferred_candidate_id: Identifier
    lower_candidate_id: Identifier
    strength: float = Field(gt=0)


class AmbiguityInput(TimeAwareModel):
    calibrated: bool
    robust_scenario_probabilities: tuple[float, ...] | None = None
    lower_expected_pnl_by_candidate_horizon: tuple[ScenarioCandidatePnL, ...] = ()


class DecisionReadyRiskPayload(TimeAwareModel):
    decision_snapshot_hash: Sha256
    pnl_semantics: Literal["INCREMENTAL_STEP"] = "INCREMENTAL_STEP"
    horizons: tuple[Horizon, ...]
    candidates: tuple[CandidateRiskInput, ...]
    scenarios: tuple[ScenarioPath, ...]
    mandatory_stresses: tuple[StressPath, ...] = ()
    risk_limits: RiskLimits
    ordinal_preferences: tuple[OrdinalPreference, ...] = ()
    ambiguity: AmbiguityInput | None = None
    policy_context: ApprovedPolicyContext

    @model_validator(mode="after")
    def validate_cross_references(self) -> "DecisionReadyRiskPayload":
        horizon_count = self._validate_horizons()
        candidate_ids = self._validate_candidates(horizon_count)
        self._validate_scenario_collection(candidate_ids, horizon_count)
        self._validate_limit_lengths(horizon_count)
        self._validate_greek_coverage()
        self._validate_preferences(candidate_ids)
        self._validate_mpc_horizon(horizon_count)
        return self

    def _validate_horizons(self) -> int:
        count = len(self.horizons)
        if not count:
            raise ValueError("at least one horizon is required")
        if [horizon.step for horizon in self.horizons] != list(range(count)):
            raise ValueError("horizon steps must be contiguous from zero")
        return count

    def _validate_candidates(self, horizon_count: int) -> set[str]:
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate candidate IDs")
        for candidate in self.candidates:
            self._validate_candidate_horizons(candidate, horizon_count)
        return set(candidate_ids)

    @staticmethod
    def _validate_candidate_horizons(candidate: CandidateRiskInput, count: int) -> None:
        if len(candidate.funding_cost_per_unit_by_horizon) != count:
            raise ValueError("candidate funding horizon mismatch")
        if len(candidate.liquidity_trade_cap_by_horizon) != count:
            raise ValueError("candidate liquidity horizon mismatch")

    def _validate_scenario_collection(self, expected: set[str], count: int) -> None:
        if self.scenarios and abs(sum(item.probability for item in self.scenarios) - 1.0) > 1e-9:
            raise ValueError("scenario probabilities must sum to one")
        for scenario in self.scenarios:
            self._validate_pnl_panel(scenario.candidate_pnl, expected, count)
        for stress in self.mandatory_stresses:
            self._validate_pnl_panel(stress.candidate_pnl, expected, count)

    @staticmethod
    def _validate_pnl_panel(
        panel: tuple[ScenarioCandidatePnL, ...],
        expected: set[str],
        count: int,
    ) -> None:
        ids = [row.candidate_id for row in panel]
        if set(ids) != expected or len(ids) != len(expected):
            raise ValueError("scenario candidate set mismatch")
        if any(len(row.incremental_pnl_by_horizon) != count for row in panel):
            raise ValueError("scenario PnL horizon mismatch")

    def _validate_limit_lengths(self, count: int) -> None:
        limits = self.risk_limits
        vectors = (
            limits.maximum_capital_by_horizon,
            limits.maximum_margin_by_horizon,
            limits.maximum_loss_by_horizon,
        )
        if any(len(vector) != count for vector in vectors):
            raise ValueError("risk limit horizon mismatch")
        self._validate_greek_limit_lengths(count)
        self._validate_concentration_lengths(count)

    def _validate_greek_limit_lengths(self, count: int) -> None:
        for item in self.risk_limits.greek_limits:
            lengths = (len(item.minimum_by_horizon), len(item.maximum_by_horizon))
            if lengths != (count, count):
                raise ValueError("greek limit horizon mismatch")

    def _validate_concentration_lengths(self, count: int) -> None:
        limits = (
            *self.risk_limits.underlying_concentration,
            *self.risk_limits.expiration_concentration,
        )
        if any(len(item.maximum_capital_by_horizon) != count for item in limits):
            raise ValueError("concentration limit horizon mismatch")

    def _validate_greek_coverage(self) -> None:
        required = {item.greek_name for item in self.risk_limits.greek_limits}
        if not required:
            return
        for candidate in self.candidates:
            may_be_nonzero = any(
                abs(quantity) > 1e-12
                for quantity in (
                    candidate.current_quantity,
                    candidate.minimum_quantity,
                    candidate.maximum_quantity,
                )
            )
            if not may_be_nonzero:
                continue
            available = {item.greek_name for item in candidate.greeks}
            missing = sorted(required - available)
            if missing:
                raise ValueError(
                    f"candidate {candidate.candidate_id} lacks mandatory Greek coverage: "
                    + ", ".join(missing)
                )

    def _validate_preferences(self, candidate_ids: set[str]) -> None:
        for preference in self.ordinal_preferences:
            pair = {preference.preferred_candidate_id, preference.lower_candidate_id}
            if not pair.issubset(candidate_ids):
                raise ValueError("ordinal preference references unknown candidate")
            if len(pair) != 2:
                raise ValueError("self ordinal preference is forbidden")

    def _validate_mpc_horizon(self, horizon_count: int) -> None:
        if self.policy_context.mpc.planning_horizon_steps != horizon_count:
            raise ValueError("MPC policy horizon differs from risk bundle")


class DecisionReadyRiskBundle(TimeAwareModel):
    envelope: ArtifactEnvelope
    payload: DecisionReadyRiskPayload

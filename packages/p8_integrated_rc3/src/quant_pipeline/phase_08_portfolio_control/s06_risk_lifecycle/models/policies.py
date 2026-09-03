from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import Identifier, Sha256, TimeAwareModel


class RiskGatePolicy(TimeAwareModel):
    numerical_tolerance: float = Field(gt=0, le=1e-3)
    require_all_horizons: bool = True
    block_on_future_plan_violation: bool = True
    maximum_optimizer_risk_discrepancy: float = Field(ge=0)


class HedgePolicy(TimeAwareModel):
    enabled: bool = True
    approved_hedge_candidate_ids: tuple[Identifier, ...] = ()
    risk_weight: float = Field(gt=0)
    transaction_cost_weight: float = Field(ge=0)
    minimum_cvar_reduction: float = Field(ge=0)
    maximum_total_absolute_hedge_units: float = Field(gt=0)
    maximum_cost: float = Field(ge=0)
    time_limit_seconds: float = Field(gt=0, le=300)
    mip_relative_gap: float = Field(ge=0, le=0.1)


class LifecyclePolicy(TimeAwareModel):
    require_complete_context: bool = True
    close_before_expiry_seconds: int = Field(ge=0)
    roll_before_expiry_seconds: int = Field(ge=0)
    minimum_early_exercise_benefit: float = Field(ge=0)
    minimum_assignment_risk_intrinsic: float = Field(ge=0)
    maximum_time_value_for_assignment_risk: float = Field(ge=0)
    allow_american_early_exercise: bool = True
    prevent_short_assignment_if_possible: bool = True

    @model_validator(mode="after")
    def valid_windows(self) -> "LifecyclePolicy":
        if self.roll_before_expiry_seconds < self.close_before_expiry_seconds:
            raise ValueError("roll window cannot be shorter than close window")
        return self


class EmergencyPolicy(TimeAwareModel):
    enabled: bool = True
    protected_candidate_ids: tuple[Identifier, ...] = ()
    protection_penalty_per_unit: float = Field(ge=0)
    economic_preservation_weight: float = Field(ge=0)
    time_limit_seconds: float = Field(gt=0, le=300)
    mip_relative_gap: float = Field(ge=0, le=0.1)


class AuthorizationPolicy(TimeAwareModel):
    validity_seconds: int = Field(ge=1, le=86400)
    allow_partial_authorization: bool = False
    emergency_overrides_normal_target: bool = True


class ApprovedS6PolicyContext(TimeAwareModel):
    policy_id: Identifier
    policy_version: Identifier
    authorized_by: Identifier
    effective_from_cycle: int = Field(ge=0)
    expires_after_cycle: int | None = Field(default=None, ge=0)
    content_sha256: Sha256
    created_at: datetime
    risk_gate: RiskGatePolicy
    hedge: HedgePolicy
    lifecycle: LifecyclePolicy
    emergency: EmergencyPolicy
    authorization: AuthorizationPolicy

    @model_validator(mode="after")
    def valid_cycle_window(self) -> "ApprovedS6PolicyContext":
        if self.expires_after_cycle is not None and self.expires_after_cycle < self.effective_from_cycle:
            raise ValueError("policy expiry precedes effective cycle")
        ids = self.hedge.approved_hedge_candidate_ids
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate approved hedge candidate IDs")
        protected = self.emergency.protected_candidate_ids
        if len(protected) != len(set(protected)):
            raise ValueError("duplicate protected candidate IDs")
        return self

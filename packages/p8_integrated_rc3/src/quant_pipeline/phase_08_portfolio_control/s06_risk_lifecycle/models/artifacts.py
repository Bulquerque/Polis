from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import ArtifactEnvelope

from .base import Identifier, Sha256, TimeAwareModel
from .enums import (
    AuthorizationActionType, AuthorizationStatus, EmergencyStatus, HedgeStatus,
    LifecycleAction, LifecycleStatus, RiskGateStatus,
)


class HorizonRiskMetrics(TimeAwareModel):
    horizon_id: Identifier
    capital: float = Field(ge=0)
    margin: float = Field(ge=0)
    maximum_loss: float = Field(ge=0)
    cvar: float | None = Field(default=None, ge=0)
    maximum_stress_loss: float | None = Field(default=None, ge=0)
    capital_limit: float = Field(ge=0)
    margin_limit: float = Field(ge=0)
    maximum_loss_limit: float = Field(ge=0)
    cvar_limit: float | None = Field(default=None, ge=0)
    feasible: bool
    reason_codes: tuple[Identifier, ...] = ()


class ExposureLimitResult(TimeAwareModel):
    exposure_type: Identifier
    bucket_id: Identifier
    horizon_id: Identifier
    value: float
    minimum: float | None = None
    maximum: float | None = None
    available: bool = True
    feasible: bool
    reason_codes: tuple[Identifier, ...] = ()


class IndependentRiskGateReport(TimeAwareModel):
    status: RiskGateStatus
    horizon_metrics: tuple[HorizonRiskMetrics, ...]
    exposure_limits: tuple[ExposureLimitResult, ...]
    optimizer_claimed_feasible: bool
    independently_feasible: bool
    maximum_optimizer_risk_discrepancy: float = Field(ge=0)
    decision_snapshot_hash: Sha256
    target_hash: Sha256
    report_hash: Sha256
    reason_codes: tuple[Identifier, ...] = ()


class HedgeAdjustment(TimeAwareModel):
    candidate_id: Identifier
    current_target_quantity: float
    adjustment_quantity: float
    hedged_target_quantity: float
    estimated_transaction_cost: float = Field(ge=0)


class HedgePlan(TimeAwareModel):
    status: HedgeStatus
    adjustments: tuple[HedgeAdjustment, ...]
    base_cvar: float | None = Field(default=None, ge=0)
    post_hedge_cvar: float | None = Field(default=None, ge=0)
    cvar_reduction: float = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    post_hedge_risk_gate: IndependentRiskGateReport | None = None
    plan_hash: Sha256
    reason_codes: tuple[Identifier, ...] = ()


class LifecycleLegDecision(TimeAwareModel):
    candidate_id: Identifier
    leg_id: Identifier
    instrument_id: Identifier
    action: LifecycleAction
    quantity: float
    effective_at: datetime
    reason_codes: tuple[Identifier, ...] = ()


class LifecyclePlan(TimeAwareModel):
    status: LifecycleStatus
    decisions: tuple[LifecycleLegDecision, ...]
    unsupported_candidate_ids: tuple[Identifier, ...] = ()
    plan_hash: Sha256
    reason_codes: tuple[Identifier, ...] = ()


class LiquidationStep(TimeAwareModel):
    sequence: int = Field(ge=1)
    candidate_id: Identifier
    current_target_quantity: float
    reduction_quantity: float
    resulting_target_quantity: float
    margin_relief: float = Field(ge=0)
    capital_relief: float = Field(ge=0)
    maximum_loss_relief: float = Field(ge=0)
    estimated_transaction_cost: float = Field(ge=0)
    structure_preserving: bool = True


class EmergencyPlan(TimeAwareModel):
    status: EmergencyStatus
    steps: tuple[LiquidationStep, ...]
    total_margin_relief: float = Field(ge=0)
    total_capital_relief: float = Field(ge=0)
    total_maximum_loss_relief: float = Field(ge=0)
    estimated_total_cost: float = Field(ge=0)
    feasibility_proven: bool
    plan_hash: Sha256
    reason_codes: tuple[Identifier, ...] = ()


class AuthorizedAction(TimeAwareModel):
    authorization_id: Identifier
    action_type: AuthorizationActionType
    candidate_id: Identifier
    target_quantity: float
    delta_quantity: float
    lifecycle_action: LifecycleAction | None = None
    valid_from: datetime
    valid_until: datetime
    reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid_window(self) -> "AuthorizedAction":
        if self.valid_until <= self.valid_from:
            raise ValueError("authorized action validity window is empty")
        return self


class ExecutionAuthorizationPayload(TimeAwareModel):
    status: AuthorizationStatus
    decision_snapshot_hash: Sha256
    risk_gate: IndependentRiskGateReport
    hedge_plan: HedgePlan
    lifecycle_plan: LifecyclePlan
    emergency_plan: EmergencyPlan
    authorized_actions: tuple[AuthorizedAction, ...]
    valid_from: datetime
    valid_until: datetime
    execution_authority: bool = True
    payload_hash: Sha256
    module_receipts: tuple[Identifier, ...]
    reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid_authority(self) -> "ExecutionAuthorizationPayload":
        authorized = {
            AuthorizationStatus.AUTHORIZED,
            AuthorizationStatus.PARTIALLY_AUTHORIZED,
            AuthorizationStatus.EMERGENCY_AUTHORIZED,
        }
        if self.valid_until < self.valid_from:
            raise ValueError("payload validity ends before it starts")
        if self.status in authorized:
            if not self.execution_authority or not self.authorized_actions:
                raise ValueError("authorized status requires executable actions")
        elif self.execution_authority or self.authorized_actions:
            raise ValueError("non-authorized status cannot carry execution authority")
        for action in self.authorized_actions:
            if action.valid_from < self.valid_from or action.valid_until > self.valid_until:
                raise ValueError("action validity escapes payload window")
        return self


class ExecutionAuthorizationBundle(TimeAwareModel):
    envelope: ArtifactEnvelope
    payload: ExecutionAuthorizationPayload

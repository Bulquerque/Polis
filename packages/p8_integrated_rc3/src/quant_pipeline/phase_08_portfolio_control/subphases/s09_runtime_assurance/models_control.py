from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from .enums import AlertSeverity, ReasonCode, RuntimeMode, ShiftState
from .models_common import RuntimeContext, StrictModel
from .models_invariants import InvariantMonitorResult
from .models_shift import ShiftMonitorResult


class ExecutionExposureState(StrictModel):
    has_unhedged_partial_fill: bool
    margin_headroom_ratio: Decimal
    safe_cancel_available: bool
    safe_hedge_available: bool
    safe_flatten_available: bool
    market_access_available: bool


class SupervisorPolicy(StrictModel):
    policy_id: str = Field(min_length=1)
    valid_until: datetime
    material_shift_mode: RuntimeMode = RuntimeMode.HOLD_NO_NEW_RISK
    critical_margin_mode: RuntimeMode = RuntimeMode.CONTROLLED_FLATTEN
    state_inconsistent_mode: RuntimeMode = RuntimeMode.HOLD_NO_NEW_RISK

    @field_validator("valid_until")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("valid_until must be timezone-aware")
        return value


class SafetySupervisorRequest(StrictModel):
    context: RuntimeContext
    shift_result: ShiftMonitorResult
    invariant_result: InvariantMonitorResult
    exposure_state: ExecutionExposureState
    policy: SupervisorPolicy


class RuntimeControlCommand(StrictModel):
    command_id: str = Field(min_length=1)
    mode: RuntimeMode
    reason_codes: tuple[ReasonCode, ...]
    issued_at: datetime
    valid_until: datetime
    idempotency_key: str = Field(min_length=1)
    allowed_actions: tuple[str, ...]
    feasibility_proven: bool


class SafetySupervisorResult(StrictModel):
    selected_mode: RuntimeMode
    command: RuntimeControlCommand
    trigger_severity: AlertSeverity
    trigger_shift_state: ShiftState

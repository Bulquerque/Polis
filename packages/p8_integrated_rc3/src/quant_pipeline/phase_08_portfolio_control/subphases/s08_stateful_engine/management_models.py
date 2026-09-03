from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import Field

from quant_pipeline.phase_08_portfolio_control.foundation.enums import RuntimeControlMode
from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, StrictModel, TimeAwareModel
from .enums import ManagementActionType, ManagementSignalType, StatefulEventKind


class ManagementSignal(TimeAwareModel):
    event_type: Literal[StatefulEventKind.MANAGEMENT_SIGNAL] = StatefulEventKind.MANAGEMENT_SIGNAL
    signal_id: NonEmptyStr
    event_time: datetime
    signal_type: ManagementSignalType
    reason_code: NonEmptyStr
    affected_instrument_ids: tuple[NonEmptyStr, ...] = ()
    affected_candidate_ids: tuple[NonEmptyStr, ...] = ()


class ManagementAction(TimeAwareModel):
    action_id: NonEmptyStr
    event_time: datetime
    action_type: ManagementActionType
    reason_code: NonEmptyStr
    requires_new_authorization: bool
    affected_instrument_ids: tuple[NonEmptyStr, ...] = ()
    affected_candidate_ids: tuple[NonEmptyStr, ...] = ()


class ReoptimizationRequest(TimeAwareModel):
    request_id: NonEmptyStr
    event_time: datetime
    source_cycle_id: NonEmptyStr
    requested_next_cycle_id: NonEmptyStr
    reason_code: NonEmptyStr
    source_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    affected_instrument_ids: tuple[NonEmptyStr, ...] = ()
    affected_candidate_ids: tuple[NonEmptyStr, ...] = ()


class ManagementDecisionBundle(StrictModel):
    actions: tuple[ManagementAction, ...]
    reoptimization_requests: tuple[ReoptimizationRequest, ...]
    active_runtime_mode: RuntimeControlMode
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

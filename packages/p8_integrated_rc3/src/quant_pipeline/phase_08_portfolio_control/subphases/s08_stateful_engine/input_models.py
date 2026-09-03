from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import InstrumentSpec, P8ExecutionAuthorizationBundle
from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, StrictModel, TimeAwareModel
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import ExecutionCommand, RuntimeControlCommand
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.runner import S7Result
from .accounting_models import AccountEvent
from .base_models import payload_hash
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256
from .lifecycle_models import LifecycleEvent, OptionContractSpec
from .management_models import ManagementSignal
from .prior_state_models import PriorPortfolioState
from .valuation_models import MarkSelectionPolicy, MarkSnapshot


class ManagementPolicy(StrictModel):
    auto_reoptimization_on_partial_fill: bool = True
    auto_reoptimization_on_target_expiry: bool = True
    auto_reoptimization_on_lifecycle_due: bool = True
    hold_on_incomplete_valuation: bool = True


class S8PolicyBundle(StrictModel):
    policy_version: NonEmptyStr
    mark_selection: MarkSelectionPolicy = MarkSelectionPolicy()
    management: ManagementPolicy = ManagementPolicy()
    allow_equity_splits: bool = True
    allow_option_contract_adjustments: bool = False
    checkpoint_event_stride: int = Field(default=1000, ge=1)


class S7ToS8Handoff(TimeAwareModel):
    handoff_id: NonEmptyStr
    contract_version: NonEmptyStr = "1.0.0"
    producer_release: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: datetime
    authorization_bundle: P8ExecutionAuthorizationBundle
    s7_result: S7Result
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_handoff(self):
        if self.run_id != self.authorization_bundle.run_id or self.cycle_id != self.authorization_bundle.cycle_id:
            raise ValueError("handoff run/cycle must match authorization bundle")
        if self.decision_time != self.authorization_bundle.decision_time:
            raise ValueError("handoff decision_time must match authorization bundle")
        receipt = self.s7_result.receipt
        if receipt.order_event_ledger_hash != content_sha256(self.s7_result.execution.order_events):
            raise ValueError("S7 order-event ledger hash mismatch")
        if receipt.fill_event_ledger_hash != content_sha256(self.s7_result.execution.fill_events):
            raise ValueError("S7 fill-event ledger hash mismatch")
        return self


class S8InputBundle(TimeAwareModel):
    bundle_id: NonEmptyStr
    contract_version: NonEmptyStr = "1.0.0"
    schema_version: NonEmptyStr = "1.0.0"
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: datetime
    valuation_time: datetime
    s7_handoff: S7ToS8Handoff
    prior_state: PriorPortfolioState
    option_contracts: tuple[OptionContractSpec, ...] = ()
    supplemental_instruments: tuple[InstrumentSpec, ...] = ()
    lifecycle_events: tuple[LifecycleEvent, ...] = ()
    account_events: tuple[AccountEvent, ...] = ()
    marks: MarkSnapshot
    runtime_commands: tuple[ExecutionCommand, ...] = ()
    management_signals: tuple[ManagementSignal, ...] = ()
    policies: S8PolicyBundle
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_bundle(self):
        if self.run_id != self.s7_handoff.run_id or self.cycle_id != self.s7_handoff.cycle_id:
            raise ValueError("S8 input run/cycle mismatch")
        if self.decision_time != self.s7_handoff.decision_time:
            raise ValueError("decision_time mismatch")
        if self.prior_state.as_of_time > self.decision_time:
            raise ValueError("prior state cannot be after decision_time")
        if self.marks.valuation_time != self.valuation_time:
            raise ValueError("mark snapshot valuation_time mismatch")
        auth = self.s7_handoff.authorization_bundle
        last_sequence = -1
        for command in self.runtime_commands:
            if isinstance(command, RuntimeControlCommand):
                if command.run_id is not None and command.run_id != self.run_id:
                    raise ValueError("runtime command run mismatch")
                if command.cycle_id is not None and command.cycle_id != self.cycle_id:
                    raise ValueError("runtime command cycle mismatch")
                if command.source_state_hash is not None and command.source_state_hash != auth.content_sha256:
                    raise ValueError("runtime command source_state_hash mismatch")
                if command.valid_until is not None and command.valid_until < self.valuation_time:
                    raise ValueError("runtime command is expired")
                if not command.feasibility_proven and command.mode.value != "NORMAL":
                    raise ValueError("runtime command lacks feasibility proof")
                if command.command_sequence <= last_sequence:
                    raise ValueError("runtime command sequence must be strictly increasing")
                last_sequence = command.command_sequence
        prior_physical = {p.instrument_id: p.quantity for p in self.prior_state.physical_positions}
        auth_physical = {p.instrument_id: p.quantity for p in auth.current_positions}
        if prior_physical != auth_physical:
            raise ValueError("prior physical positions must equal S7 authorization current positions")
        prior_virtual = {(p.candidate_id,p.instrument_id): p.quantity for p in self.prior_state.virtual_positions}
        auth_virtual = {(p.candidate_id,p.instrument_id): p.quantity for p in auth.current_virtual_positions}
        if prior_virtual != auth_virtual:
            raise ValueError("prior virtual positions must equal S7 authorization current virtual positions")
        return self

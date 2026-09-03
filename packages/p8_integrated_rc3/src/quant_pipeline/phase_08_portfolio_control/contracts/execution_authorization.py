from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, model_validator

from ..foundation.enums import (
    AuthorizationStatus,
    OrderType,
    PositionIntent,
    RiskRole,
    SecurityType,
    TimeInForce,
    Urgency,
)
from ..foundation.models import Fraction, NonEmptyStr, NonNegativeDecimal, PositiveDecimal, StrictModel, TimeAwareModel
from ..foundation.hashing import content_sha256
from .common import ArtifactReference, LineageEdge

SignedDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


class InstrumentSpec(TimeAwareModel):
    instrument_id: NonEmptyStr
    symbol: NonEmptyStr
    security_type: SecurityType
    currency: NonEmptyStr
    lot_size: PositiveDecimal
    quantity_increment: PositiveDecimal
    contract_multiplier: PositiveDecimal
    valid_from: datetime
    valid_until: datetime | None = None
    underlying_id: str | None = None
    expiration: datetime | None = None

    @model_validator(mode="after")
    def validate_contract(self):
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.security_type == SecurityType.OPTION and self.expiration is None:
            raise ValueError("options require expiration")
        return self


class CandidateAllocation(StrictModel):
    candidate_id: NonEmptyStr
    allocated_target_quantity: SignedDecimal


class ExecutableTarget(StrictModel):
    target_id: NonEmptyStr
    authorization_id: NonEmptyStr
    execution_group_id: NonEmptyStr
    instrument_id: NonEmptyStr
    target_quantity: SignedDecimal
    urgency: Urgency
    risk_role: RiskRole
    position_intent: PositionIntent
    leg_priority: int = Field(default=0, ge=0)
    virtual_allocations: tuple[CandidateAllocation, ...]

    @model_validator(mode="after")
    def validate_allocations(self):
        total = sum((item.allocated_target_quantity for item in self.virtual_allocations), Decimal("0"))
        if total != self.target_quantity:
            raise ValueError("virtual allocations must sum exactly to target_quantity")
        return self


class CurrentPosition(StrictModel):
    instrument_id: NonEmptyStr
    quantity: SignedDecimal


class CurrentVirtualPosition(StrictModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    quantity: SignedDecimal


class OpenOrderExposure(StrictModel):
    order_id: NonEmptyStr
    instrument_id: NonEmptyStr
    remaining_signed_quantity: SignedDecimal
    virtual_allocations: tuple[CandidateAllocation, ...]

    @model_validator(mode="after")
    def validate_virtual_allocations(self):
        total = sum((item.allocated_target_quantity for item in self.virtual_allocations), Decimal("0"))
        if total != self.remaining_signed_quantity:
            raise ValueError("open-order virtual allocations must sum to remaining_signed_quantity")
        return self


class ExecutionAuthorization(TimeAwareModel):
    authorization_id: NonEmptyStr
    target_id: NonEmptyStr
    status: AuthorizationStatus
    valid_until: datetime
    allowed_order_types: tuple[OrderType, ...]
    allowed_time_in_force: tuple[TimeInForce, ...]
    allow_legging: bool
    allow_market_order: bool = False
    allow_unwind: bool = False
    max_temporary_notional: NonNegativeDecimal = Decimal("0")
    max_participation_rate: Fraction
    price_protection_bps: NonNegativeDecimal
    preferred_venues: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_execution_permissions(self):
        if not self.allowed_order_types or not self.allowed_time_in_force or not self.preferred_venues:
            raise ValueError("execution authorization requires order types, TIFs, and preferred venues")
        if OrderType.MARKET in self.allowed_order_types and not self.allow_market_order:
            raise ValueError("MARKET in allowed_order_types requires allow_market_order=true")
        if self.max_participation_rate <= 0:
            raise ValueError("max_participation_rate must be positive")
        return self


class P8ExecutionAuthorizationBundle(TimeAwareModel):
    bundle_id: NonEmptyStr
    contract_version: NonEmptyStr = "1.0.0"
    schema_version: NonEmptyStr = "1.0.0"
    producer_release: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: datetime
    valid_until: datetime
    targets: tuple[ExecutableTarget, ...]
    authorizations: tuple[ExecutionAuthorization, ...]
    instruments: tuple[InstrumentSpec, ...]
    current_positions: tuple[CurrentPosition, ...] = ()
    current_virtual_positions: tuple[CurrentVirtualPosition, ...] = ()
    open_orders: tuple[OpenOrderExposure, ...] = ()
    dual_book_map_ref: ArtifactReference
    risk_gate_ref: ArtifactReference
    hedge_plan_ref: ArtifactReference
    lifecycle_plan_ref: ArtifactReference
    lineage: tuple[LineageEdge, ...]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_bundle(self):
        if self.valid_until <= self.decision_time:
            raise ValueError("bundle validity must extend beyond decision_time")
        instrument_ids = {item.instrument_id for item in self.instruments}
        auth_by_id = {item.authorization_id: item for item in self.authorizations}
        target_ids = set()
        for target in self.targets:
            if target.target_id in target_ids:
                raise ValueError(f"duplicate target_id: {target.target_id}")
            target_ids.add(target.target_id)
            if target.instrument_id not in instrument_ids:
                raise ValueError(f"unknown instrument_id: {target.instrument_id}")
            auth = auth_by_id.get(target.authorization_id)
            if auth is None or auth.target_id != target.target_id:
                raise ValueError(f"authorization mismatch for target: {target.target_id}")
        if len(auth_by_id) != len(self.authorizations):
            raise ValueError("duplicate authorization_id")
        target_instruments = [item.instrument_id for item in self.targets]
        if len(target_instruments) != len(set(target_instruments)):
            raise ValueError("final executable bundle requires one net physical target per instrument")
        physical_by_instrument = {item.instrument_id: item.quantity for item in self.current_positions}
        virtual_by_instrument: dict[str, Decimal] = {}
        virtual_keys: set[tuple[str, str]] = set()
        for item in self.current_virtual_positions:
            key = (item.candidate_id, item.instrument_id)
            if key in virtual_keys:
                raise ValueError(f"duplicate current virtual position: {key}")
            virtual_keys.add(key)
            virtual_by_instrument[item.instrument_id] = virtual_by_instrument.get(item.instrument_id, Decimal("0")) + item.quantity
        for instrument_id in set(physical_by_instrument) | set(virtual_by_instrument):
            if physical_by_instrument.get(instrument_id, Decimal("0")) != virtual_by_instrument.get(instrument_id, Decimal("0")):
                raise ValueError(f"current virtual positions must reconcile to physical position: {instrument_id}")
        open_physical: dict[str, Decimal] = {}
        open_virtual: dict[str, Decimal] = {}
        for item in self.open_orders:
            open_physical[item.instrument_id] = open_physical.get(item.instrument_id, Decimal("0")) + item.remaining_signed_quantity
            open_virtual[item.instrument_id] = open_virtual.get(item.instrument_id, Decimal("0")) + sum(
                (allocation.allocated_target_quantity for allocation in item.virtual_allocations), Decimal("0")
            )
        if open_physical != open_virtual:
            raise ValueError("open-order virtual allocations must reconcile by instrument")
        return self


def execution_authorization_payload_hash(bundle: P8ExecutionAuthorizationBundle) -> str:
    return content_sha256(bundle.model_dump(mode="python", exclude={"content_sha256"}))


def seal_execution_authorization_bundle(
    bundle: P8ExecutionAuthorizationBundle,
) -> P8ExecutionAuthorizationBundle:
    """Return an immutable copy sealed with the canonical payload hash."""
    return bundle.model_copy(update={"content_sha256": execution_authorization_payload_hash(bundle)})

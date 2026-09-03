"""Read-only portfolio/account state contracts consumed by P8.S1."""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from .base import AwareDatetime, CurrencyCode, NonEmptyStr, SHA256Str, StrictModel
from .common import ArtifactReference
from .enums import DiscrepancySeverity, RuntimeMode, StateQualityStatus


class PositionRecord(StrictModel):
    instrument_id: NonEmptyStr
    quantity: Decimal
    contract_multiplier: Decimal = Field(gt=0)
    currency: CurrencyCode
    average_cost: Decimal | None = None


class CashBalance(StrictModel):
    currency: CurrencyCode
    amount: Decimal


class MarginBalance(StrictModel):
    currency: CurrencyCode
    used: Decimal = Field(ge=0)
    available: Decimal = Field(ge=0)


class CollateralBalance(StrictModel):
    asset_id: NonEmptyStr
    currency: CurrencyCode
    market_value: Decimal = Field(ge=0)
    eligible_value: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_eligibility(self) -> Self:
        if self.eligible_value > self.market_value:
            raise ValueError("eligible collateral cannot exceed market value")
        return self




class OpenOrderVirtualAllocation(StrictModel):
    candidate_id: NonEmptyStr
    allocated_remaining_quantity: Decimal


class OpenOrderRecord(StrictModel):
    order_id: NonEmptyStr
    instrument_id: NonEmptyStr
    total_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    signed_remaining_quantity: Decimal | None = None
    virtual_allocations: tuple[OpenOrderVirtualAllocation, ...] = Field(default_factory=tuple)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_quantity_conservation(self) -> Self:
        if self.total_quantity != self.filled_quantity + self.remaining_quantity:
            raise ValueError("open order quantity does not conserve")
        if self.signed_remaining_quantity is not None:
            if abs(self.signed_remaining_quantity) != abs(self.remaining_quantity):
                raise ValueError("signed remaining quantity must match remaining_quantity magnitude")
            allocated = sum(
                (item.allocated_remaining_quantity for item in self.virtual_allocations),
                Decimal("0"),
            )
            if allocated != self.signed_remaining_quantity:
                raise ValueError("open-order virtual allocations must reconcile to signed remaining quantity")
        elif self.virtual_allocations:
            raise ValueError("open-order virtual allocations require signed_remaining_quantity")
        return self


def _validate_unique_state_records(
    *,
    positions: tuple[PositionRecord, ...],
    cash: tuple[CashBalance, ...],
    margin: tuple[MarginBalance, ...],
    collateral: tuple[CollateralBalance, ...],
    open_orders: tuple[OpenOrderRecord, ...],
    label: str,
) -> None:
    checks = (
        (tuple(position.instrument_id for position in positions), "positions", "instrument_id"),
        (tuple(balance.currency for balance in cash), "cash balances", "currency"),
        (tuple(balance.currency for balance in margin), "margin balances", "currency"),
        (tuple(balance.asset_id for balance in collateral), "collateral balances", "asset_id"),
        (tuple(order.order_id for order in open_orders), "open orders", "order_id"),
    )
    for values, category, key in checks:
        if len(set(values)) != len(values):
            raise ValueError(f"{label} {category} must be unique by {key}")


class PortfolioStateProjection(StrictModel):
    state_id: NonEmptyStr
    as_of_time: AwareDatetime
    positions: tuple[PositionRecord, ...] = Field(default_factory=tuple)
    cash: tuple[CashBalance, ...] = Field(default_factory=tuple)
    margin: tuple[MarginBalance, ...] = Field(default_factory=tuple)
    collateral: tuple[CollateralBalance, ...] = Field(default_factory=tuple)
    open_orders: tuple[OpenOrderRecord, ...] = Field(default_factory=tuple)
    virtual_candidate_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    event_log_ref: ArtifactReference
    checkpoint_ref: ArtifactReference | None = None
    replay_hash: SHA256Str
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_unique_records(self) -> Self:
        _validate_unique_state_records(
            positions=self.positions,
            cash=self.cash,
            margin=self.margin,
            collateral=self.collateral,
            open_orders=self.open_orders,
            label="portfolio",
        )
        return self


class AccountSnapshot(StrictModel):
    account_snapshot_id: NonEmptyStr
    as_of_time: AwareDatetime
    positions: tuple[PositionRecord, ...] = Field(default_factory=tuple)
    cash: tuple[CashBalance, ...] = Field(default_factory=tuple)
    margin: tuple[MarginBalance, ...] = Field(default_factory=tuple)
    collateral: tuple[CollateralBalance, ...] = Field(default_factory=tuple)
    open_orders: tuple[OpenOrderRecord, ...] = Field(default_factory=tuple)
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_unique_records(self) -> Self:
        _validate_unique_state_records(
            positions=self.positions,
            cash=self.cash,
            margin=self.margin,
            collateral=self.collateral,
            open_orders=self.open_orders,
            label="account",
        )
        return self


class StateDiscrepancy(StrictModel):
    category: NonEmptyStr
    key: NonEmptyStr
    severity: DiscrepancySeverity
    internal_value: NonEmptyStr
    external_value: NonEmptyStr
    tolerance: Decimal = Field(ge=0)


class StateQualityReport(StrictModel):
    runtime_mode: RuntimeMode
    status: StateQualityStatus
    discrepancies: tuple[StateDiscrepancy, ...] = Field(default_factory=tuple)
    external_snapshot_present: bool
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class CurrentPortfolioAndAccountState(StrictModel):
    portfolio_state: PortfolioStateProjection
    account_snapshot: AccountSnapshot | None = None
    quality_report: StateQualityReport

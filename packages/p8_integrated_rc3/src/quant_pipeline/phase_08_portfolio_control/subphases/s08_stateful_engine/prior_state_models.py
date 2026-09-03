from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, StrictModel, TimeAwareModel
from .base_models import EquityPoint, SignedDecimal


class PriorPhysicalPosition(TimeAwareModel):
    instrument_id: NonEmptyStr
    quantity: SignedDecimal
    signed_cost_basis: SignedDecimal
    average_entry_price: Decimal | None
    opened_at: datetime | None

    @model_validator(mode="after")
    def validate_basis(self):
        if self.quantity == 0:
            if self.signed_cost_basis != 0 or self.average_entry_price is not None:
                raise ValueError("flat position must have zero basis and no average price")
        else:
            if self.average_entry_price is None or self.average_entry_price <= 0:
                raise ValueError("open position requires positive average_entry_price")
            if (self.signed_cost_basis > 0) != (self.quantity > 0):
                raise ValueError("signed_cost_basis sign must match quantity")
        return self


class PriorVirtualPosition(TimeAwareModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    quantity: SignedDecimal
    signed_cost_basis: SignedDecimal
    average_entry_price: Decimal | None
    opened_at: datetime | None


class CurrencyAccountState(StrictModel):
    currency: NonEmptyStr
    cash_available: SignedDecimal
    collateral_restricted: SignedDecimal = Decimal("0")
    liabilities: SignedDecimal = Decimal("0")
    margin_used: SignedDecimal = Decimal("0")


class PriorPortfolioState(TimeAwareModel):
    state_id: NonEmptyStr
    as_of_time: datetime
    physical_positions: tuple[PriorPhysicalPosition, ...] = ()
    virtual_positions: tuple[PriorVirtualPosition, ...] = ()
    accounts: tuple[CurrencyAccountState, ...]
    opening_nav_functional: SignedDecimal
    functional_currency: NonEmptyStr
    net_external_flow_since_open: SignedDecimal = Decimal("0")
    equity_curve: tuple[EquityPoint, ...] = ()
    last_event_offsets: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_state(self):
        pids = [p.instrument_id for p in self.physical_positions]
        if len(pids) != len(set(pids)):
            raise ValueError("duplicate physical position")
        vids = [(p.candidate_id, p.instrument_id) for p in self.virtual_positions]
        if len(vids) != len(set(vids)):
            raise ValueError("duplicate virtual position")
        accounts = [a.currency for a in self.accounts]
        if len(accounts) != len(set(accounts)):
            raise ValueError("duplicate account currency")
        physical_qty = {p.instrument_id: p.quantity for p in self.physical_positions if p.quantity != 0}
        physical_basis = {p.instrument_id: p.signed_cost_basis for p in self.physical_positions if p.quantity != 0}
        virtual_qty: dict[str, Decimal] = {}
        virtual_basis: dict[str, Decimal] = {}
        for item in self.virtual_positions:
            virtual_qty[item.instrument_id] = virtual_qty.get(item.instrument_id, Decimal("0")) + item.quantity
            virtual_basis[item.instrument_id] = virtual_basis.get(item.instrument_id, Decimal("0")) + item.signed_cost_basis
        virtual_qty = {k: v for k, v in virtual_qty.items() if v != 0}
        virtual_basis = {k: v for k, v in virtual_basis.items() if v != 0}
        if physical_qty != virtual_qty:
            raise ValueError("virtual quantities must reconcile to physical positions")
        if physical_basis != virtual_basis:
            raise ValueError("virtual cost basis must reconcile to physical positions")
        if self.equity_curve and self.equity_curve[-1].as_of_time > self.as_of_time:
            raise ValueError("equity curve cannot extend past prior state")
        return self

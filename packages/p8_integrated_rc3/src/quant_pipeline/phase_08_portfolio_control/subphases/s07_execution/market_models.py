from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from ...foundation.enums import MarketEventType, OrderType, SecurityType, TimeInForce, VenueState
from ...foundation.models import NonEmptyStr, NonNegativeDecimal, PositiveDecimal, StrictModel, TimeAwareModel


class Quote(TimeAwareModel):
    instrument_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    bid_price: PositiveDecimal
    ask_price: PositiveDecimal
    bid_size: NonNegativeDecimal
    ask_size: NonNegativeDecimal
    venue: NonEmptyStr

    @model_validator(mode="after")
    def validate_quote(self):
        if self.ask_price < self.bid_price:
            raise ValueError("crossed quote is not accepted by the champion engine")
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        return self

    @property
    def mid(self):
        return (self.bid_price + self.ask_price) / 2


class MarketStateSnapshot(TimeAwareModel):
    snapshot_id: NonEmptyStr
    as_of_time: datetime
    quotes: tuple[Quote, ...]
    venue_states: dict[str, VenueState]

    @model_validator(mode="after")
    def validate_snapshot(self):
        keys = [(item.instrument_id, item.venue) for item in self.quotes]
        if len(keys) != len(set(keys)):
            raise ValueError("market snapshot requires at most one quote per instrument and venue")
        if any(item.available_at > self.as_of_time for item in self.quotes):
            raise ValueError("market snapshot cannot contain quotes unavailable at as_of_time")
        return self


class VenueCapabilities(StrictModel):
    venue: NonEmptyStr
    supports_combo: bool
    min_combo_legs: int = Field(default=2, ge=2)
    max_combo_legs: int = Field(default=4, ge=2)
    supported_security_types: tuple[SecurityType, ...]
    supported_order_types: tuple[OrderType, ...]
    supported_tifs: tuple[TimeInForce, ...]
    supports_fractional: bool = False
    supports_replace: bool = True

    @model_validator(mode="after")
    def validate_combo_limits(self):
        if self.max_combo_legs < self.min_combo_legs:
            raise ValueError("max_combo_legs must be >= min_combo_legs")
        return self


class QuoteEvent(TimeAwareModel):
    event_type: Literal[MarketEventType.QUOTE] = MarketEventType.QUOTE
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    quote: Quote

    @model_validator(mode="after")
    def validate_nested_clock(self):
        if self.event_time != self.quote.event_time or self.available_at != self.quote.available_at:
            raise ValueError("quote event clocks must equal nested quote clocks")
        return self


class TradeEvent(TimeAwareModel):
    event_type: Literal[MarketEventType.TRADE] = MarketEventType.TRADE
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    instrument_id: NonEmptyStr
    price: PositiveDecimal
    quantity: PositiveDecimal
    venue: NonEmptyStr

    @model_validator(mode="after")
    def validate_availability(self):
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        return self


class VenueStatusEvent(TimeAwareModel):
    event_type: Literal[MarketEventType.VENUE_STATUS] = MarketEventType.VENUE_STATUS
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    venue: NonEmptyStr
    state: VenueState

    @model_validator(mode="after")
    def validate_availability(self):
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        return self


MarketEvent = Annotated[Union[QuoteEvent, TradeEvent, VenueStatusEvent], Field(discriminator="event_type")]

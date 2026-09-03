from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import (
    CandidateAllocation, CurrentPosition, CurrentVirtualPosition, OpenOrderExposure,
)
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import canonicalize
from quant_pipeline.phase_08_portfolio_control.foundation.models import utc
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import Quote


def test_current_virtual_must_reconcile_with_physical(stock_bundle):
    with pytest.raises(ValidationError, match="current virtual positions"):
        stock_bundle.__class__(**{
            **stock_bundle.model_dump(mode="python"),
            "current_positions": (CurrentPosition(instrument_id="AAPL", quantity=Decimal("1")),),
            "current_virtual_positions": (),
        })


def test_open_order_allocations_must_reconcile():
    with pytest.raises(ValidationError, match="open-order virtual allocations"):
        OpenOrderExposure(
            order_id="o", instrument_id="AAPL", remaining_signed_quantity=Decimal("2"),
            virtual_allocations=(CandidateAllocation(candidate_id="c", allocated_target_quantity=Decimal("1")),),
        )


def test_crossed_quote_is_rejected(stock_market):
    quote = stock_market.quotes[0]
    with pytest.raises(ValidationError, match="crossed quote"):
        Quote(**{**quote.model_dump(mode="python"), "bid_price": Decimal("102")})


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        utc(datetime(2026, 1, 1))


def test_unsupported_canonical_type_is_rejected():
    with pytest.raises(Exception, match="unsupported canonical type"):
        canonicalize(object())

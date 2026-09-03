from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.adapters.alpaca_activity_mapper import (
    AlpacaActivityContext,
    map_activity,
)
from quant_pipeline.phase_08_portfolio_control.foundation.errors import UnsupportedMappingError
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.accounting_models import (
    CashAdjustmentEvent,
    FeeEvent,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.enums import (
    CashAdjustmentType,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.lifecycle_models import (
    LifecycleCandidateAllocation,
    OptionAssignmentEvent,
    OptionCashSettlementEvent,
    OptionExerciseEvent,
    OptionExpirationEvent,
    SplitEvent,
)

AT = "2026-08-03T18:00:00Z"
DT = datetime(2026, 8, 3, 18, tzinfo=timezone.utc)


def _context(quantity: Decimal = Decimal("1")) -> AlpacaActivityContext:
    return AlpacaActivityContext(
        instrument_id="AAPL_C100",
        contract_quantity=abs(quantity),
        candidate_allocations=(LifecycleCandidateAllocation(
            candidate_id="c1", instrument_id="AAPL_C100",
            signed_contract_quantity=quantity, event_time=DT,
        ),),
    )


@pytest.mark.parametrize(
    ("entry_type", "expected"),
    [
        ("OPEXC", OptionExerciseEvent),
        ("OPASN", OptionAssignmentEvent),
        ("OPEXP", OptionExpirationEvent),
    ],
)
def test_option_activity_mapping(entry_type, expected):
    quantity = Decimal("-1") if entry_type == "OPASN" else Decimal("1")
    event = map_activity(
        {"id": "activity-1", "entry_type": entry_type, "at": AT, "status": "executed"},
        _context(quantity),
    )
    assert isinstance(event, expected)
    assert event.event_time == DT
    assert event.candidate_allocations[0].signed_contract_quantity == quantity


def test_cash_settlement_mapping():
    event = map_activity(
        {"event_ulid": "01ABC", "entry_type": "OPCSH", "at": AT,
         "status": "executed", "net_amount": "500.25"},
        _context(),
    )
    assert isinstance(event, OptionCashSettlementEvent)
    assert event.cash_amount == Decimal("500.25")


def test_split_requires_explicit_reconciled_ratio():
    with pytest.raises(UnsupportedMappingError):
        map_activity(
            {"id": "split", "entry_type": "SPLIT", "at": AT, "status": "executed"},
            AlpacaActivityContext(instrument_id="AAPL"),
        )
    event = map_activity(
        {"id": "split", "entry_type": "SPLIT", "at": AT, "status": "executed"},
        AlpacaActivityContext(
            instrument_id="AAPL", split_ratio_numerator=Decimal("2"),
            split_ratio_denominator=Decimal("1"),
        ),
    )
    assert isinstance(event, SplitEvent)
    assert event.ratio_numerator == Decimal("2")


def test_dividend_interest_and_fee_mapping():
    dividend = map_activity(
        {"id": "div", "entry_type": "DIV", "at": AT,
         "status": "executed", "net_amount": "10.5"},
        AlpacaActivityContext(),
    )
    interest = map_activity(
        {"id": "int", "entry_type": "INT", "at": AT,
         "status": "executed", "net_amount": "2"},
        AlpacaActivityContext(),
    )
    fee = map_activity(
        {"id": "fee", "entry_type": "OCC_FEE", "at": AT,
         "status": "executed", "net_amount": "-1.25"},
        AlpacaActivityContext(),
    )
    assert isinstance(dividend, CashAdjustmentEvent)
    assert dividend.adjustment_type == CashAdjustmentType.DIVIDEND
    assert isinstance(interest, CashAdjustmentEvent)
    assert interest.adjustment_type == CashAdjustmentType.INTEREST
    assert isinstance(fee, FeeEvent)
    assert fee.amount == Decimal("1.25")


def test_revision_nonfinal_and_unknown_activities_fail_closed():
    with pytest.raises(UnsupportedMappingError, match="compensating-event"):
        map_activity(
            {"id": "x", "entry_type": "DIV", "at": AT, "status": "executed",
             "net_amount": "1", "previous_id": "old"},
            AlpacaActivityContext(),
        )
    with pytest.raises(UnsupportedMappingError, match="not final"):
        map_activity(
            {"id": "x", "entry_type": "DIV", "at": AT, "status": "pending",
             "net_amount": "1"},
            AlpacaActivityContext(),
        )
    with pytest.raises(UnsupportedMappingError, match="unsupported"):
        map_activity(
            {"id": "x", "entry_type": "UNKNOWN", "at": AT, "status": "executed"},
            AlpacaActivityContext(),
        )


def test_option_mapping_requires_candidate_context():
    with pytest.raises(UnsupportedMappingError, match="candidate attribution"):
        map_activity(
            {"id": "x", "entry_type": "OPEXC", "at": AT, "status": "executed"},
            AlpacaActivityContext(instrument_id="AAPL_C100", contract_quantity=Decimal("1")),
        )

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tests.agents.a4.conftest import NOW
from tests.agents.a4.s7_regression.unit.test_m02_structure import _option_bundle

from quant_pipeline.phase_08_portfolio_control.adapters.alpaca_mapper import to_order_payload
from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import seal_execution_authorization_bundle
from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderStatus, VenueState
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import (
    m01_intents, m02_structure, m03_routing, m04_costs, m05_engine, m06_reconciliation,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import (
    MarketStateSnapshot, Quote, QuoteEvent,
)


def _combo_case(option_instruments, context, venue_capabilities, policies):
    bundle = _option_bundle(option_instruments)
    auths = tuple(auth.model_copy(update={"price_protection_bps": Decimal("2000")}) for auth in bundle.authorizations)
    bundle = seal_execution_authorization_bundle(bundle.model_copy(update={"authorizations": auths}))
    quotes = (
        Quote(instrument_id=option_instruments[0].instrument_id, event_time=NOW, available_at=NOW,
              bid_price=Decimal("1"), ask_price=Decimal("1.2"), bid_size=Decimal("10"), ask_size=Decimal("10"), venue="SIM"),
        Quote(instrument_id=option_instruments[1].instrument_id, event_time=NOW, available_at=NOW,
              bid_price=Decimal("1"), ask_price=Decimal("1.2"), bid_size=Decimal("10"), ask_size=Decimal("10"), venue="SIM"),
    )
    market = MarketStateSnapshot(snapshot_id="combo", as_of_time=NOW, quotes=quotes, venue_states={"SIM": VenueState.OPEN})
    intents = m01_intents.execute(bundle, context, policies.intent)
    structures = m02_structure.execute(intents, bundle, venue_capabilities, policies.structure)
    orders = m03_routing.execute(intents, structures, bundle, market, venue_capabilities, context, policies.routing)
    events = tuple(
        QuoteEvent(event_id=f"q{idx}", event_time=NOW + timedelta(milliseconds=idx),
                   available_at=NOW + timedelta(milliseconds=idx),
                   quote=quote.model_copy(update={"event_time": NOW + timedelta(milliseconds=idx),
                                                  "available_at": NOW + timedelta(milliseconds=idx)}))
        for idx, quote in enumerate(quotes, 1)
    )
    return bundle, market, intents, orders, events


def test_combo_planning_alpaca_mapping_and_atomic_fill(option_instruments, context, venue_capabilities, policies):
    bundle, market, intents, orders, events = _combo_case(option_instruments, context, venue_capabilities, policies)
    order = orders.orders[0]
    assert order.order_class.value == "MLEG"
    payload = to_order_payload(order)
    assert payload["order_class"] == "mleg"
    assert len(payload["legs"]) == 2
    execution = m05_engine.execute(orders, events, (), bundle, context, policies.execution)
    assert execution.final_status_by_order[order.order_id] == OrderStatus.FILLED
    assert len(execution.fill_events) == 2
    costs = m04_costs.execute(orders, market, bundle, policies.cost)
    receipt = m06_reconciliation.execute(intents, orders, execution, costs, market)
    assert receipt.status.value == "PASS"
    assert len(receipt.candidate_allocations) == 2


def test_combo_requires_all_leg_capacity(option_instruments, context, venue_capabilities, policies):
    bundle, market, _, orders, events = _combo_case(option_instruments, context, venue_capabilities, policies)
    weak_quote = events[1].quote.model_copy(update={"bid_size": Decimal("0.5")})
    weak_event = events[1].model_copy(update={"quote": weak_quote})
    execution = m05_engine.execute(orders, (events[0], weak_event), (), bundle, context, policies.execution)
    assert execution.fill_events == ()
    assert set(execution.final_status_by_order.values()) == {OrderStatus.EXPIRED}

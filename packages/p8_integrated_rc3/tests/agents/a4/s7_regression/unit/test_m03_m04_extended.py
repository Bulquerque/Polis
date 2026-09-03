from __future__ import annotations

from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import seal_execution_authorization_bundle
from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderType, Urgency, VenueState
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents, m02_structure, m03_routing, m04_costs
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import MarketStateSnapshot


def _inputs(stock_bundle, context, venue_capabilities, policies):
    intents = m01_intents.execute(stock_bundle, context, policies.intent)
    structures = m02_structure.execute(intents, stock_bundle, venue_capabilities, policies.structure)
    return intents, structures


def test_closed_venue_blocks_structure(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents, structures = _inputs(stock_bundle, context, venue_capabilities, policies)
    market = stock_market.model_copy(update={"venue_states": {"SIM": VenueState.CLOSED}})
    result = m03_routing.execute(intents, structures, stock_bundle, market, venue_capabilities, context, policies.routing)
    assert result.orders == ()
    assert result.blocked_structure_ids == (structures.structures[0].structure_id,)


def test_missing_quote_blocks_structure_atomically(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents, structures = _inputs(stock_bundle, context, venue_capabilities, policies)
    market = stock_market.model_copy(update={"quotes": ()})
    result = m03_routing.execute(intents, structures, stock_bundle, market, venue_capabilities, context, policies.routing)
    assert result.orders == ()
    assert result.blocked_structure_ids


def test_critical_order_uses_market_when_authorized(stock_bundle, stock_market, context, venue_capabilities, policies):
    target = stock_bundle.targets[0].model_copy(update={"urgency": Urgency.CRITICAL})
    bundle = seal_execution_authorization_bundle(stock_bundle.model_copy(update={"targets": (target,)}))
    intents, structures = _inputs(bundle, context, venue_capabilities, policies)
    routing = policies.routing.model_copy(update={"use_market_for_critical": True})
    result = m03_routing.execute(intents, structures, bundle, stock_market, venue_capabilities, context, routing)
    assert result.orders[0].order_type == OrderType.MARKET
    assert result.orders[0].limit_price is None


def test_no_safe_order_type_raises(stock_bundle, stock_market, context, venue_capabilities, policies):
    auth = stock_bundle.authorizations[0].model_copy(update={"allowed_order_types": (OrderType.STOP,), "allow_market_order": False})
    bundle = seal_execution_authorization_bundle(stock_bundle.model_copy(update={"authorizations": (auth,)}))
    intents, structures = _inputs(bundle, context, venue_capabilities, policies)
    result = m03_routing.execute(intents, structures, bundle, stock_market, venue_capabilities, context, policies.routing)
    assert result.orders == ()
    assert "ROUTING_POLICY_UNSUPPORTED" in result.routing_blocks[0].reason_code


def test_cost_quality_unavailable_without_quote(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents, structures = _inputs(stock_bundle, context, venue_capabilities, policies)
    orders = m03_routing.execute(intents, structures, stock_bundle, stock_market, venue_capabilities, context, policies.routing)
    market = MarketStateSnapshot(snapshot_id="missing", as_of_time=stock_market.as_of_time, quotes=(), venue_states=stock_market.venue_states)
    costs = m04_costs.execute(orders, market, stock_bundle, policies.cost)
    assert all(x.quality.value == "UNAVAILABLE" for x in costs.estimates)

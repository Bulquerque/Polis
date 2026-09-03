from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents, m02_structure, m03_routing, m04_costs


def test_cost_components_sum(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents=m01_intents.execute(stock_bundle,context,policies.intent)
    structures=m02_structure.execute(intents,stock_bundle,venue_capabilities,policies.structure)
    orders=m03_routing.execute(intents,structures,stock_bundle,stock_market,venue_capabilities,context,policies.routing)
    result=m04_costs.execute(orders,stock_market,stock_bundle,policies.cost)
    assert result.estimates
    for estimate in result.estimates:
        assert estimate.total_cost == estimate.components.total
        assert estimate.total_cost >= Decimal("0")

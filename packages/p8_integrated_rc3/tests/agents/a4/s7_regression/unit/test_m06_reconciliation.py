from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents,m02_structure,m03_routing,m04_costs,m05_engine,m06_reconciliation


def test_quantity_conservation(stock_bundle,stock_market,stock_events,context,venue_capabilities,policies):
    i=m01_intents.execute(stock_bundle,context,policies.intent)
    s=m02_structure.execute(i,stock_bundle,venue_capabilities,policies.structure)
    o=m03_routing.execute(i,s,stock_bundle,stock_market,venue_capabilities,context,policies.routing)
    c=m04_costs.execute(o,stock_market,stock_bundle,policies.cost)
    e=m05_engine.execute(o,stock_events,(),stock_bundle,context,policies.execution)
    r=m06_reconciliation.execute(i,o,e,c,stock_market)
    assert all(x.quantity_conserved for x in r.order_reconciliations)
    assert sum((x.signed_quantity_delta for x in r.instrument_position_deltas),Decimal("0"))==Decimal("10")

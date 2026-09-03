from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents, m02_structure, m03_routing


def test_limit_order_and_slicing(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents=m01_intents.execute(stock_bundle,context,policies.intent)
    structures=m02_structure.execute(intents,stock_bundle,venue_capabilities,policies.structure)
    result=m03_routing.execute(intents,structures,stock_bundle,stock_market,venue_capabilities,context,policies.routing)
    assert len(result.orders)==2
    assert sum((x.quantity for x in result.orders), Decimal("0")) == Decimal("10")
    assert all(x.order_type.value=="LIMIT" for x in result.orders)
    assert all(x.limit_price <= Decimal("101") for x in result.orders)


def test_options_use_day_tif(option_instruments, context, venue_capabilities, policies):
    from tests.agents.a4.s7_regression.unit.test_m02_structure import _option_bundle
    from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import MarketStateSnapshot, Quote
    from quant_pipeline.phase_08_portfolio_control.foundation.enums import VenueState
    from tests.agents.a4.conftest import NOW
    bundle=_option_bundle(option_instruments)
    intents=m01_intents.execute(bundle,context,policies.intent)
    structures=m02_structure.execute(intents,bundle,venue_capabilities,policies.structure)
    quotes=tuple(Quote(instrument_id=i.instrument_id,event_time=NOW,available_at=NOW,bid_price=Decimal("1"),ask_price=Decimal("1.2"),bid_size=Decimal("10"),ask_size=Decimal("10"),venue="SIM") for i in option_instruments)
    market=MarketStateSnapshot(snapshot_id="opt",as_of_time=NOW,quotes=quotes,venue_states={"SIM":VenueState.OPEN})
    result=m03_routing.execute(intents,structures,bundle,market,venue_capabilities,context,policies.routing)
    assert result.orders[0].time_in_force.value == "DAY"
    assert result.orders[0].order_class.value == "MLEG"

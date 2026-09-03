import pytest

from quant_pipeline.phase_08_portfolio_control.adapters.alpaca_mapper import map_status,to_order_payload
from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderStatus
from quant_pipeline.phase_08_portfolio_control.foundation.errors import UnsupportedMappingError
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents,m02_structure,m03_routing


def test_status_mapping():
    assert map_status("partially_filled") == OrderStatus.PARTIALLY_FILLED
    assert map_status("filled") == OrderStatus.FILLED
    with pytest.raises(UnsupportedMappingError):
        map_status("mystery")


def test_simple_payload(stock_bundle,stock_market,context,venue_capabilities,policies):
    i=m01_intents.execute(stock_bundle,context,policies.intent)
    s=m02_structure.execute(i,stock_bundle,venue_capabilities,policies.structure)
    o=m03_routing.execute(i,s,stock_bundle,stock_market,venue_capabilities,context,policies.routing)
    payload=to_order_payload(o.orders[0])
    assert payload["client_order_id"] == o.orders[0].client_order_id
    assert payload["time_in_force"] == "day"
    assert payload["order_class"] == "simple"


def test_option_payload_rejects_non_day(option_instruments, context, venue_capabilities, policies):
    from tests.agents.a4.s7_regression.unit.test_combo_execution import _combo_case
    from quant_pipeline.phase_08_portfolio_control.foundation.enums import TimeInForce

    _, _, _, orders, _ = _combo_case(option_instruments, context, venue_capabilities, policies)
    non_day = orders.orders[0].model_copy(update={"time_in_force": TimeInForce.GTC})
    with pytest.raises(UnsupportedMappingError, match="require DAY"):
        to_order_payload(non_day)


def test_mleg_payload_rejects_unsupported_shape(option_instruments, context, venue_capabilities, policies):
    from decimal import Decimal
    from tests.agents.a4.s7_regression.unit.test_combo_execution import _combo_case

    _, _, _, orders, _ = _combo_case(option_instruments, context, venue_capabilities, policies)
    order = orders.orders[0]
    fractional_leg = order.legs[0].model_copy(update={"ratio_quantity": Decimal("0.5")})
    with pytest.raises(UnsupportedMappingError, match="integral"):
        to_order_payload(order.model_copy(update={"legs": (fractional_leg, order.legs[1])}))
    with pytest.raises(UnsupportedMappingError, match="two to four"):
        to_order_payload(order.model_copy(update={"legs": order.legs * 3}))

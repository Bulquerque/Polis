from datetime import timedelta
from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderStatus, RuntimeControlMode, TimeInForce
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents,m02_structure,m03_routing,m05_engine
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import RuntimeControlCommand
from tests.agents.a4.conftest import NOW


def _orders(stock_bundle,stock_market,context,venue_capabilities,policies):
    i=m01_intents.execute(stock_bundle,context,policies.intent)
    s=m02_structure.execute(i,stock_bundle,venue_capabilities,policies.structure)
    return m03_routing.execute(i,s,stock_bundle,stock_market,venue_capabilities,context,policies.routing)


def test_sliced_orders_fill_across_events(stock_bundle,stock_market,stock_events,context,venue_capabilities,policies):
    orders=_orders(stock_bundle,stock_market,context,venue_capabilities,policies)
    result=m05_engine.execute(orders,stock_events,(),stock_bundle,context,policies.execution)
    assert len(result.fill_events)==2
    assert all(status==OrderStatus.FILLED for status in result.final_status_by_order.values())


def test_cancel_all_runtime_command(stock_bundle,stock_market,context,venue_capabilities,policies):
    orders=_orders(stock_bundle,stock_market,context,venue_capabilities,policies)
    cmd=RuntimeControlCommand(command_id="rc1",event_time=NOW+timedelta(milliseconds=1),mode=RuntimeControlMode.CANCEL_OPEN_ORDERS,reason_code="RUNTIME_RISK")
    result=m05_engine.execute(orders,(),(cmd,),stock_bundle,context,policies.execution)
    assert all(status==OrderStatus.CANCELLED for status in result.final_status_by_order.values())


def test_ioc_cancels_remainder(stock_bundle,stock_market,stock_events,context,venue_capabilities,policies):
    orders=_orders(stock_bundle,stock_market,context,venue_capabilities,policies)
    first=orders.orders[0].model_copy(update={"time_in_force":TimeInForce.IOC,"quantity":Decimal("10")})
    orders=orders.model_copy(update={"orders":(first,)})
    result=m05_engine.execute(orders,(stock_events[0],),(),stock_bundle,context,policies.execution)
    assert result.final_status_by_order[first.order_id] == OrderStatus.CANCELLED
    assert result.fill_events[0].quantity == Decimal("6")


def test_deterministic_events(stock_bundle,stock_market,stock_events,context,venue_capabilities,policies):
    orders=_orders(stock_bundle,stock_market,context,venue_capabilities,policies)
    a=m05_engine.execute(orders,stock_events,(),stock_bundle,context,policies.execution)
    b=m05_engine.execute(orders,stock_events,(),stock_bundle,context,policies.execution)
    assert a==b

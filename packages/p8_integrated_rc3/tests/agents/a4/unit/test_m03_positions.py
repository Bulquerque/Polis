from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine import m01_timeline, m02_execution_state, m03_positions


def test_linear_fill_updates_dual_book(s8_linear_input):
    queue=m01_timeline.execute(s8_linear_input)
    execution=m02_execution_state.execute(s8_linear_input,queue)
    result=m03_positions.execute(s8_linear_input,queue,execution)
    assert result.physical_positions[0].quantity==Decimal("10")
    assert result.physical_positions[0].signed_cost_basis==Decimal("1010")
    assert result.virtual_positions[0].quantity==Decimal("10")
    assert result.virtual_positions[0].signed_cost_basis==Decimal("1010")
    assert sum((x.quantity for x in result.virtual_positions),Decimal("0"))==result.physical_positions[0].quantity

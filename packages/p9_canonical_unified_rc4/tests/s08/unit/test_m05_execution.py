import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass
from quant_pipeline.phase_09.subphases.s08_attribution.m05_execution_attribution import ExecutionAttributionPolicy, ExecutionRecord, LifecycleEvent, OrderSide, attribute_execution_and_lifecycle


def test_full_fill_zero_shortfall():
    record=ExecutionRecord(order_id="o", side=OrderSide.BUY, target_quantity=1, ordered_quantity=1, filled_quantity=1, decision_price=10, arrival_price=10, average_fill_price=10, evaluation_price=10, evidence_class=EvidenceClass.FACTUAL_EXECUTED)
    result=attribute_execution_and_lifecycle((record,), (), ExecutionAttributionPolicy())
    assert result.total_shortfall == 0.0
    assert result.aggregate_pnl_effect == 0.0


def test_no_fill_has_opportunity_cost():
    record=ExecutionRecord(order_id="o", side=OrderSide.BUY, target_quantity=2, ordered_quantity=2, filled_quantity=0, decision_price=10, arrival_price=10.5, evaluation_price=12, evidence_class=EvidenceClass.FACTUAL_EXECUTED)
    result=attribute_execution_and_lifecycle((record,), (), ExecutionAttributionPolicy())
    assert result.orders[0].opportunity_cost == 4.0
    assert result.orders[0].fill_rate == 0.0


def test_sell_shortfall_sign():
    record=ExecutionRecord(order_id="o", side=OrderSide.SELL, target_quantity=1, ordered_quantity=1, filled_quantity=1, decision_price=10, arrival_price=9, average_fill_price=8, evaluation_price=8, evidence_class=EvidenceClass.FACTUAL_EXECUTED)
    result=attribute_execution_and_lifecycle((record,), (), ExecutionAttributionPolicy())
    assert result.total_delay_cost == 1.0
    assert result.total_trading_cost == 1.0


def test_lifecycle_deviation_is_reported():
    event=LifecycleEvent(position_id="p", planned_event="HOLD", actual_event="ASSIGN", planned_pnl=0, actual_pnl=-2, evidence_class=EvidenceClass.FACTUAL_EXECUTED)
    result=attribute_execution_and_lifecycle((), (event,), ExecutionAttributionPolicy())
    assert result.lifecycle_pnl_effect == -2.0
    assert "P9_ATTRIBUTION_LIFECYCLE_DEVIATION" in result.reason_codes


def test_combo_cannot_have_legging_cost():
    with pytest.raises(ValueError):
        ExecutionRecord(order_id="o", side=OrderSide.BUY, target_quantity=1, ordered_quantity=1, filled_quantity=1, decision_price=10, arrival_price=10, average_fill_price=10, evaluation_price=10, combo_execution=True, legging_cost=1, evidence_class=EvidenceClass.FACTUAL_EXECUTED)

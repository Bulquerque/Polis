from __future__ import annotations

from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.foundation.errors import ReconciliationError
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import (
    m01_intents, m02_structure, m03_routing, m04_costs, m05_engine, m06_reconciliation,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import FillEvent


def _pipeline(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    intents = m01_intents.execute(stock_bundle, context, policies.intent)
    structures = m02_structure.execute(intents, stock_bundle, venue_capabilities, policies.structure)
    orders = m03_routing.execute(intents, structures, stock_bundle, stock_market, venue_capabilities, context, policies.routing)
    costs = m04_costs.execute(orders, stock_market, stock_bundle, policies.cost)
    execution = m05_engine.execute(orders, stock_events, (), stock_bundle, context, policies.execution)
    return intents, orders, costs, execution


def test_orphan_fill_is_rejected(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    intents, orders, costs, execution = _pipeline(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies)
    fill = execution.fill_events[0].model_copy(update={"fill_id": "orphan", "order_id": "unknown"})
    corrupted = execution.model_copy(update={"fill_events": execution.fill_events + (fill,)})
    with pytest.raises(ReconciliationError, match="orphan fill"):
        m06_reconciliation.execute(intents, orders, corrupted, costs, stock_market)


def test_virtual_only_reallocation_reaches_receipt(stock_bundle, stock_instrument, stock_market, context, venue_capabilities, policies):
    from tests.agents.a4.conftest import make_bundle
    from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import CandidateAllocation, CurrentPosition, CurrentVirtualPosition
    target = stock_bundle.targets[0].model_copy(update={
        "target_quantity": Decimal("10"),
        "virtual_allocations": (
            CandidateAllocation(candidate_id="c1", allocated_target_quantity=Decimal("4")),
            CandidateAllocation(candidate_id="c2", allocated_target_quantity=Decimal("6")),
        ),
    })
    bundle = make_bundle(
        (target,), stock_bundle.authorizations, (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("10")),),
        virtual_positions=(CurrentVirtualPosition(candidate_id="c1", instrument_id="AAPL", quantity=Decimal("10")),),
    )
    intents = m01_intents.execute(bundle, context, policies.intent)
    structures = m02_structure.execute(intents, bundle, venue_capabilities, policies.structure)
    orders = m03_routing.execute(intents, structures, bundle, stock_market, venue_capabilities, context, policies.routing)
    costs = m04_costs.execute(orders, stock_market, bundle, policies.cost)
    execution = m05_engine.execute(orders, (), (), bundle, context, policies.execution)
    receipt = m06_reconciliation.execute(intents, orders, execution, costs, stock_market)
    assert receipt.status.value == "PASS"
    assert receipt.candidate_allocations == ()
    assert {(x.candidate_id, x.signed_quantity_delta) for x in receipt.virtual_reallocations} == {
        ("c1", Decimal("-6")), ("c2", Decimal("6"))
    }

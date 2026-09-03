from decimal import Decimal
import random

import pytest

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import seal_execution_authorization_bundle

from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents,m02_structure,m03_routing


@pytest.mark.property
def test_larger_cost_policy_does_not_change_order_quantity(stock_bundle,stock_market,context,venue_capabilities,policies):
    i=m01_intents.execute(stock_bundle,context,policies.intent)
    s=m02_structure.execute(i,stock_bundle,venue_capabilities,policies.structure)
    a=m03_routing.execute(i,s,stock_bundle,stock_market,venue_capabilities,context,policies.routing)
    b=m03_routing.execute(i,s,stock_bundle,stock_market,venue_capabilities,context,policies.routing)
    assert sum(x.quantity for x in a.orders)==sum(x.quantity for x in b.orders)


@pytest.mark.property
def test_intent_permutation_invariance(stock_bundle,context,policies):
    base=m01_intents.execute(stock_bundle,context,policies.intent)
    shuffled=seal_execution_authorization_bundle(stock_bundle.model_copy(update={"targets":tuple(reversed(stock_bundle.targets))}))
    other=m01_intents.execute(shuffled,context,policies.intent)
    assert base==other


@pytest.mark.property
def test_random_slicing_conserves_quantity(stock_bundle,stock_market,context,venue_capabilities,policies):
    for quantity in range(1,31):
        target=stock_bundle.targets[0].model_copy(update={
            "target_quantity":Decimal(quantity),
            "virtual_allocations":(stock_bundle.targets[0].virtual_allocations[0].model_copy(update={"allocated_target_quantity":Decimal(quantity)}),),
        })
        changed=seal_execution_authorization_bundle(stock_bundle.model_copy(update={"targets":(target,)}))
        i=m01_intents.execute(changed,context,policies.intent)
        s=m02_structure.execute(i,changed,venue_capabilities,policies.structure)
        o=m03_routing.execute(i,s,changed,stock_market,venue_capabilities,context,policies.routing)
        assert sum(x.quantity for x in o.orders)==Decimal(quantity)

from __future__ import annotations

from pydantic import Field

from ...contracts.execution_authorization import P8ExecutionAuthorizationBundle
from ...foundation.context import ModuleExecutionContext
from ...foundation.models import StrictModel
from . import m01_intents, m02_structure, m03_routing, m04_costs, m05_engine, m06_reconciliation
from .models import (
    ExecutionCommand,
    ExecutionReceipt,
    ExecutionResult,
    ExecutionStructureBundle,
    MarketEvent,
    MarketStateSnapshot,
    OrderIntentBundle,
    PlannedOrderBundle,
    PretradeCostBundle,
    VenueCapabilities,
)
from .policies import S7PolicyBundle


class S7Result(StrictModel):
    intents: OrderIntentBundle
    structures: ExecutionStructureBundle
    planned_orders: PlannedOrderBundle
    pretrade_costs: PretradeCostBundle
    execution: ExecutionResult
    receipt: ExecutionReceipt


def run(
    authorization_bundle: P8ExecutionAuthorizationBundle,
    market_snapshot: MarketStateSnapshot,
    market_events: tuple[MarketEvent, ...],
    commands: tuple[ExecutionCommand, ...],
    venue_capabilities: tuple[VenueCapabilities, ...],
    policies: S7PolicyBundle,
    context: ModuleExecutionContext,
) -> S7Result:
    intents = m01_intents.execute(authorization_bundle, context, policies.intent)
    structures = m02_structure.execute(intents, authorization_bundle, venue_capabilities, policies.structure)
    planned = m03_routing.execute(
        intents, structures, authorization_bundle, market_snapshot,
        venue_capabilities, context, policies.routing,
    )
    costs = m04_costs.execute(planned, market_snapshot, authorization_bundle, policies.cost)
    execution = m05_engine.execute(
        planned, market_events, commands, authorization_bundle, context, policies.execution,
    )
    receipt = m06_reconciliation.execute(intents, planned, execution, costs, market_snapshot)
    return S7Result(
        intents=intents,
        structures=structures,
        planned_orders=planned,
        pretrade_costs=costs,
        execution=execution,
        receipt=receipt,
    )

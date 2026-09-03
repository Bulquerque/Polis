from datetime import timedelta
from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import CandidateAllocation, ExecutableTarget, ExecutionAuthorization
from quant_pipeline.phase_08_portfolio_control.foundation.enums import AuthorizationStatus, OrderType, PositionIntent, RiskRole, TimeInForce, Urgency
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents, m02_structure
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.policies import IntentPolicy, StructurePolicy
from tests.agents.a4.conftest import NOW, make_bundle


def _option_bundle(option_instruments, allow_legging=True, allow_unwind=True):
    targets=[]; auths=[]
    for i,(inst,qty,role,pi) in enumerate([
        (option_instruments[0], Decimal("1"), RiskRole.PROTECTIVE, PositionIntent.BUY_TO_OPEN),
        (option_instruments[1], Decimal("-1"), RiskRole.RISK_INCREASING, PositionIntent.SELL_TO_OPEN),
    ],1):
        targets.append(ExecutableTarget(
            target_id=f"t{i}", authorization_id=f"a{i}", execution_group_id="spread", instrument_id=inst.instrument_id,
            target_quantity=qty, urgency=Urgency.NORMAL, risk_role=role, position_intent=pi,
            virtual_allocations=(CandidateAllocation(candidate_id="spread-c", allocated_target_quantity=qty),),
        ))
        auths.append(ExecutionAuthorization(
            authorization_id=f"a{i}", target_id=f"t{i}", status=AuthorizationStatus.AUTHORIZED,
            valid_until=NOW+timedelta(hours=1), allowed_order_types=(OrderType.LIMIT,),
            allowed_time_in_force=(TimeInForce.DAY,), allow_legging=allow_legging, allow_unwind=allow_unwind,
            max_temporary_notional=Decimal("1000"), max_participation_rate=Decimal("1"),
            price_protection_bps=Decimal("10"), preferred_venues=("SIM",),
        ))
    return make_bundle(targets,auths,option_instruments)


def test_prefers_combo(option_instruments, context, venue_capabilities):
    bundle=_option_bundle(option_instruments)
    intents=m01_intents.execute(bundle, context, IntentPolicy())
    result=m02_structure.execute(intents,bundle,venue_capabilities,StructurePolicy(prefer_combo=True))
    assert result.structures[0].structure_type.value == "COMBO"


def test_safe_legging_orders_protective_first(option_instruments, context, venue_capabilities):
    bundle=_option_bundle(option_instruments)
    intents=m01_intents.execute(bundle, context, IntentPolicy())
    no_combo=tuple(x.model_copy(update={"supports_combo":False}) for x in venue_capabilities)
    result=m02_structure.execute(intents,bundle,no_combo,StructurePolicy())
    structure=result.structures[0]
    assert structure.structure_type.value == "LEGGING"
    protective=next(x.intent_id for x in intents.intents if x.risk_role.value=="PROTECTIVE")
    assert structure.sequence[0] == protective


def test_blocks_legging_without_unwind(option_instruments, context, venue_capabilities):
    bundle=_option_bundle(option_instruments, allow_unwind=False)
    intents=m01_intents.execute(bundle, context, IntentPolicy())
    no_combo=tuple(x.model_copy(update={"supports_combo":False}) for x in venue_capabilities)
    result=m02_structure.execute(intents,bundle,no_combo,StructurePolicy())
    assert result.structures[0].structure_type.value == "BLOCKED"

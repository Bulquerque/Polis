from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from ...contracts.execution_authorization import CandidateAllocation, P8ExecutionAuthorizationBundle, execution_authorization_payload_hash
from ...foundation.context import ModuleExecutionContext
from ...foundation.enums import IntentType, PositionIntent, Side
from ...foundation.errors import AuthorizationError, ContractIntegrityError, TemporalIntegrityError
from ...foundation.hashing import content_sha256, deterministic_id
from .models import OrderIntent, OrderIntentBundle, VirtualReallocation
from .policies import IntentPolicy

MODULE_ID = "P8.S7.M01"


@dataclass(frozen=True, slots=True)
class _IntentState:
    instruments: dict
    positions: dict[str, Decimal]
    current_virtual: dict[tuple[str, str], Decimal]
    open_effects: dict[str, Decimal]
    open_virtual: dict[tuple[str, str], Decimal]
    authorizations: dict


def _intent_type(current: Decimal, target: Decimal) -> IntentType:
    if current == target:
        raise ValueError("zero delta has no intent type")
    if current == 0:
        return IntentType.OPEN
    if target == 0 or current * target < 0:
        return IntentType.CLOSE
    if abs(target) > abs(current):
        return IntentType.INCREASE
    return IntentType.REDUCE


def _position_intent(current: Decimal, signed_delta: Decimal) -> PositionIntent:
    side = Side.BUY if signed_delta > 0 else Side.SELL
    if side == Side.BUY:
        return PositionIntent.BUY_TO_CLOSE if current < 0 else PositionIntent.BUY_TO_OPEN
    return PositionIntent.SELL_TO_CLOSE if current > 0 else PositionIntent.SELL_TO_OPEN


def _validate_bundle(bundle: P8ExecutionAuthorizationBundle, context: ModuleExecutionContext) -> None:
    if execution_authorization_payload_hash(bundle) != bundle.content_sha256:
        raise ContractIntegrityError("execution authorization bundle hash mismatch")
    if context.run_id != bundle.run_id or context.cycle_id != bundle.cycle_id:
        raise AuthorizationError("context run/cycle must equal authorization bundle")
    if context.decision_time != bundle.decision_time:
        raise TemporalIntegrityError("context decision_time must equal bundle decision_time")
    if bundle.valid_until <= context.decision_time:
        raise AuthorizationError("execution authorization bundle is expired")


def _build_state(bundle: P8ExecutionAuthorizationBundle) -> _IntentState:
    current_virtual: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for item in bundle.current_virtual_positions:
        current_virtual[(item.candidate_id, item.instrument_id)] += item.quantity
    open_effects: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    open_virtual: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for item in bundle.open_orders:
        open_effects[item.instrument_id] += item.remaining_signed_quantity
        for allocation in item.virtual_allocations:
            open_virtual[(allocation.candidate_id, item.instrument_id)] += allocation.allocated_target_quantity
    return _IntentState(
        instruments={item.instrument_id: item for item in bundle.instruments},
        positions={item.instrument_id: item.quantity for item in bundle.current_positions},
        current_virtual=current_virtual,
        open_effects=open_effects,
        open_virtual=open_virtual,
        authorizations={item.authorization_id: item for item in bundle.authorizations},
    )


def _virtual_deltas(target, state: _IntentState) -> tuple[CandidateAllocation, ...]:
    desired = {item.candidate_id: item.allocated_target_quantity for item in target.virtual_allocations}
    candidate_ids = desired.keys() | {
        candidate_id for candidate_id, instrument_id in state.current_virtual if instrument_id == target.instrument_id
    } | {
        candidate_id for candidate_id, instrument_id in state.open_virtual if instrument_id == target.instrument_id
    }
    return tuple(
        CandidateAllocation(candidate_id=candidate_id, allocated_target_quantity=delta)
        for candidate_id in sorted(candidate_ids)
        if (delta := desired.get(candidate_id, Decimal("0"))
            - state.current_virtual[(candidate_id, target.instrument_id)]
            - state.open_virtual[(candidate_id, target.instrument_id)]) != 0
    )


def _reallocations(bundle_id: str, target, deltas: tuple[CandidateAllocation, ...]) -> tuple[VirtualReallocation, ...]:
    return tuple(
        VirtualReallocation(
            reallocation_id=deterministic_id(
                "virtual-reallocation", bundle_id, target.target_id,
                allocation.candidate_id, allocation.allocated_target_quantity,
            ),
            instrument_id=target.instrument_id,
            candidate_id=allocation.candidate_id,
            signed_quantity_delta=allocation.allocated_target_quantity,
        )
        for allocation in deltas
    )


def _build_intent(bundle, target, projected: Decimal, delta: Decimal, virtual_deltas, state, context) -> OrderIntent:
    if projected * target.target_quantity < 0:
        raise AuthorizationError(f"zero-crossing target requires close-to-zero and reauthorization: {target.target_id}")
    instrument = state.instruments[target.instrument_id]
    if context.decision_time < instrument.valid_from or (
        instrument.valid_until is not None and context.decision_time >= instrument.valid_until
    ):
        raise AuthorizationError(f"instrument contract not valid: {instrument.instrument_id}")
    return OrderIntent(
        intent_id=deterministic_id("intent", bundle.bundle_id, target.target_id, delta),
        target_id=target.target_id,
        authorization_id=target.authorization_id,
        execution_group_id=target.execution_group_id,
        instrument_id=target.instrument_id,
        security_type=instrument.security_type,
        intent_type=_intent_type(projected, target.target_quantity),
        position_intent=_position_intent(projected, delta),
        side=Side.BUY if delta > 0 else Side.SELL,
        quantity=abs(delta),
        signed_quantity=delta,
        urgency=target.urgency,
        risk_role=target.risk_role,
        leg_priority=target.leg_priority,
        virtual_allocations=virtual_deltas,
    )


def _process_target(bundle, target, context, policy, state):
    authorization = state.authorizations[target.authorization_id]
    if authorization.valid_until <= context.decision_time:
        raise AuthorizationError(f"authorization expired: {authorization.authorization_id}")
    projected = state.positions.get(target.instrument_id, Decimal("0")) + state.open_effects[target.instrument_id]
    delta = target.target_quantity - projected
    deltas = _virtual_deltas(target, state)
    if sum((item.allocated_target_quantity for item in deltas), Decimal("0")) != delta:
        raise ContractIntegrityError(f"virtual delta does not reconcile to physical delta: {target.target_id}")
    if abs(delta) <= policy.zero_tolerance:
        return None, _reallocations(bundle.bundle_id, target, deltas)
    return _build_intent(bundle, target, projected, delta, deltas, state, context), ()


def execute(
    bundle: P8ExecutionAuthorizationBundle,
    context: ModuleExecutionContext,
    policy: IntentPolicy,
) -> OrderIntentBundle:
    _validate_bundle(bundle, context)
    state = _build_state(bundle)
    intents: list[OrderIntent] = []
    reallocations: list[VirtualReallocation] = []
    for target in sorted(bundle.targets, key=lambda item: item.target_id):
        intent, virtual_only = _process_target(bundle, target, context, policy, state)
        if intent is not None:
            intents.append(intent)
        reallocations.extend(virtual_only)
    intent_rows, reallocation_rows = tuple(intents), tuple(reallocations)
    hash_payload = {"intents": intent_rows, "virtual_reallocations": reallocation_rows}
    return OrderIntentBundle(
        bundle_id=deterministic_id("intent-bundle", bundle.bundle_id, hash_payload),
        intents=intent_rows,
        virtual_reallocations=reallocation_rows,
        no_action=not intent_rows and not reallocation_rows,
        content_sha256=content_sha256(hash_payload),
    )

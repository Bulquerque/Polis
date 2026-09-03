from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ...contracts.execution_authorization import P8ExecutionAuthorizationBundle
from ...foundation.enums import IntentType, RiskRole, StructureType
from ...foundation.hashing import content_sha256, deterministic_id
from .models import ExecutionStructureBundle, ExecutionStructurePlan, OrderIntent, OrderIntentBundle, TemporaryRiskBudget, VenueCapabilities
from .policies import StructurePolicy

MODULE_ID = "P8.S7.M02"


def _legging_rank(intent: OrderIntent) -> tuple[int, int, str]:
    closing = intent.intent_type in {IntentType.CLOSE, IntentType.REDUCE}
    roles = (
        {RiskRole.RISK_INCREASING: 0, RiskRole.NEUTRAL: 1, RiskRole.RISK_REDUCING: 2, RiskRole.PROTECTIVE: 3}
        if closing else
        {RiskRole.PROTECTIVE: 0, RiskRole.RISK_REDUCING: 1, RiskRole.NEUTRAL: 2, RiskRole.RISK_INCREASING: 3}
    )
    return roles[intent.risk_role], intent.leg_priority, intent.intent_id


def _plan(group_id, group, auths, capability_by_venue, policy) -> ExecutionStructurePlan:
    group = sorted(group, key=lambda item: item.intent_id)
    preferred = tuple(dict.fromkeys(
        venue for item in group for venue in auths[item.authorization_id].preferred_venues
    ))
    selected = next((venue for venue in preferred if venue in capability_by_venue), None)
    max_temp = min((auths[item.authorization_id].max_temporary_notional for item in group), default=Decimal("0"))
    intent_ids = tuple(item.intent_id for item in group)
    if len(group) == 1:
        return ExecutionStructurePlan(
            structure_id=deterministic_id("structure", group_id, "single"), execution_group_id=group_id,
            structure_type=StructureType.SINGLE, intent_ids=intent_ids, venue=selected,
            sequence=intent_ids, temporary_risk_budget=TemporaryRiskBudget(max_temporary_notional=Decimal("0"), unwind_required=False),
        )
    combo_venue = next((
        venue for venue in preferred
        if venue in capability_by_venue and capability_by_venue[venue].supports_combo
    ), None)
    if policy.prefer_combo and combo_venue is not None:
        return ExecutionStructurePlan(
            structure_id=deterministic_id("structure", group_id, "combo"), execution_group_id=group_id,
            structure_type=StructureType.COMBO, intent_ids=intent_ids, venue=combo_venue,
            sequence=intent_ids, temporary_risk_budget=TemporaryRiskBudget(max_temporary_notional=Decimal("0"), unwind_required=False),
        )
    can_leg = all(auths[item.authorization_id].allow_legging for item in group)
    can_unwind = all(auths[item.authorization_id].allow_unwind for item in group)
    if not can_leg or (policy.require_unwind_for_legging and not can_unwind) or max_temp <= 0:
        return ExecutionStructurePlan(
            structure_id=deterministic_id("structure", group_id, "blocked"), execution_group_id=group_id,
            structure_type=StructureType.BLOCKED, intent_ids=intent_ids, venue=selected, sequence=(),
            temporary_risk_budget=TemporaryRiskBudget(max_temporary_notional=max_temp, unwind_required=True),
            block_reason="LEGGING_CONTINGENCY_UNAVAILABLE",
        )
    sequence = tuple(item.intent_id for item in sorted(group, key=_legging_rank))
    return ExecutionStructurePlan(
        structure_id=deterministic_id("structure", group_id, "legging", sequence), execution_group_id=group_id,
        structure_type=StructureType.LEGGING, intent_ids=intent_ids, venue=selected, sequence=sequence,
        temporary_risk_budget=TemporaryRiskBudget(max_temporary_notional=max_temp, unwind_required=True),
    )


def execute(
    intents: OrderIntentBundle,
    bundle: P8ExecutionAuthorizationBundle,
    capabilities: tuple[VenueCapabilities, ...],
    policy: StructurePolicy,
) -> ExecutionStructureBundle:
    auths = {item.authorization_id: item for item in bundle.authorizations}
    capability_by_venue = {item.venue: item for item in capabilities}
    grouped: dict[str, list[OrderIntent]] = defaultdict(list)
    for intent in intents.intents:
        grouped[intent.execution_group_id].append(intent)
    payload = tuple(
        _plan(group_id, group, auths, capability_by_venue, policy)
        for group_id, group in sorted(grouped.items())
    )
    return ExecutionStructureBundle(structures=payload, content_sha256=content_sha256(payload))

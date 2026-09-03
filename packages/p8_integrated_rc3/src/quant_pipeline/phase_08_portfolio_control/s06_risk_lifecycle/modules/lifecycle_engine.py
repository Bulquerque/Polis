from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import DecisionReadyRiskBundle

from ..domain.target import first_horizon_target_portfolio
from ..models.artifacts import LifecycleLegDecision, LifecyclePlan
from ..models.enums import (
    CandidateType,
    InstrumentType,
    LifecycleAction,
    LifecycleStatus,
    OptionStyle,
    PositionSide,
    SettlementType,
)
from ..models.inputs import CandidateLifecycleInput, LifecycleLegInput
from ..models.policies import LifecyclePolicy


def _decision(
    *,
    candidate_id: str,
    leg: LifecycleLegInput,
    quantity: float,
    now: datetime,
    action: LifecycleAction,
    reasons: tuple[str, ...] = (),
) -> LifecycleLegDecision:
    return LifecycleLegDecision(
        candidate_id=candidate_id,
        leg_id=leg.leg_id,
        instrument_id=leg.instrument_id,
        action=action,
        quantity=quantity * leg.quantity_per_candidate_unit,
        effective_at=now,
        reason_codes=reasons,
    )


def _expired_action(leg: LifecycleLegInput) -> tuple[LifecycleAction, tuple[str, ...]]:
    if leg.settlement_type == SettlementType.CASH and leg.settlement_supported:
        return LifecycleAction.CASH_SETTLE, ("EXPIRY_CASH_SETTLEMENT",)
    if leg.side == PositionSide.LONG and leg.intrinsic_value_per_unit > 0 and leg.exercise_supported:
        return LifecycleAction.EXERCISE, ("EXPIRY_EXERCISE",)
    if leg.side == PositionSide.SHORT and leg.assignment_supported:
        return LifecycleAction.ALLOW_ASSIGNMENT, ("EXPIRY_ASSIGNMENT",)
    if leg.settlement_type == SettlementType.PHYSICAL and leg.settlement_supported:
        return LifecycleAction.PHYSICAL_SETTLE, ("EXPIRY_PHYSICAL_SETTLEMENT",)
    return LifecycleAction.UNSUPPORTED, ("EXPIRY_ACTION_UNSUPPORTED",)


def _early_exercise_action(
    leg: LifecycleLegInput,
    policy: LifecyclePolicy,
) -> tuple[LifecycleAction, tuple[str, ...]] | None:
    if leg.side != PositionSide.LONG or leg.option_style != OptionStyle.AMERICAN:
        return None
    if not policy.allow_american_early_exercise or not leg.exercise_supported:
        return None
    if leg.dividend_present_value_per_unit is None or leg.exercise_fee_per_unit is None:
        return LifecycleAction.UNSUPPORTED, ("OPTION_EXERCISE_ECONOMICS_UNAVAILABLE",)
    benefit = (
        leg.intrinsic_value_per_unit
        + leg.dividend_present_value_per_unit
        - leg.mark_value_per_unit
        - leg.exercise_fee_per_unit
    )
    if benefit < policy.minimum_early_exercise_benefit:
        return None
    return LifecycleAction.EXERCISE, ("EARLY_EXERCISE_BENEFIT",)


def _assignment_prevention_action(
    leg: LifecycleLegInput,
    policy: LifecyclePolicy,
) -> tuple[LifecycleAction, tuple[str, ...]] | None:
    if leg.side != PositionSide.SHORT or not policy.prevent_short_assignment_if_possible:
        return None
    assignment_risk = (
        leg.intrinsic_value_per_unit >= policy.minimum_assignment_risk_intrinsic
        and leg.time_value_per_unit <= policy.maximum_time_value_for_assignment_risk
    )
    if not assignment_risk or not leg.close_supported:
        return None
    return LifecycleAction.PREVENT_ASSIGNMENT, ("ASSIGNMENT_RISK",)


def _expiry_window_action(
    leg: LifecycleLegInput,
    remaining_seconds: float,
    policy: LifecyclePolicy,
) -> tuple[LifecycleAction, tuple[str, ...]]:
    if remaining_seconds <= policy.close_before_expiry_seconds and leg.close_supported:
        return LifecycleAction.CLOSE, ("CLOSE_WINDOW",)
    if remaining_seconds <= policy.roll_before_expiry_seconds and leg.roll_supported:
        return LifecycleAction.ROLL, ("ROLL_WINDOW",)
    return LifecycleAction.HOLD, ()


def _option_action(
    leg: LifecycleLegInput,
    now: datetime,
    policy: LifecyclePolicy,
) -> tuple[LifecycleAction, tuple[str, ...]]:
    if leg.expiration_at is None:
        return LifecycleAction.UNSUPPORTED, ("OPTION_EXPIRATION_MISSING",)
    remaining_seconds = (leg.expiration_at - now).total_seconds()
    if remaining_seconds <= 0:
        return _expired_action(leg)
    early_exercise = _early_exercise_action(leg, policy)
    if early_exercise is not None:
        return early_exercise
    assignment_prevention = _assignment_prevention_action(leg, policy)
    if assignment_prevention is not None:
        return assignment_prevention
    return _expiry_window_action(leg, remaining_seconds, policy)


def _decide_leg(
    candidate_id: str,
    leg: LifecycleLegInput,
    quantity: float,
    now: datetime,
    policy: LifecyclePolicy,
) -> LifecycleLegDecision:
    if leg.instrument_type != InstrumentType.OPTION:
        return _decision(
            candidate_id=candidate_id,
            leg=leg,
            quantity=quantity,
            now=now,
            action=LifecycleAction.HOLD,
        )
    action, reasons = _option_action(leg, now, policy)
    return _decision(
        candidate_id=candidate_id,
        leg=leg,
        quantity=quantity,
        now=now,
        action=action,
        reasons=reasons,
    )


def _hash_plan(plan: LifecyclePlan) -> LifecyclePlan:
    unhashed = plan.model_copy(update={"plan_hash": "0" * 64})
    return plan.model_copy(update={"plan_hash": canonical_sha256(unhashed)})


def _no_action_plan() -> LifecyclePlan:
    return _hash_plan(
        LifecyclePlan(
            status=LifecycleStatus.NO_ACTION_VALID,
            decisions=(),
            plan_hash="0" * 64,
            reason_codes=("NO_ACTION_VALID",),
        )
    )


def _target_decisions(
    *,
    target: dict[str, float],
    context_map: dict[str, CandidateLifecycleInput],
    policy: LifecyclePolicy,
    now: datetime,
) -> tuple[list[LifecycleLegDecision], set[str]]:
    decisions: list[LifecycleLegDecision] = []
    unsupported: set[str] = set()
    for candidate_id, quantity in target.items():
        if abs(quantity) <= 1e-12:
            continue
        context = context_map.get(candidate_id)
        if context is None:
            continue
        if context.candidate_type == CandidateType.LINEAR:
            continue
        for leg in context.legs:
            decision = _decide_leg(candidate_id, leg, quantity, now, policy)
            decisions.append(decision)
            if decision.action == LifecycleAction.UNSUPPORTED:
                unsupported.add(candidate_id)
    return decisions, unsupported


def run_module(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    contexts: tuple[CandidateLifecycleInput, ...],
    policy: LifecyclePolicy,
    now: datetime,
) -> LifecyclePlan:
    target = first_horizon_target_portfolio(s5_bundle)
    if not target or not any(abs(value) > 1e-12 for value in target.values()):
        return _no_action_plan()
    context_map = {item.candidate_id: item for item in contexts}
    expected_ids = {candidate.candidate_id for candidate in risk_bundle.payload.candidates}
    missing_ids = expected_ids - set(context_map) if policy.require_complete_context else set()
    decisions, unsupported = _target_decisions(
        target=target,
        context_map=context_map,
        policy=policy,
        now=now,
    )
    unsupported.update(missing_ids)
    status = LifecycleStatus.BLOCKED if unsupported else LifecycleStatus.SUPPORTED
    reasons = ("LIFECYCLE_CONTEXT_MISSING_OR_UNSUPPORTED",) if unsupported else ()
    return _hash_plan(
        LifecyclePlan(
            status=status,
            decisions=tuple(decisions),
            unsupported_candidate_ids=tuple(sorted(unsupported)),
            plan_hash="0" * 64,
            reason_codes=reasons,
        )
    )

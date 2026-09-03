from __future__ import annotations

from datetime import datetime, timedelta

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle

from ..domain.target import (
    first_action_current_quantity_map,
    first_action_delta_map,
    first_horizon_target_portfolio,
)
from ..models.artifacts import (
    AuthorizedAction,
    EmergencyPlan,
    ExecutionAuthorizationPayload,
    HedgePlan,
    IndependentRiskGateReport,
    LifecycleLegDecision,
    LifecyclePlan,
    LiquidationStep,
)
from ..models.enums import (
    AuthorizationActionType,
    AuthorizationStatus,
    EmergencyStatus,
    HedgeStatus,
    LifecycleAction,
    LifecycleStatus,
    RiskGateStatus,
)
from ..models.policies import AuthorizationPolicy


def _action_id(
    run_id: str,
    action_type: AuthorizationActionType,
    candidate_id: str,
    index: int,
) -> str:
    return f"{run_id}:P8.S6:{action_type.value}:{candidate_id}:{index}"


def _validity_window(
    s5_bundle: S5ResultBundle,
    policy: AuthorizationPolicy,
    now: datetime,
) -> tuple[datetime, datetime]:
    mpc = s5_bundle.payload.mpc_plan
    valid_from = max(now, mpc.valid_from)
    if now >= mpc.valid_until:
        return valid_from, valid_from + timedelta(seconds=1)
    valid_until = min(
        mpc.valid_until,
        valid_from + timedelta(seconds=policy.validity_seconds),
    )
    return valid_from, valid_until


def _emergency_action(
    s5_bundle: S5ResultBundle,
    step: LiquidationStep,
    index: int,
    valid_from: datetime,
    valid_until: datetime,
) -> AuthorizedAction:
    return AuthorizedAction(
        authorization_id=_action_id(
            s5_bundle.envelope.run_id,
            AuthorizationActionType.EMERGENCY,
            step.candidate_id,
            index,
        ),
        action_type=AuthorizationActionType.EMERGENCY,
        candidate_id=step.candidate_id,
        target_quantity=step.resulting_target_quantity,
        delta_quantity=step.reduction_quantity,
        valid_from=valid_from,
        valid_until=valid_until,
        reason_codes=("FORCED_RISK_REDUCTION",),
    )


def _emergency_actions(
    s5_bundle: S5ResultBundle,
    emergency: EmergencyPlan,
    valid_from: datetime,
    valid_until: datetime,
) -> list[AuthorizedAction]:
    return [
        _emergency_action(s5_bundle, step, index, valid_from, valid_until)
        for index, step in enumerate(emergency.steps, 1)
    ]


def _hedged_targets(
    s5_bundle: S5ResultBundle,
    hedge: HedgePlan,
) -> dict[str, float]:
    target = first_horizon_target_portfolio(s5_bundle)
    if hedge.status != HedgeStatus.ACCEPTED:
        return target
    for adjustment in hedge.adjustments:
        target[adjustment.candidate_id] = adjustment.hedged_target_quantity
    return target


def _hedged_candidate_ids(hedge: HedgePlan) -> set[str]:
    return {adjustment.candidate_id for adjustment in hedge.adjustments}


def _current_quantity(s5_bundle: S5ResultBundle, candidate_id: str) -> float:
    current = first_action_current_quantity_map(s5_bundle)
    if candidate_id in current:
        return current[candidate_id]
    # Unchanged positions are present in the complete first-horizon portfolio
    # but absent from the delta map. In that case current equals target.
    complete_target = first_horizon_target_portfolio(s5_bundle)
    if candidate_id not in complete_target:
        raise ValueError(f"authorized candidate absent from first-horizon target: {candidate_id}")
    return complete_target[candidate_id]


def _target_actions(
    s5_bundle: S5ResultBundle,
    hedge: HedgePlan,
    target: dict[str, float],
    valid_from: datetime,
    valid_until: datetime,
) -> list[AuthorizedAction]:
    hedged_ids = _hedged_candidate_ids(hedge)
    actions: list[AuthorizedAction] = []
    changed_ids = set(first_action_delta_map(s5_bundle)) | hedged_ids
    for index, candidate_id in enumerate(sorted(changed_ids), 1):
        target_quantity = target[candidate_id]
        delta = target_quantity - _current_quantity(s5_bundle, candidate_id)
        if abs(delta) <= 1e-12:
            continue
        action_type = (
            AuthorizationActionType.HEDGE
            if candidate_id in hedged_ids
            else AuthorizationActionType.TARGET
        )
        actions.append(
            AuthorizedAction(
                authorization_id=_action_id(
                    s5_bundle.envelope.run_id,
                    action_type,
                    candidate_id,
                    index,
                ),
                action_type=action_type,
                candidate_id=candidate_id,
                target_quantity=target_quantity,
                delta_quantity=delta,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        )
    return actions


def _lifecycle_action(
    *,
    s5_bundle: S5ResultBundle,
    decision: LifecycleLegDecision,
    target: dict[str, float],
    index: int,
    valid_from: datetime,
    valid_until: datetime,
) -> AuthorizedAction:
    return AuthorizedAction(
        authorization_id=_action_id(
            s5_bundle.envelope.run_id,
            AuthorizationActionType.LIFECYCLE,
            decision.candidate_id,
            index,
        ),
        action_type=AuthorizationActionType.LIFECYCLE,
        candidate_id=decision.candidate_id,
        target_quantity=target[decision.candidate_id],
        delta_quantity=0.0,
        lifecycle_action=decision.action,
        valid_from=valid_from,
        valid_until=valid_until,
        reason_codes=decision.reason_codes,
    )


def _lifecycle_actions(
    s5_bundle: S5ResultBundle,
    lifecycle: LifecyclePlan,
    target: dict[str, float],
    offset: int,
    valid_from: datetime,
    valid_until: datetime,
) -> list[AuthorizedAction]:
    decisions = [
        decision
        for decision in lifecycle.decisions
        if decision.action != LifecycleAction.HOLD
    ]
    return [
        _lifecycle_action(
            s5_bundle=s5_bundle,
            decision=decision,
            target=target,
            index=offset + index,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        for index, decision in enumerate(decisions, 1)
    ]


def _normal_actions(
    s5_bundle: S5ResultBundle,
    hedge: HedgePlan,
    lifecycle: LifecyclePlan,
    valid_from: datetime,
    valid_until: datetime,
) -> list[AuthorizedAction]:
    target = _hedged_targets(s5_bundle, hedge)
    target_actions = _target_actions(
        s5_bundle, hedge, target, valid_from, valid_until
    )
    lifecycle_actions = _lifecycle_actions(
        s5_bundle,
        lifecycle,
        target,
        len(target_actions),
        valid_from,
        valid_until,
    )
    return target_actions + lifecycle_actions


def _blocked_status(
    gate: IndependentRiskGateReport,
    lifecycle: LifecyclePlan,
    emergency: EmergencyPlan,
) -> tuple[AuthorizationStatus, list[str]] | None:
    if emergency.status == EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN:
        return AuthorizationStatus.RISK_BLOCKED, ["NO_SAFE_LIQUIDATION_PLAN"]
    if gate.status != RiskGateStatus.APPROVED:
        if gate.status == RiskGateStatus.NO_ACTION_VALID:
            return None
        return AuthorizationStatus.RISK_BLOCKED, list(
            gate.reason_codes or ("RISK_GATE_BLOCKED",)
        )
    if lifecycle.status == LifecycleStatus.BLOCKED:
        return AuthorizationStatus.LIFECYCLE_BLOCKED, list(lifecycle.reason_codes)
    return None


def _authorization_decision(
    s5_bundle: S5ResultBundle,
    gate: IndependentRiskGateReport,
    hedge: HedgePlan,
    lifecycle: LifecyclePlan,
    emergency: EmergencyPlan,
    policy: AuthorizationPolicy,
    now: datetime,
    valid_from: datetime,
    valid_until: datetime,
) -> tuple[AuthorizationStatus, list[AuthorizedAction], list[str]]:
    if now >= s5_bundle.payload.mpc_plan.valid_until:
        return AuthorizationStatus.INFEASIBLE, [], ["S5_TARGET_EXPIRED"]
    if emergency.status == EmergencyStatus.PLAN_AVAILABLE and policy.emergency_overrides_normal_target:
        return (
            AuthorizationStatus.EMERGENCY_AUTHORIZED,
            _emergency_actions(s5_bundle, emergency, valid_from, valid_until),
            [],
        )
    blocked = _blocked_status(gate, lifecycle, emergency)
    if blocked is not None:
        status, reasons = blocked
        return status, [], reasons
    actions = _normal_actions(s5_bundle, hedge, lifecycle, valid_from, valid_until)
    if gate.status == RiskGateStatus.NO_ACTION_VALID:
        actions = [
            action for action in actions
            if action.action_type == AuthorizationActionType.LIFECYCLE
        ]
    status = AuthorizationStatus.AUTHORIZED if actions else AuthorizationStatus.NO_ACTION_VALID
    return status, actions, []


def _has_execution_authority(status: AuthorizationStatus) -> bool:
    return status in {
        AuthorizationStatus.AUTHORIZED,
        AuthorizationStatus.PARTIALLY_AUTHORIZED,
        AuthorizationStatus.EMERGENCY_AUTHORIZED,
    }


def run_module(
    s5_bundle: S5ResultBundle,
    gate: IndependentRiskGateReport,
    hedge: HedgePlan,
    lifecycle: LifecyclePlan,
    emergency: EmergencyPlan,
    policy: AuthorizationPolicy,
    now: datetime,
) -> ExecutionAuthorizationPayload:
    valid_from, valid_until = _validity_window(s5_bundle, policy, now)
    status, actions, reasons = _authorization_decision(
        s5_bundle,
        gate,
        hedge,
        lifecycle,
        emergency,
        policy,
        now,
        valid_from,
        valid_until,
    )
    draft = ExecutionAuthorizationPayload(
        status=status,
        decision_snapshot_hash=s5_bundle.payload.mpc_plan.decision_snapshot_hash,
        risk_gate=gate,
        hedge_plan=hedge,
        lifecycle_plan=lifecycle,
        emergency_plan=emergency,
        authorized_actions=tuple(actions),
        valid_from=valid_from,
        valid_until=valid_until,
        execution_authority=_has_execution_authority(status),
        payload_hash="0" * 64,
        module_receipts=(
            "P8.S6.M01:INDEPENDENTLY_RECALCULATED",
            "P8.S6.M02:SEMANTICALLY_CONSUMED",
            "P8.S6.M03:SEMANTICALLY_CONSUMED",
            "P8.S6.M04:SEMANTICALLY_CONSUMED",
            "P8.S6.M05:PUBLISHED",
        ),
        reason_codes=tuple(sorted(set(reasons))),
    )
    unsigned = draft.model_copy(update={"payload_hash": "0" * 64})
    return draft.model_copy(update={"payload_hash": canonical_sha256(unsigned)})

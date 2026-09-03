from __future__ import annotations

from datetime import datetime, timedelta

from ..contracts.canonicalization import canonical_sha256
from ..models.artifacts import DiscreteTargetPositionPanel, MPCControlPlan, RebalanceDecisionPanel, TargetAction
from ..models.enums import RebalanceAction
from ..models.inputs import DecisionReadyRiskPayload

MODULE_ID = "P8.S5.M07"


def run_module(payload: DecisionReadyRiskPayload, discrete: DiscreteTargetPositionPanel, decision: RebalanceDecisionPanel, decision_time: datetime) -> MPCControlPlan:
    current = {c.candidate_id: c.current_quantity for c in payload.candidates}
    first_actions: list[TargetAction] = []
    if decision.action not in {RebalanceAction.HOLD, RebalanceAction.NO_ACTION_VALID}:
        for path in discrete.quantities:
            target = path.quantities_by_horizon[0]
            delta = target - current[path.candidate_id]
            if abs(delta) > 1e-10:
                first_actions.append(TargetAction(candidate_id=path.candidate_id, current_quantity=current[path.candidate_id], target_quantity=target, delta_quantity=delta))
    valid_from = decision_time
    valid_until = valid_from + timedelta(seconds=payload.policy_context.mpc.target_validity_seconds)
    draft = MPCControlPlan(
        decision_snapshot_hash=payload.decision_snapshot_hash,
        action=decision.action,
        first_actions=tuple(first_actions),
        future_plan=discrete.quantities,
        valid_from=valid_from,
        valid_until=valid_until,
        reoptimization_triggers=payload.policy_context.mpc.reoptimization_triggers,
        first_action_only=True,
        plan_hash="0" * 64,
    )
    return draft.model_copy(update={"plan_hash": canonical_sha256(draft.model_copy(update={"plan_hash": "0" * 64}))})

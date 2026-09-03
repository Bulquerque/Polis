from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..domain.arrays import RiskArrays, payload_to_arrays
from ..domain.problem import LinearOptimizationProblem
from ..domain.validation import validate_solution
from ..models.artifacts import DiscreteTargetPositionPanel, MarginalTradeBenefitReport, RebalanceDecisionPanel
from ..models.enums import DiscreteStatus, RebalanceAction
from ..models.inputs import DecisionReadyRiskPayload

MODULE_ID = "P8.S5.M06"


@dataclass(frozen=True)
class _TradeComparison:
    hold_value: float
    target_value: float
    improvement: float
    total_change: float
    changed_candidates: int


def run_module(
    payload: DecisionReadyRiskPayload,
    discrete: DiscreteTargetPositionPanel,
    problem: LinearOptimizationProblem,
) -> RebalanceDecisionPanel:
    terminal = _terminal_decision(discrete)
    if terminal is not None:
        return terminal
    arrays = payload_to_arrays(payload)
    hold_x = _hold_vector(problem, arrays.current, payload.risk_limits.cvar_alpha)
    tolerance = payload.policy_context.solver.primal_feasibility_tolerance
    hold_feasible = validate_solution(problem, hold_x, tolerance).feasible
    comparison = _trade_comparison(problem, discrete, arrays, hold_x)
    return _policy_decision(payload, discrete, arrays, comparison, hold_feasible)


def _terminal_decision(
    discrete: DiscreteTargetPositionPanel,
) -> RebalanceDecisionPanel | None:
    if discrete.status == DiscreteStatus.NO_ACTION_VALID:
        return _decision(RebalanceAction.NO_ACTION_VALID, 0.0, 0.0, 0.0, ("NO_ACTION_VALID",))
    if not discrete.validation.feasible:
        return _decision(RebalanceAction.HOLD, 0.0, 0.0, 0.0, ("DISCRETE_TARGET_INFEASIBLE",))
    return None


def _trade_comparison(
    problem: LinearOptimizationProblem,
    discrete: DiscreteTargetPositionPanel,
    arrays: RiskArrays,
    hold_x: np.ndarray,
) -> _TradeComparison:
    first_target = {path.candidate_id: path.quantities_by_horizon[0] for path in discrete.quantities}
    changes = tuple(
        abs(first_target[candidate_id] - arrays.current[index])
        for index, candidate_id in enumerate(arrays.candidate_ids)
    )
    hold_value = float(problem.c @ hold_x)
    if discrete.objective_value is None:
        raise ValueError("feasible discrete target lacks objective value")
    target_value = float(discrete.objective_value)
    return _TradeComparison(
        hold_value=hold_value,
        target_value=target_value,
        improvement=hold_value - target_value,
        total_change=sum(changes),
        changed_candidates=sum(change > 1e-10 for change in changes),
    )


def _policy_decision(
    payload: DecisionReadyRiskPayload,
    discrete: DiscreteTargetPositionPanel,
    arrays: RiskArrays,
    comparison: _TradeComparison,
    hold_feasible: bool,
) -> RebalanceDecisionPanel:
    policy = payload.policy_context.no_trade
    if policy.risk_reduction_override and not hold_feasible and discrete.validation.feasible:
        return _from_comparison(
            RebalanceAction.RISK_REDUCTION_ONLY,
            comparison,
            ("CURRENT_STATE_VIOLATES_CONSTRAINTS",),
        )
    threshold = _effective_threshold(policy.minimum_objective_improvement, policy.hysteresis_multiplier, arrays)
    if comparison.improvement <= threshold:
        return _from_comparison(RebalanceAction.HOLD, comparison, ("INSUFFICIENT_MARGINAL_BENEFIT",))
    if comparison.total_change <= policy.minimum_total_quantity_change:
        return _from_comparison(RebalanceAction.HOLD, comparison, ("INSUFFICIENT_MARGINAL_BENEFIT",))
    action = _rebalance_action(comparison.changed_candidates, len(arrays.candidate_ids))
    return _from_comparison(action, comparison, ())


def _effective_threshold(base: float, multiplier: float, arrays: RiskArrays) -> float:
    if any(abs(value) > 1e-10 for value in arrays.current):
        return base * multiplier
    return base


def _rebalance_action(changed: int, candidate_count: int) -> RebalanceAction:
    if changed < candidate_count:
        return RebalanceAction.PARTIAL_REBALANCE
    return RebalanceAction.REBALANCE


def _from_comparison(
    action: RebalanceAction,
    comparison: _TradeComparison,
    reasons: tuple[str, ...],
) -> RebalanceDecisionPanel:
    return _decision(
        action,
        comparison.hold_value,
        comparison.target_value,
        comparison.total_change,
        reasons,
    )


def _hold_vector(problem: LinearOptimizationProblem, current: np.ndarray, alpha: float) -> np.ndarray:
    x = np.zeros(problem.layout.total_size, dtype=float)
    _populate_hold_positions(problem, x, current)
    _populate_hold_cvar(problem, x, alpha)
    _populate_hold_ordinals(problem, x)
    return x


def _populate_hold_positions(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    current: np.ndarray,
) -> None:
    for horizon in range(problem.layout.horizon_count):
        for candidate, value in enumerate(current):
            x[problem.layout.q_index(horizon, candidate)] = value
            x[problem.layout.position_index(horizon, candidate)] = abs(value)


def _populate_hold_cvar(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    alpha: float,
) -> None:
    losses = tuple(
        float(problem.a_ub[index] @ x)
        for index, name in enumerate(problem.constraint_names)
        if name.startswith("CVAR_EXCESS")
    )
    if not losses:
        return
    zeta = float(np.quantile(losses, alpha, method="higher"))
    x[problem.layout.zeta] = zeta
    for index, loss in enumerate(losses):
        x[problem.layout.xi.start + index] = max(0.0, loss - zeta)


def _populate_hold_ordinals(problem: LinearOptimizationProblem, x: np.ndarray) -> None:
    for ordinal in range(problem.layout.ordinal_count):
        violations = _ordinal_violations(problem, x, ordinal)
        x[problem.layout.inversion.start + ordinal] = max([0.0, *violations])


def _ordinal_violations(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    ordinal: int,
) -> tuple[float, ...]:
    prefix = f"ORDINAL_INVERSION:{ordinal}:"
    return tuple(
        float(problem.a_ub[index] @ x - problem.b_ub[index])
        for index, name in enumerate(problem.constraint_names)
        if name.startswith(prefix)
    )


def _decision(
    action: RebalanceAction,
    hold: float,
    target: float,
    change: float,
    reasons: tuple[str, ...],
) -> RebalanceDecisionPanel:
    return RebalanceDecisionPanel(
        action=action,
        benefit=MarginalTradeBenefitReport(
            hold_objective=hold,
            target_objective=target,
            objective_improvement=hold - target,
            total_first_action_quantity_change=change,
        ),
        reason_codes=reasons,
    )

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..adapters.scipy_highs import ScipyHighsMILPSolver
from ..contracts.canonicalization import canonical_sha256
from ..domain.arrays import payload_to_arrays
from ..domain.problem import LinearOptimizationProblem
from ..domain.validation import quantities_from_vector, validate_solution
from ..models.artifacts import ContinuousTargetSolution, DiscreteTargetPositionPanel, QuantityPath, RoundingChange, SolutionValidationReport
from ..models.enums import DiscreteStatus, SolverStatus
from ..models.inputs import DecisionReadyRiskPayload

MODULE_ID = "P8.S5.M05"


@dataclass(frozen=True)
class _DiscreteSelection:
    vector: np.ndarray | None
    validation: SolutionValidationReport
    status: DiscreteStatus


def run_module(
    payload: DecisionReadyRiskPayload,
    continuous: ContinuousTargetSolution,
    problem: LinearOptimizationProblem,
) -> DiscreteTargetPositionPanel:
    terminal = _terminal_panel(continuous, problem)
    if terminal is not None:
        return terminal
    arrays = payload_to_arrays(payload)
    rounded = _rounded_vector(
        problem,
        continuous,
        arrays.increments,
        arrays.current,
        payload.risk_limits.cvar_alpha,
    )
    selection = _select_vector(payload, problem, rounded, arrays.increments)
    if selection.vector is None or not selection.validation.feasible:
        return _infeasible_panel(problem, "INFEASIBLE_AFTER_ROUNDING")
    objective_value = float(problem.c @ selection.vector)
    if _degradation_exceeded(payload, continuous, objective_value):
        return _infeasible_panel(problem, "MAXIMUM_OBJECTIVE_DEGRADATION_EXCEEDED")
    return _feasible_panel(problem, continuous, selection, objective_value)


def _terminal_panel(
    continuous: ContinuousTargetSolution,
    problem: LinearOptimizationProblem,
) -> DiscreteTargetPositionPanel | None:
    if continuous.status == SolverStatus.NO_ACTION_VALID:
        return _empty_panel(problem)
    if not continuous.validation.feasible:
        return _infeasible_panel(problem, "CONTINUOUS_SOLUTION_NOT_FEASIBLE")
    return None


def _select_vector(
    payload: DecisionReadyRiskPayload,
    problem: LinearOptimizationProblem,
    rounded: np.ndarray,
    increments: np.ndarray,
) -> _DiscreteSelection:
    tolerance = payload.policy_context.solver.primal_feasibility_tolerance
    validation = validate_solution(problem, rounded, tolerance)
    if validation.feasible:
        return _DiscreteSelection(rounded, validation, DiscreteStatus.FEASIBLE_ROUNDED)
    if not payload.policy_context.rounding.use_milp_reoptimization:
        return _DiscreteSelection(rounded, validation, DiscreteStatus.INFEASIBLE_AFTER_ROUNDING)
    raw = ScipyHighsMILPSolver(payload.policy_context.rounding).solve_discrete(problem, increments)
    repaired = validate_solution(problem, raw.x, tolerance)
    status = (
        DiscreteStatus.FEASIBLE_REOPTIMIZED
        if repaired.feasible
        else DiscreteStatus.INFEASIBLE_AFTER_ROUNDING
    )
    return _DiscreteSelection(raw.x, repaired, status)


def _degradation_exceeded(
    payload: DecisionReadyRiskPayload,
    continuous: ContinuousTargetSolution,
    discrete_value: float,
) -> bool:
    if continuous.objective_value is None:
        return False
    degradation = discrete_value - continuous.objective_value
    return degradation > payload.policy_context.rounding.maximum_objective_degradation


def _feasible_panel(
    problem: LinearOptimizationProblem,
    continuous: ContinuousTargetSolution,
    selection: _DiscreteSelection,
    objective_value: float,
) -> DiscreteTargetPositionPanel:
    quantities = quantities_from_vector(problem, selection.vector)
    paths = tuple(
        QuantityPath(candidate_id=candidate_id, quantities_by_horizon=quantities[index])
        for index, candidate_id in enumerate(problem.candidate_ids)
    )
    draft = DiscreteTargetPositionPanel(
        status=selection.status,
        quantities=paths,
        changes=_changes(problem, continuous, quantities),
        objective_value=objective_value,
        validation=selection.validation,
        discrete_hash="0" * 64,
        reason_codes=(),
    )
    return _with_hash(draft)


def _rounded_vector(
    problem: LinearOptimizationProblem,
    solution: ContinuousTargetSolution,
    increments: np.ndarray,
    current: np.ndarray,
    alpha: float,
) -> np.ndarray:
    x = np.zeros(problem.layout.total_size, dtype=float)
    paths = {path.candidate_id: path.quantities_by_horizon for path in solution.quantities}
    for horizon in range(problem.layout.horizon_count):
        for candidate, candidate_id in enumerate(problem.candidate_ids):
            value = paths[candidate_id][horizon]
            x[problem.layout.q_index(horizon, candidate)] = round(value / increments[candidate]) * increments[candidate]
    _populate_auxiliaries(problem, x, current, alpha)
    return x


def _populate_auxiliaries(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    current: np.ndarray,
    alpha: float,
) -> None:
    _populate_trade_and_position(problem, x, current)
    _populate_cvar(problem, x, alpha)
    _populate_ordinals(problem, x)


def _populate_trade_and_position(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    current: np.ndarray,
) -> None:
    for horizon in range(problem.layout.horizon_count):
        for candidate in range(problem.layout.candidate_count):
            quantity = x[problem.layout.q_index(horizon, candidate)]
            previous = current[candidate] if horizon == 0 else x[problem.layout.q_index(horizon - 1, candidate)]
            x[problem.layout.trade_index(horizon, candidate)] = abs(quantity - previous)
            x[problem.layout.position_index(horizon, candidate)] = abs(quantity)


def _populate_cvar(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    alpha: float,
) -> None:
    if not problem.layout.scenario_count:
        return
    losses = _cvar_losses(problem, x)
    zeta = float(np.quantile(losses, alpha, method="higher")) if losses else 0.0
    x[problem.layout.zeta] = zeta
    for scenario, loss in enumerate(losses):
        x[problem.layout.xi.start + scenario] = max(0.0, loss - zeta)


def _cvar_losses(problem: LinearOptimizationProblem, x: np.ndarray) -> tuple[float, ...]:
    return tuple(
        float(row @ x + bound)
        for name, row, bound in zip(
            problem.constraint_names,
            problem.a_ub,
            problem.b_ub,
            strict=True,
        )
        if name.startswith("CVAR_EXCESS")
    )


def _populate_ordinals(problem: LinearOptimizationProblem, x: np.ndarray) -> None:
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


def _changes(
    problem: LinearOptimizationProblem,
    continuous: ContinuousTargetSolution,
    discrete: tuple[tuple[float, ...], ...],
) -> tuple[RoundingChange, ...]:
    original = {path.candidate_id: path.quantities_by_horizon for path in continuous.quantities}
    changes: list[RoundingChange] = []
    for candidate, candidate_id in enumerate(problem.candidate_ids):
        for horizon in range(problem.layout.horizon_count):
            before = original[candidate_id][horizon]
            after = discrete[candidate][horizon]
            if abs(before - after) > 1e-10:
                changes.append(RoundingChange(
                    candidate_id=candidate_id,
                    horizon_id=problem.horizon_ids[horizon],
                    continuous_quantity=before,
                    discrete_quantity=after,
                ))
    return tuple(changes)


def _empty_panel(problem: LinearOptimizationProblem) -> DiscreteTargetPositionPanel:
    validation = validate_solution(problem, np.zeros(problem.layout.total_size), 1e-9)
    draft = DiscreteTargetPositionPanel(
        status=DiscreteStatus.NO_ACTION_VALID,
        quantities=(),
        changes=(),
        objective_value=0.0,
        validation=validation,
        discrete_hash="0" * 64,
        reason_codes=("NO_ACTION_VALID",),
    )
    return _with_hash(draft)


def _infeasible_panel(
    problem: LinearOptimizationProblem,
    reason: str,
) -> DiscreteTargetPositionPanel:
    draft = DiscreteTargetPositionPanel(
        status=DiscreteStatus.INFEASIBLE_AFTER_ROUNDING,
        quantities=(),
        changes=(),
        objective_value=None,
        validation=validate_solution(problem, None, 1e-9),
        discrete_hash="0" * 64,
        reason_codes=(reason,),
    )
    return _with_hash(draft)


def _with_hash(panel: DiscreteTargetPositionPanel) -> DiscreteTargetPositionPanel:
    hash_input = panel.model_copy(update={"discrete_hash": "0" * 64})
    return panel.model_copy(update={"discrete_hash": canonical_sha256(hash_input)})

from __future__ import annotations

import numpy as np

from ..models.artifacts import ConstraintSlack, SolutionValidationReport
from .problem import LinearOptimizationProblem


def validate_solution(
    problem: LinearOptimizationProblem,
    x: np.ndarray | None,
    tolerance: float,
) -> SolutionValidationReport:
    if x is None:
        return _missing_solution_report()
    inequality_values, equality_values = _constraint_values(problem, x)
    max_inequality = _maximum_inequality_violation(problem, x, inequality_values)
    max_equality = _maximum_value(equality_values)
    feasible = max(max_inequality, max_equality) <= tolerance
    return SolutionValidationReport(
        feasible=bool(feasible),
        objective_value=float(problem.c @ x),
        maximum_inequality_violation=max_inequality,
        maximum_equality_violation=max_equality,
        slacks=_constraint_slacks(problem, x),
        reason_codes=() if feasible else ("CONSTRAINT_VIOLATION",),
    )


def _missing_solution_report() -> SolutionValidationReport:
    return SolutionValidationReport(
        feasible=False,
        objective_value=None,
        maximum_inequality_violation=None,
        maximum_equality_violation=None,
        reason_codes=("NO_SOLUTION_VECTOR",),
    )


def _constraint_values(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    inequalities = problem.a_ub @ x - problem.b_ub if len(problem.b_ub) else np.zeros(0)
    equalities = np.abs(problem.a_eq @ x - problem.b_eq) if len(problem.b_eq) else np.zeros(0)
    return inequalities, equalities


def _maximum_inequality_violation(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
    inequality_values: np.ndarray,
) -> float:
    values = [0.0, *(float(value) for value in inequality_values)]
    values.extend(_bound_violations(problem, x))
    return max(values)


def _bound_violations(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
) -> tuple[float, ...]:
    return tuple(
        _bound_violation(value, lower, upper)
        for value, (lower, upper) in zip(x, problem.bounds, strict=True)
    )


def _bound_violation(value: float, lower: float | None, upper: float | None) -> float:
    below = lower - value if lower is not None else 0.0
    above = value - upper if upper is not None else 0.0
    return max(0.0, below, above)


def _maximum_value(values: np.ndarray) -> float:
    return max([0.0, *(float(value) for value in values)])


def _constraint_slacks(
    problem: LinearOptimizationProblem,
    x: np.ndarray,
) -> tuple[ConstraintSlack, ...]:
    return tuple(
        ConstraintSlack(
            constraint_name=name,
            slack=float(problem.b_ub[index] - problem.a_ub[index] @ x),
        )
        for index, name in enumerate(problem.constraint_names)
    )


def quantities_from_vector(
    problem: LinearOptimizationProblem,
    x: np.ndarray | None,
) -> tuple[tuple[float, ...], ...]:
    if x is None:
        return tuple(tuple() for _ in problem.candidate_ids)
    matrix = x[problem.layout.q].reshape(
        problem.layout.horizon_count,
        problem.layout.candidate_count,
    )
    return tuple(
        tuple(float(matrix[horizon, candidate]) for horizon in range(problem.layout.horizon_count))
        for candidate in range(problem.layout.candidate_count)
    )

from __future__ import annotations

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from ..domain.problem import LinearOptimizationProblem
from ..models.enums import SolverStatus
from ..models.policies import RoundingPolicy, SolverPolicy
from ..ports.solvers import RawSolverResult


class ScipyHighsLPSolver:
    def __init__(self, policy: SolverPolicy) -> None:
        self._policy = policy

    def solve(self, problem: LinearOptimizationProblem) -> RawSolverResult:
        result = linprog(
            c=problem.c,
            A_ub=problem.a_ub if len(problem.b_ub) else None,
            b_ub=problem.b_ub if len(problem.b_ub) else None,
            A_eq=problem.a_eq if len(problem.b_eq) else None,
            b_eq=problem.b_eq if len(problem.b_eq) else None,
            bounds=problem.bounds,
            method="highs",
            options={
                "time_limit": self._policy.time_limit_seconds,
                "presolve": self._policy.presolve,
                "primal_feasibility_tolerance": self._policy.primal_feasibility_tolerance,
                "dual_feasibility_tolerance": self._policy.dual_feasibility_tolerance,
            },
        )
        return _raw_solver_result(result, "SCIPY_HIGHS_LP", scale=None)


class ScipyHighsMILPSolver:
    def __init__(self, policy: RoundingPolicy) -> None:
        self._policy = policy

    def solve_discrete(
        self,
        problem: LinearOptimizationProblem,
        increments: np.ndarray,
    ) -> RawSolverResult:
        scale = _scale_vector(problem, increments)
        lower, upper = _scaled_bounds(problem, scale)
        result = milp(
            c=problem.c * scale,
            integrality=_integrality_vector(problem),
            bounds=Bounds(lower, upper),
            constraints=_milp_constraints(problem, scale),
            options={
                "time_limit": self._policy.time_limit_seconds,
                "mip_rel_gap": self._policy.milp_relative_gap,
                "presolve": True,
            },
        )
        return _raw_solver_result(result, "SCIPY_HIGHS_MILP", scale=scale)


def _scale_vector(
    problem: LinearOptimizationProblem,
    increments: np.ndarray,
) -> np.ndarray:
    scale = np.ones(problem.layout.total_size, dtype=float)
    for horizon in range(problem.layout.horizon_count):
        for candidate in range(problem.layout.candidate_count):
            scale[problem.layout.q_index(horizon, candidate)] = increments[candidate]
    return scale


def _scaled_bounds(
    problem: LinearOptimizationProblem,
    scale: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    lower = np.asarray(
        [_scaled_lower(bound[0], scale[index]) for index, bound in enumerate(problem.bounds)],
        dtype=float,
    )
    upper = np.asarray(
        [_scaled_upper(bound[1], scale[index]) for index, bound in enumerate(problem.bounds)],
        dtype=float,
    )
    return lower, upper


def _scaled_lower(value: float | None, scale: float) -> float:
    return -np.inf if value is None else value / scale


def _scaled_upper(value: float | None, scale: float) -> float:
    return np.inf if value is None else value / scale


def _integrality_vector(problem: LinearOptimizationProblem) -> np.ndarray:
    values = np.zeros(problem.layout.total_size, dtype=int)
    values[problem.layout.q] = 1
    return values


def _milp_constraints(
    problem: LinearOptimizationProblem,
    scale: np.ndarray,
) -> list[LinearConstraint]:
    constraints: list[LinearConstraint] = []
    if len(problem.b_ub):
        constraints.append(LinearConstraint(problem.a_ub * scale[None, :], -np.inf, problem.b_ub))
    if len(problem.b_eq):
        scaled = problem.a_eq * scale[None, :]
        constraints.append(LinearConstraint(scaled, problem.b_eq, problem.b_eq))
    return constraints


def _raw_solver_result(result, solver_name: str, scale: np.ndarray | None) -> RawSolverResult:
    vector = None if result.x is None else np.asarray(result.x, dtype=float)
    if vector is not None and scale is not None:
        vector = vector * scale
    return RawSolverResult(
        status=_map_status(int(result.status), bool(result.success)),
        x=vector,
        objective_value=None if result.fun is None else float(result.fun),
        message=str(result.message),
        iterations=None if getattr(result, "nit", None) is None else int(result.nit),
        solver_name=solver_name,
        solver_version=scipy.__version__,
    )


def _map_status(status: int, success: bool) -> SolverStatus:
    if success and status == 0:
        return SolverStatus.OPTIMAL
    if status == 1:
        return SolverStatus.TIMEOUT_NO_SOLUTION
    if status == 2:
        return SolverStatus.INFEASIBLE
    if status == 3:
        return SolverStatus.UNBOUNDED
    return SolverStatus.SOLVER_ERROR

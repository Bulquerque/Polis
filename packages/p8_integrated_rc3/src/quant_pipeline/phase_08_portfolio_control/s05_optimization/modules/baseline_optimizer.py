from ..adapters.scipy_highs import ScipyHighsLPSolver
from ..domain.problem_builder import build_linear_problem
from ..domain.solution_factory import make_continuous_solution
from ..models.artifacts import CompiledConstraintSet, CompiledPortfolioObjective, ContinuousTargetSolution
from ..models.enums import SolverStatus
from ..models.inputs import DecisionReadyRiskPayload

import numpy as np
from ..ports.solvers import RawSolverResult

MODULE_ID = "P8.S5.M03"


def run_module(
    payload: DecisionReadyRiskPayload,
    objective: CompiledPortfolioObjective,
    constraints: CompiledConstraintSet,
) -> tuple[ContinuousTargetSolution, object]:
    problem = build_linear_problem(payload, objective, constraints)
    if not payload.candidates:
        raw = RawSolverResult(SolverStatus.NO_ACTION_VALID, np.zeros(problem.layout.total_size), 0.0, "empty valid universe", 0, "NO_SOLVER", "0")
        return make_continuous_solution(problem, raw, payload.policy_context.solver.primal_feasibility_tolerance), problem
    raw = ScipyHighsLPSolver(payload.policy_context.solver).solve(problem)
    solution = make_continuous_solution(problem, raw, payload.policy_context.solver.primal_feasibility_tolerance)
    return solution, problem

from __future__ import annotations

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp

from ..errors import SolverAdapterError
from ..ports.solvers import LinearMixedIntegerProblem, SolverResult


class ScipyHighsMilpAdapter:
    name = "scipy-highs-milp"
    version = scipy.__version__

    def solve(self, problem: LinearMixedIntegerProblem) -> SolverResult:
        constraints = LinearConstraint(
            problem.a_matrix,
            problem.a_lower,
            problem.a_upper,
        )
        bounds = Bounds(problem.lower_bounds, problem.upper_bounds)
        options = {
            "time_limit": problem.time_limit_seconds,
            "mip_rel_gap": problem.mip_relative_gap,
            "presolve": True,
        }
        try:
            result = milp(
                c=problem.objective,
                integrality=problem.integrality,
                bounds=bounds,
                constraints=constraints,
                options=options,
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise SolverAdapterError(str(exc)) from exc
        solution = None if result.x is None else np.asarray(result.x, dtype=float)
        objective = None if result.fun is None else float(result.fun)
        return SolverResult(
            success=bool(result.success),
            status=int(result.status),
            message=str(result.message),
            x=solution,
            objective_value=objective,
        )

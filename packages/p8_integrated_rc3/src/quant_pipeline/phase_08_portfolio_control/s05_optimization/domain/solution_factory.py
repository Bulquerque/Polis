from __future__ import annotations

from ..contracts.canonicalization import canonical_sha256
from ..domain.problem import LinearOptimizationProblem
from ..models.artifacts import ContinuousTargetSolution, QuantityPath
from ..models.enums import SolverStatus
from ..ports.solvers import RawSolverResult
from .validation import quantities_from_vector, validate_solution


def make_continuous_solution(problem: LinearOptimizationProblem, raw: RawSolverResult, tolerance: float) -> ContinuousTargetSolution:
    validation = validate_solution(problem, raw.x, tolerance)
    quantities = quantities_from_vector(problem, raw.x)
    paths = tuple(
        QuantityPath(candidate_id=candidate_id, quantities_by_horizon=quantities[i])
        for i, candidate_id in enumerate(problem.candidate_ids)
    )
    status = raw.status
    if raw.x is not None and status == SolverStatus.OPTIMAL and not validation.feasible:
        status = SolverStatus.SOLVER_ERROR
    draft = ContinuousTargetSolution(
        status=status,
        quantities=paths,
        objective_value=raw.objective_value,
        solver_name=raw.solver_name,
        solver_version=raw.solver_version,
        iterations=raw.iterations,
        message=raw.message,
        solution_hash="0" * 64,
        validation=validation,
    )
    return draft.model_copy(update={"solution_hash": canonical_sha256(draft.model_copy(update={"solution_hash": "0" * 64}))})

from ..adapters.scipy_highs import ScipyHighsLPSolver
from ..domain.problem_builder import build_linear_problem
from ..domain.solution_factory import make_continuous_solution
from ..models.artifacts import CompiledConstraintSet, CompiledPortfolioObjective, ContinuousTargetSolution, RobustComparisonReport, RobustTargetSolution
from ..models.enums import ComparisonState, RobustMethod
from ..models.inputs import DecisionReadyRiskPayload

import numpy as np

MODULE_ID = "P8.S5.M04"


def run_module(
    payload: DecisionReadyRiskPayload,
    objective: CompiledPortfolioObjective,
    constraints: CompiledConstraintSet,
    nominal: ContinuousTargetSolution,
    nominal_input_hash: str,
) -> RobustTargetSolution:
    policy = payload.policy_context.robust
    if not payload.candidates:
        return RobustTargetSolution(solution=None, comparison=RobustComparisonReport(
            state=ComparisonState.NOT_RUN, maximum_quantity_difference=0.0,
            nominal_objective=nominal.objective_value, robust_objective=None,
            input_hashes_equal=True, execution_capability=False, reason_codes=("NO_ACTION_VALID",),
        ))
    if not policy.enabled or policy.method == RobustMethod.DISABLED:
        return RobustTargetSolution(solution=None, comparison=RobustComparisonReport(
            state=ComparisonState.NOT_RUN, maximum_quantity_difference=0.0,
            nominal_objective=nominal.objective_value, robust_objective=None,
            input_hashes_equal=True, execution_capability=False, reason_codes=("ROBUST_DISABLED",),
        ))
    ambiguity = payload.ambiguity
    if ambiguity is None or ambiguity.robust_scenario_probabilities is None:
        raise ValueError("robust optimizer requires calibrated probability bands")
    nominal_probabilities = np.asarray([s.probability for s in payload.scenarios], dtype=float)
    robust_probabilities = np.asarray(ambiguity.robust_scenario_probabilities, dtype=float)
    if float(np.abs(nominal_probabilities - robust_probabilities).sum()) > policy.maximum_probability_shift_l1 + 1e-12:
        raise ValueError("robust probability shift exceeds approved bound")
    problem = build_linear_problem(payload, objective, constraints, robust=True)
    raw = ScipyHighsLPSolver(payload.policy_context.solver).solve(problem)
    robust = make_continuous_solution(problem, raw, payload.policy_context.solver.primal_feasibility_tolerance)
    difference = _maximum_quantity_difference(nominal, robust)
    state = ComparisonState.BENIGN if difference <= policy.material_quantity_difference else ComparisonState.MATERIAL
    if robust.validation.feasible is False:
        state = ComparisonState.UNSAFE
    comparison = RobustComparisonReport(
        state=state,
        maximum_quantity_difference=difference,
        nominal_objective=nominal.objective_value,
        robust_objective=robust.objective_value,
        input_hashes_equal=(nominal_input_hash == problem.input_hash),
        execution_capability=False,
        reason_codes=(),
    )
    return RobustTargetSolution(solution=robust, comparison=comparison)


def _maximum_quantity_difference(nominal: ContinuousTargetSolution, robust: ContinuousTargetSolution) -> float:
    nominal_map = {p.candidate_id: p.quantities_by_horizon for p in nominal.quantities}
    robust_map = {p.candidate_id: p.quantities_by_horizon for p in robust.quantities}
    values = [abs(a - b) for cid, path in nominal_map.items() for a, b in zip(path, robust_map.get(cid, ()), strict=True)]
    return max(values, default=0.0)

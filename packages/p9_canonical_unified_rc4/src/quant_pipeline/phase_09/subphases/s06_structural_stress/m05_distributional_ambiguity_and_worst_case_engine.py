from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.spatial.distance import cdist

from .contracts import CapabilityState, S6State
from .models import DROFrontierPoint, DRORequest, DistributionalRobustnessResult
from .numerics import weighted_cvar


def _standardized_cost_matrix(states: np.ndarray) -> np.ndarray:
    scale = np.std(states, axis=0, ddof=1)
    scale = np.where(scale <= 1e-12, 1.0, scale)
    standardized = states / scale
    return cdist(standardized, standardized, metric="euclidean")


def _transport_lp(
    values: np.ndarray,
    cost_matrix: np.ndarray,
    radius: float,
    method: str,
) -> tuple[np.ndarray, float, str]:
    n = values.size
    objective = -np.tile(values, n)
    a_eq = np.zeros((n, n * n), dtype=np.float64)
    for source in range(n):
        a_eq[source, source * n : (source + 1) * n] = 1.0
    b_eq = np.full(n, 1.0 / n, dtype=np.float64)
    a_ub = cost_matrix.reshape(1, n * n)
    b_ub = np.asarray([radius], dtype=np.float64)
    result = linprog(
        objective,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=(0.0, None),
        method=method,
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"transport LP failed: {result.message}")
    transport = result.x.reshape(n, n)
    target_probabilities = np.sum(transport, axis=0)
    target_probabilities = np.maximum(target_probabilities, 0.0)
    target_probabilities /= np.sum(target_probabilities)
    transport_cost = float(np.sum(transport * cost_matrix))
    return target_probabilities, transport_cost, str(result.message)


def _worst_case_cvar(
    losses: np.ndarray,
    cost_matrix: np.ndarray,
    radius: float,
    confidence: float,
    method: str,
) -> float:
    candidates = np.unique(losses)
    best = float("inf")
    for eta in candidates:
        hinges = np.maximum(losses - eta, 0.0)
        probabilities, _, _ = _transport_lp(hinges, cost_matrix, radius, method)
        value = float(eta + np.dot(probabilities, hinges) / (1.0 - confidence))
        best = min(best, value)
    return best


def evaluate_distributional_robustness(request: DRORequest) -> DistributionalRobustnessResult:
    """Solve a finite-support Wasserstein-1 stress frontier with HiGHS."""

    distribution = request.distribution
    n = len(distribution.scenario_ids)
    if n > request.policy.maximum_scenarios:
        return DistributionalRobustnessResult(
            status=S6State.CAPABILITY_UNAVAILABLE,
            family=request.policy.family,
            empirical_mean_loss=float(np.mean(distribution.losses)),
            empirical_cvar=weighted_cvar(
                distribution.losses,
                np.full(n, 1.0 / n),
                request.policy.cvar_confidence_level,
            ),
            empirical_mean_score=(
                None if distribution.scores is None else float(np.mean(distribution.scores))
            ),
            frontier=(),
            capability_state=CapabilityState.UNAVAILABLE,
            radius_calibrated=request.policy.radius_calibration_id is not None,
            reason_codes=("P9_STRESS_DRO_SCENARIO_BUDGET_EXCEEDED",),
        )

    states = np.asarray(distribution.state_vectors, dtype=np.float64)
    losses = np.asarray(distribution.losses, dtype=np.float64)
    scores = (
        None
        if distribution.scores is None
        else np.asarray(distribution.scores, dtype=np.float64)
    )
    cost_matrix = _standardized_cost_matrix(states)
    empirical_probabilities = np.full(n, 1.0 / n, dtype=np.float64)
    empirical_mean_loss = float(np.mean(losses))
    empirical_cvar = weighted_cvar(
        losses, empirical_probabilities, request.policy.cvar_confidence_level
    )
    empirical_score = None if scores is None else float(np.mean(scores))
    frontier: list[DROFrontierPoint] = []
    reason_codes: list[str] = []
    limitations: list[str] = []

    try:
        for radius in request.policy.radius_grid:
            probabilities, transport_cost, message = _transport_lp(
                losses,
                cost_matrix,
                radius,
                request.policy.solver_method,
            )
            worst_loss = float(np.dot(probabilities, losses))
            worst_cvar = _worst_case_cvar(
                losses,
                cost_matrix,
                radius,
                request.policy.cvar_confidence_level,
                request.policy.solver_method,
            )
            worst_score = None
            if scores is not None:
                score_probabilities, _, _ = _transport_lp(
                    -scores,
                    cost_matrix,
                    radius,
                    request.policy.solver_method,
                )
                worst_score = float(np.dot(score_probabilities, scores))
            frontier.append(
                DROFrontierPoint(
                    radius=radius,
                    worst_case_mean_loss=worst_loss,
                    worst_case_cvar=worst_cvar,
                    worst_case_score=worst_score,
                    transport_cost=transport_cost,
                    solver_status=message,
                    target_probabilities=tuple(float(value) for value in probabilities),
                )
            )
    except (RuntimeError, ValueError, FloatingPointError) as error:
        return DistributionalRobustnessResult(
            status=S6State.SOLVER_NOT_QUALIFIED,
            family=request.policy.family,
            empirical_mean_loss=empirical_mean_loss,
            empirical_cvar=empirical_cvar,
            empirical_mean_score=empirical_score,
            frontier=tuple(frontier),
            capability_state=CapabilityState.RESEARCH_ONLY,
            radius_calibrated=request.policy.radius_calibration_id is not None,
            reason_codes=("P9_STRESS_DRO_SOLVER_FAILED",),
            limitations=(str(error),),
        )

    zero = frontier[0]
    if abs(zero.worst_case_mean_loss - empirical_mean_loss) > 1e-8:
        reason_codes.append("P9_STRESS_DRO_BASELINE_MISMATCH")
    if any(
        right.worst_case_mean_loss + 1e-9 < left.worst_case_mean_loss
        for left, right in zip(frontier, frontier[1:])
    ):
        reason_codes.append("P9_STRESS_DRO_MONOTONICITY_FAILED")
    calibrated = request.policy.radius_calibration_id is not None
    if not calibrated:
        reason_codes.append("P9_STRESS_DRO_RADIUS_UNCALIBRATED")
        limitations.append("radius grid is user supplied and not externally calibrated")
    if reason_codes:
        status = S6State.RESEARCH_ONLY
        capability = CapabilityState.RESEARCH_ONLY
    else:
        status = S6State.QUALIFIED
        capability = CapabilityState.AVAILABLE
    return DistributionalRobustnessResult(
        status=status,
        family=request.policy.family,
        empirical_mean_loss=empirical_mean_loss,
        empirical_cvar=empirical_cvar,
        empirical_mean_score=empirical_score,
        frontier=tuple(frontier),
        capability_state=capability,
        radius_calibrated=calibrated,
        reason_codes=tuple(reason_codes),
        limitations=tuple(limitations),
    )

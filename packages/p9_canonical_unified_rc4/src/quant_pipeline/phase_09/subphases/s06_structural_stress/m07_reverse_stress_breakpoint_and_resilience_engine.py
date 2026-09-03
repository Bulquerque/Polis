from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.optimize import minimize

from .contracts import S6State
from .models import FactorBound, ReverseStressRequest, ReverseStressResult
from .numerics import breach_margin, evaluate_quadratic_response, is_breached
from .randomness import derive_generator

_CANONICAL_DECIMALS = 8


def _canonical_float(value: float) -> float:
    """Quantize published numerics so hashes are stable across BLAS/SciPy builds."""
    result = round(float(value), _CANONICAL_DECIMALS)
    return 0.0 if result == -0.0 else result


def _canonical_optional(value: float | None) -> float | None:
    return None if value is None else _canonical_float(value)


def _ordered_bounds(request: ReverseStressRequest) -> list[FactorBound]:
    by_id = {bound.factor_id: bound for bound in request.bounds}
    return [by_id[factor_id] for factor_id in request.response_model.factor_ids]


def _distance(vector: np.ndarray, weights: np.ndarray) -> float:
    return float(math.sqrt(np.sum(weights * vector * vector)))


def _start_points(
    request: ReverseStressRequest,
    lower: np.ndarray,
    upper: np.ndarray,
) -> list[np.ndarray]:
    starts = [np.zeros_like(lower)]
    for index in range(lower.size):
        left = np.zeros_like(lower)
        right = np.zeros_like(lower)
        left[index] = lower[index]
        right[index] = upper[index]
        starts.extend((left, right))
    generator = derive_generator(
        request.seed_policy,
        request.failure_condition.condition_id,
        "reverse",
    )
    while len(starts) < request.policy.multi_start_points:
        starts.append(generator.uniform(lower, upper))
    return starts[: request.policy.multi_start_points]


def _axis_distance(
    request: ReverseStressRequest,
    factor_index: int,
    bound: FactorBound,
) -> float | None:
    candidates: list[float] = []
    for endpoint in (bound.lower, bound.upper):
        baseline = np.zeros(len(request.response_model.factor_ids), dtype=np.float64)
        endpoint_vector = baseline.copy()
        endpoint_vector[factor_index] = endpoint
        endpoint_value = evaluate_quadratic_response(
            request.response_model,
            endpoint_vector,
        )
        if not is_breached(
            endpoint_value,
            request.failure_condition.threshold,
            request.failure_condition.breach_direction,
        ):
            continue
        low, high = 0.0, endpoint
        for _ in range(80):
            midpoint = (low + high) / 2.0
            vector = baseline.copy()
            vector[factor_index] = midpoint
            value = evaluate_quadratic_response(request.response_model, vector)
            if is_breached(
                value,
                request.failure_condition.threshold,
                request.failure_condition.breach_direction,
            ):
                high = midpoint
            else:
                low = midpoint
        candidates.append(abs(high) * math.sqrt(bound.norm_weight))
    return min(candidates) if candidates else None


def _axis_distances(
    request: ReverseStressRequest,
    ordered: list[FactorBound],
) -> tuple[tuple[str, float | None], ...]:
    return tuple(
        (
            factor_id,
            _axis_distance(request, factor_index, ordered[factor_index]),
        )
        for factor_index, factor_id in enumerate(request.response_model.factor_ids)
    )


def _baseline_failure_result(
    request: ReverseStressRequest,
    value: float,
) -> ReverseStressResult:
    return ReverseStressResult(
        status=S6State.STRUCTURALLY_UNSAFE,
        condition_id=request.failure_condition.condition_id,
        distance_to_failure=_canonical_float(0.0),
        shock_vector=tuple(
            (factor_id, 0.0) for factor_id in request.response_model.factor_ids
        ),
        stressed_value=_canonical_float(value),
        binding_condition=request.failure_condition.condition_id,
        verification_error=_canonical_float(0.0),
        solution_count=1,
        safe_axis_distances=tuple(
            (factor_id, _canonical_float(0.0))
            for factor_id in request.response_model.factor_ids
        ),
        solver_messages=("baseline already breaches the failure condition",),
        reason_codes=("P9_STRESS_BASELINE_ALREADY_FAILED",),
    )


def _optimize_candidates(
    request: ReverseStressRequest,
    lower: np.ndarray,
    upper: np.ndarray,
    weights: np.ndarray,
) -> tuple[list[tuple[np.ndarray, float]], list[str]]:
    def objective(vector: np.ndarray) -> float:
        return float(np.sum(weights * vector * vector))

    def constraint(vector: np.ndarray) -> float:
        value = evaluate_quadratic_response(request.response_model, vector)
        return breach_margin(
            value,
            request.failure_condition.threshold,
            request.failure_condition.breach_direction,
        )

    candidates: list[tuple[np.ndarray, float]] = []
    messages: list[str] = []
    for start in _start_points(request, lower, upper):
        result = minimize(
            objective,
            start,
            method="SLSQP",
            bounds=list(zip(lower, upper)),
            constraints=({"type": "ineq", "fun": constraint},),
            options={
                "maxiter": request.policy.maximum_iterations,
                "ftol": request.policy.solver_tolerance,
                "disp": False,
            },
        )
        messages.append(str(result.message))
        if not result.success or result.x is None:
            continue
        value = evaluate_quadratic_response(request.response_model, result.x)
        if is_breached(
            value,
            request.failure_condition.threshold,
            request.failure_condition.breach_direction,
        ):
            candidates.append((np.asarray(result.x, dtype=np.float64), value))
    return candidates, messages


def _domain_probe_vectors(lower: np.ndarray, upper: np.ndarray) -> list[np.ndarray]:
    if lower.size <= 12:
        return [
            np.asarray(values, dtype=np.float64)
            for values in itertools.product(
                *[(lo, hi) for lo, hi in zip(lower, upper)]
            )
        ]
    vectors: list[np.ndarray] = []
    for index in range(lower.size):
        for endpoint in (lower[index], upper[index]):
            vector = np.zeros_like(lower)
            vector[index] = endpoint
            vectors.append(vector)
    return vectors


def _no_candidate_result(
    request: ReverseStressRequest,
    lower: np.ndarray,
    upper: np.ndarray,
    axis_distances: tuple[tuple[str, float | None], ...],
    messages: list[str],
) -> ReverseStressResult:
    failure_exists = any(
        is_breached(
            evaluate_quadratic_response(request.response_model, vector),
            request.failure_condition.threshold,
            request.failure_condition.breach_direction,
        )
        for vector in _domain_probe_vectors(lower, upper)
    )
    status = S6State.SEARCH_NOT_CONVERGED if failure_exists else S6State.NO_FAILURE_WITHIN_DOMAIN
    return ReverseStressResult(
        status=status,
        condition_id=request.failure_condition.condition_id,
        distance_to_failure=None,
        shock_vector=(),
        stressed_value=None,
        binding_condition=None,
        verification_error=None,
        solution_count=0,
        safe_axis_distances=tuple(
            (factor_id, _canonical_optional(value)) for factor_id, value in axis_distances
        ),
        solver_messages=tuple(messages),
        reason_codes=("P9_STRESS_REVERSE_SEARCH_NOT_CONVERGED",) if failure_exists else (),
        limitations=("no failure was found inside the committed search domain",)
        if not failure_exists
        else (),
    )


def _unique_solution_count(candidates: list[tuple[np.ndarray, float]]) -> int:
    unique: list[np.ndarray] = []
    for vector, _ in candidates:
        if not any(np.linalg.norm(vector - existing) <= 1e-6 for existing in unique):
            unique.append(vector)
    return len(unique)


def _solution_status(
    request: ReverseStressRequest,
    distance: float,
    verification_error: float,
) -> tuple[S6State, tuple[str, ...]]:
    if verification_error > request.policy.verification_tolerance:
        return (
            S6State.RESILIENT_WITH_LIMITATIONS,
            ("P9_STRESS_REVERSE_FORWARD_VERIFICATION_FAILED",),
        )
    if distance < request.policy.minimum_safe_distance:
        return (
            S6State.REVERSE_STRESS_TOO_CLOSE,
            ("P9_STRESS_REVERSE_BREAKPOINT_TOO_CLOSE",),
        )
    return S6State.STRESS_RESILIENT, ()


def solve_reverse_stress(request: ReverseStressRequest) -> ReverseStressResult:
    """Find the minimum weighted-L2 shock that breaches a committed condition."""

    ordered = _ordered_bounds(request)
    lower = np.asarray([bound.lower for bound in ordered], dtype=np.float64)
    upper = np.asarray([bound.upper for bound in ordered], dtype=np.float64)
    weights = np.asarray([bound.norm_weight for bound in ordered], dtype=np.float64)
    baseline = np.zeros_like(lower)
    baseline_value = evaluate_quadratic_response(request.response_model, baseline)
    if is_breached(
        baseline_value,
        request.failure_condition.threshold,
        request.failure_condition.breach_direction,
    ):
        return _baseline_failure_result(request, baseline_value)

    candidates, messages = _optimize_candidates(request, lower, upper, weights)
    axis_distances = _axis_distances(request, ordered)
    if not candidates:
        return _no_candidate_result(
            request,
            lower,
            upper,
            axis_distances,
            messages,
        )
    candidates.sort(key=lambda item: _distance(item[0], weights))
    best_vector, best_value = candidates[0]
    distance = _distance(best_vector, weights)
    verification_error = abs(best_value - request.failure_condition.threshold)
    status, reason_codes = _solution_status(
        request,
        distance,
        verification_error,
    )
    return ReverseStressResult(
        status=status,
        condition_id=request.failure_condition.condition_id,
        distance_to_failure=_canonical_float(distance),
        shock_vector=tuple(
            (factor_id, _canonical_float(float(value)))
            for factor_id, value in zip(
                request.response_model.factor_ids,
                best_vector,
            )
        ),
        stressed_value=_canonical_float(best_value),
        binding_condition=request.failure_condition.condition_id,
        verification_error=_canonical_float(verification_error),
        solution_count=_unique_solution_count(candidates),
        safe_axis_distances=tuple(
            (factor_id, _canonical_optional(value)) for factor_id, value in axis_distances
        ),
        solver_messages=tuple(messages),
        reason_codes=reason_codes,
    )

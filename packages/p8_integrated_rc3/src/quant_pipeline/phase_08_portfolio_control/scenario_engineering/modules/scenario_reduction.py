"""P8.S3.M05 decision-aware scenario reduction engine."""
from __future__ import annotations

import numpy as np
from scipy.spatial.distance import cdist

from ..arrays import ScenarioSet
from ..contracts import ReductionAssessment, ReductionPolicy, ReductionStatus
from ..ports import DecisionEvaluationPort

MODULE_ID = "P8.S3.M05"


def _relative_norm(left: np.ndarray, right: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(right)), 1e-12)
    return float(np.linalg.norm(left-right) / denominator)


def _mandatory_tail_indices(flat: np.ndarray, count: int) -> set[int]:
    if count <= 0:
        return set()
    severity = np.linalg.norm(flat, axis=1)
    return set(np.argsort(severity)[-min(count, len(flat)):].tolist())


def _select_forward(flat: np.ndarray, probabilities: np.ndarray, target: int, mandatory: set[int]) -> list[int]:
    distances = cdist(flat, flat, metric="euclidean")
    selected = list(sorted(mandatory))
    if not selected:
        expected_cost = (distances * probabilities[:, None]).sum(axis=0)
        selected.append(int(np.argmin(expected_cost)))
    nearest = distances[:, selected].min(axis=1)
    while len(selected) < target:
        best_index = -1
        best_cost = float("inf")
        for candidate in range(len(flat)):
            if candidate in selected:
                continue
            cost = float(np.sum(probabilities * np.minimum(nearest, distances[:, candidate])))
            if cost < best_cost:
                best_cost = cost
                best_index = candidate
        if best_index < 0:
            break
        selected.append(best_index)
        nearest = np.minimum(nearest, distances[:, best_index])
    return selected


def _reassign(
    scenarios: ScenarioSet, selected: list[int]
) -> tuple[ScenarioSet, float]:
    flat = scenarios.flattened()
    distances = cdist(flat, flat[selected], metric="euclidean")
    assignment = distances.argmin(axis=1)
    probabilities = np.zeros(len(selected), dtype=np.float64)
    for original, reduced in enumerate(assignment):
        probabilities[reduced] += scenarios.probabilities[original]
    transport = float(np.sum(scenarios.probabilities * distances[np.arange(len(flat)), assignment]))
    reduced = ScenarioSet(
        values=scenarios.values[selected], probabilities=probabilities,
        scenario_ids=tuple(scenarios.scenario_ids[index] for index in selected),
        factor_ids=scenarios.factor_ids, step_labels=scenarios.step_labels,
        origins=tuple(scenarios.origins[index] for index in selected),
    )
    return reduced, transport


def _errors(full: ScenarioSet, reduced: ScenarioSet) -> tuple[float, float, float]:
    full_flat = full.flattened()
    reduced_flat = reduced.flattened()
    full_mean = np.average(full_flat, axis=0, weights=full.probabilities)
    reduced_mean = np.average(reduced_flat, axis=0, weights=reduced.probabilities)
    mean_error = _relative_norm(reduced_mean, full_mean)
    full_cov = np.atleast_2d(np.cov(full_flat, rowvar=False, aweights=full.probabilities))
    reduced_cov = np.atleast_2d(np.cov(reduced_flat, rowvar=False, aweights=reduced.probabilities))
    covariance_error = _relative_norm(reduced_cov, full_cov)
    quantiles = np.asarray([0.01, 0.05, 0.95, 0.99])
    full_tail = np.quantile(full_flat, quantiles, axis=0)
    reduced_tail = np.quantile(reduced_flat, quantiles, axis=0)
    tail_error = _relative_norm(reduced_tail, full_tail)
    return mean_error, covariance_error, tail_error


def reduce_scenarios(
    full: ScenarioSet,
    policy: ReductionPolicy,
    evaluator: DecisionEvaluationPort | None = None,
) -> tuple[ScenarioSet, ReductionAssessment]:
    if full.shape[0] * full.shape[0] > policy.max_pairwise_elements:
        assessment = ReductionAssessment(
            status=ReductionStatus.CAPABILITY_UNAVAILABLE,
            original_count=full.shape[0], output_count=full.shape[0],
            mean_error=0.0, covariance_error=0.0, tail_error=0.0, transport_cost=0.0,
            decision_aware_status="CAPABILITY_UNAVAILABLE",
            content_sha256=full.content_sha256(),
        )
        return full, assessment
    if policy.target_count >= full.shape[0]:
        assessment = ReductionAssessment(
            status=ReductionStatus.SAFE, original_count=full.shape[0], output_count=full.shape[0],
            mean_error=0.0, covariance_error=0.0, tail_error=0.0, transport_cost=0.0,
            decision_aware_status="EVALUATED" if evaluator else "CAPABILITY_UNAVAILABLE",
            content_sha256=full.content_sha256(),
        )
        return full, assessment
    flat = full.flattened()
    mandatory = _mandatory_tail_indices(flat, policy.preserve_tail_count)
    selected = _select_forward(flat, full.probabilities, policy.target_count, mandatory)
    reduced, transport = _reassign(full, selected)
    mean_error, covariance_error, tail_error = _errors(full, reduced)
    stable = (
        mean_error <= policy.mean_error_max
        and covariance_error <= policy.covariance_error_max
        and tail_error <= policy.tail_error_max
    )
    decision_status = "CAPABILITY_UNAVAILABLE"
    if evaluator is not None:
        decision_status = "EVALUATED"
        full_eval = evaluator.evaluate(full)
        reduced_eval = evaluator.evaluate(reduced)
        action_error = np.max(np.abs(np.asarray(full_eval.first_action)-np.asarray(reduced_eval.first_action)))
        stable = stable and action_error <= policy.first_action_tolerance
        stable = stable and not reduced_eval.constraint_violations
    if not stable:
        assessment = ReductionAssessment(
            status=ReductionStatus.SCENARIO_REDUCTION_UNSAFE,
            original_count=full.shape[0], output_count=full.shape[0], mean_error=mean_error,
            covariance_error=covariance_error, tail_error=tail_error, transport_cost=transport,
            decision_aware_status=decision_status, content_sha256=full.content_sha256(),
        )
        return full, assessment
    assessment = ReductionAssessment(
        status=ReductionStatus.SAFE, original_count=full.shape[0], output_count=reduced.shape[0],
        mean_error=mean_error, covariance_error=covariance_error, tail_error=tail_error,
        transport_cost=transport, decision_aware_status=decision_status,
        content_sha256=reduced.content_sha256(),
    )
    return reduced, assessment

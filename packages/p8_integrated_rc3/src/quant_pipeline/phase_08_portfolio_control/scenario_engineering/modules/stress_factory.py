"""P8.S3.M04 tail stress and reverse-stress factory."""
from __future__ import annotations

import numpy as np

from ..arrays import ScenarioSet, StressScenarioSet
from ..contracts import StressPolicy, StressResult
from ..errors import ContractIntegrityError
from ..ports import RiskResponseEvaluatorPort

MODULE_ID = "P8.S3.M04"


def build_stresses(scenarios: ScenarioSet, policy: StressPolicy) -> StressScenarioSet:
    baseline = np.average(scenarios.values, axis=0, weights=scenarios.probabilities)
    factor_index = {factor: index for index, factor in enumerate(scenarios.factor_ids)}
    values: list[np.ndarray] = []
    ids: list[str] = []
    severities: list[float] = []
    tags: list[tuple[str, ...]] = []
    for template in policy.templates:
        stressed = baseline.copy()
        for factor, shock in template.factor_shocks.items():
            if factor not in factor_index:
                raise ContractIntegrityError(f"unknown stress factor: {factor}")
            column = factor_index[factor]
            if template.mode == "ADDITIVE":
                stressed[:, column] += shock
            else:
                stressed[:, column] *= 1.0 + shock
        values.append(stressed)
        ids.append(template.stress_id)
        severities.append(template.severity)
        tags.append(template.tags)
    if not values:
        values = [baseline]
        ids = ["BASELINE_NO_EXPLICIT_STRESS"]
        severities = [1.0]
        tags = [("BASELINE",)]
    return StressScenarioSet(
        values=np.stack(values), stress_ids=tuple(ids), factor_ids=scenarios.factor_ids,
        step_labels=scenarios.step_labels, severities=tuple(severities), tags=tuple(tags),
    )


def find_reverse_stress(
    base_shock: tuple[float, ...],
    evaluator: RiskResponseEvaluatorPort | None,
    policy: StressPolicy,
) -> tuple[str, float | None, tuple[str, ...]]:
    if evaluator is None:
        return "CAPABILITY_UNAVAILABLE", None, ()
    if not base_shock or all(abs(value) < 1e-15 for value in base_shock):
        raise ContractIntegrityError("reverse-stress base shock must be non-zero")
    upper = 1.0
    response = evaluator.evaluate(tuple(upper*x for x in base_shock))
    while not response.failure_states and upper < policy.reverse_stress_max_multiplier:
        upper *= 2.0
        response = evaluator.evaluate(tuple(upper*x for x in base_shock))
    if not response.failure_states:
        return "NO_FAILURE_WITHIN_BOUND", None, ()
    lower = 0.0
    failure_states = response.failure_states
    for _ in range(policy.reverse_stress_max_iterations):
        midpoint = (lower + upper) / 2.0
        response = evaluator.evaluate(tuple(midpoint*x for x in base_shock))
        if response.failure_states:
            upper = midpoint
            failure_states = response.failure_states
        else:
            lower = midpoint
        if upper-lower <= policy.reverse_stress_tolerance:
            break
    return "COMPUTED", upper, failure_states


def make_stress_result(
    stresses: StressScenarioSet,
    reverse_status: str,
    reverse_multiplier: float | None,
    failure_states: tuple[str, ...],
) -> StressResult:
    return StressResult(
        stress_scenario_count=len(stresses.stress_ids),
        stress_artifact_id=f"stress-{stresses.content_sha256()[:16]}",
        stress_content_sha256=stresses.content_sha256(),
        reverse_stress_status=reverse_status,
        reverse_stress_multiplier=reverse_multiplier,
        failure_states=failure_states,
    )

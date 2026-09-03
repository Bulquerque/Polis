from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import (
    CandidateRiskInput, DecisionReadyRiskBundle,
)

from ..models.policies import HedgePolicy
from ..ports.solvers import LinearMixedIntegerProblem


@dataclass(frozen=True)
class HedgeProblemMetadata:
    hedge_ids: tuple[str, ...]
    steps: tuple[float, ...]
    base_losses: tuple[float, ...]
    probabilities: tuple[float, ...]
    variable_count: int


@dataclass(frozen=True)
class HedgeCandidateSpec:
    candidate_id: str
    step: float
    lower_count: int
    upper_count: int


def _tradable_step(quantity_increment: float, lot_size: float) -> float | None:
    larger, smaller = max(quantity_increment, lot_size), min(quantity_increment, lot_size)
    ratio = larger / smaller
    return larger if abs(ratio - round(ratio)) <= 1e-9 else None


def _candidate_spec(
    candidate: CandidateRiskInput,
    target: dict[str, float],
    policy: HedgePolicy,
) -> HedgeCandidateSpec | None:
    step = _tradable_step(candidate.quantity_increment, candidate.lot_size)
    if step is None:
        return None
    current = target.get(candidate.candidate_id, candidate.current_quantity)
    low = math.ceil((candidate.minimum_quantity - current) / step - 1e-10)
    high = math.floor((candidate.maximum_quantity - current) / step + 1e-10)
    cap = math.floor(policy.maximum_total_absolute_hedge_units / step + 1e-10)
    return HedgeCandidateSpec(candidate.candidate_id, step, max(low, -cap), min(high, cap))


def _eligible_specs(
    bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
    policy: HedgePolicy,
) -> list[HedgeCandidateSpec] | None:
    candidate_map = {candidate.candidate_id: candidate for candidate in bundle.payload.candidates}
    candidates = [
        candidate_map[candidate_id]
        for candidate_id in policy.approved_hedge_candidate_ids
        if candidate_id in candidate_map
    ]
    if not candidates or not bundle.payload.scenarios:
        return None
    specs = [_candidate_spec(candidate, target, policy) for candidate in candidates]
    return None if any(spec is None for spec in specs) else [spec for spec in specs if spec]


def _scenario_data(
    bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
) -> tuple[list[dict[str, tuple[float, ...]]], tuple[float, ...], tuple[float, ...]]:
    scenario_maps = [
        {row.candidate_id: row.incremental_pnl_by_horizon for row in scenario.candidate_pnl}
        for scenario in bundle.payload.scenarios
    ]
    probabilities = tuple(scenario.probability for scenario in bundle.payload.scenarios)
    base_losses = tuple(
        -sum(rows[candidate_id][0] * quantity for candidate_id, quantity in target.items())
        for rows in scenario_maps
    )
    return scenario_maps, probabilities, base_losses


def _objective(
    bundle: DecisionReadyRiskBundle,
    specs: list[HedgeCandidateSpec],
    probabilities: tuple[float, ...],
    policy: HedgePolicy,
) -> np.ndarray:
    n = len(specs)
    objective = np.zeros(2 * n + 1 + len(probabilities))
    candidate_map = {candidate.candidate_id: candidate for candidate in bundle.payload.candidates}
    for index, spec in enumerate(specs):
        objective[n + index] = (
            policy.transaction_cost_weight
            * candidate_map[spec.candidate_id].transaction_cost_per_unit
        )
    objective[2 * n] = policy.risk_weight
    scale = policy.risk_weight / (1.0 - bundle.payload.risk_limits.cvar_alpha)
    for scenario_index, probability in enumerate(probabilities):
        objective[2 * n + 1 + scenario_index] = scale * probability
    return objective


def _variable_bounds(
    specs: list[HedgeCandidateSpec],
    scenario_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(specs)
    count = 2 * n + 1 + scenario_count
    lower = np.full(count, -np.inf)
    upper = np.full(count, np.inf)
    integrality = np.zeros(count, dtype=int)
    for index, spec in enumerate(specs):
        lower[index] = spec.lower_count
        upper[index] = spec.upper_count
        integrality[index] = 1
    lower[n : 2 * n] = 0
    lower[2 * n + 1 :] = 0
    return lower, upper, integrality


def _constraint_matrix(
    specs: list[HedgeCandidateSpec],
    scenario_maps: list[dict[str, tuple[float, ...]]],
    base_losses: tuple[float, ...],
    maximum_units: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(specs)
    variable_count = 2 * n + 1 + len(scenario_maps)
    rows: list[np.ndarray] = []
    upper: list[float] = []
    for index, spec in enumerate(specs):
        positive = np.zeros(variable_count)
        positive[index], positive[n + index] = spec.step, -1
        negative = np.zeros(variable_count)
        negative[index], negative[n + index] = -spec.step, -1
        rows.extend((positive, negative))
        upper.extend((0.0, 0.0))
    total = np.zeros(variable_count)
    total[n : 2 * n] = 1
    rows.append(total)
    upper.append(maximum_units)
    for scenario_index, (base_loss, scenario_map) in enumerate(
        zip(base_losses, scenario_maps, strict=True)
    ):
        row = np.zeros(variable_count)
        for index, spec in enumerate(specs):
            row[index] = -scenario_map[spec.candidate_id][0] * spec.step
        row[2 * n] = -1
        row[2 * n + 1 + scenario_index] = -1
        rows.append(row)
        upper.append(-base_loss)
    return np.full(len(rows), -np.inf), np.asarray(rows), np.asarray(upper)


def build_hedge_problem(
    bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
    policy: HedgePolicy,
) -> tuple[LinearMixedIntegerProblem, HedgeProblemMetadata] | None:
    specs = _eligible_specs(bundle, target, policy)
    if not specs:
        return None
    scenario_maps, probabilities, base_losses = _scenario_data(bundle, target)
    objective = _objective(bundle, specs, probabilities, policy)
    lower, upper, integrality = _variable_bounds(specs, len(scenario_maps))
    a_lower, a_matrix, a_upper = _constraint_matrix(
        specs, scenario_maps, base_losses, policy.maximum_total_absolute_hedge_units
    )
    problem = LinearMixedIntegerProblem(
        objective=objective,
        lower_bounds=lower,
        upper_bounds=upper,
        integrality=integrality,
        a_lower=a_lower,
        a_matrix=a_matrix,
        a_upper=a_upper,
        time_limit_seconds=policy.time_limit_seconds,
        mip_relative_gap=policy.mip_relative_gap,
    )
    metadata = HedgeProblemMetadata(
        hedge_ids=tuple(spec.candidate_id for spec in specs),
        steps=tuple(spec.step for spec in specs),
        base_losses=base_losses,
        probabilities=probabilities,
        variable_count=len(objective),
    )
    return problem, metadata

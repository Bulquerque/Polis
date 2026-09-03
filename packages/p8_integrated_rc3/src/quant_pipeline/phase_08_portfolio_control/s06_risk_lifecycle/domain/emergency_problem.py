from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import (
    CandidateRiskInput, DecisionReadyRiskBundle,
)

from ..models.inputs import EmergencyState
from ..models.policies import EmergencyPolicy
from ..ports.solvers import LinearMixedIntegerProblem


@dataclass(frozen=True)
class EmergencyProblemMetadata:
    candidate_ids: tuple[str, ...]
    steps: tuple[float, ...]
    directions: tuple[float, ...]


@dataclass(frozen=True)
class EmergencyCandidateRow:
    candidate_id: str
    step: float
    direction: float
    maximum_count: int
    objective_cost: float


def _active_candidates(
    bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
) -> list[CandidateRiskInput]:
    return [
        candidate
        for candidate in bundle.payload.candidates
        if abs(target.get(candidate.candidate_id, 0.0)) > 1e-12
    ]


def _expected_pnl(
    bundle: DecisionReadyRiskBundle,
    candidates: list[CandidateRiskInput],
) -> dict[str, float]:
    expected = {candidate.candidate_id: 0.0 for candidate in candidates}
    for scenario in bundle.payload.scenarios:
        rows = {row.candidate_id: row.incremental_pnl_by_horizon for row in scenario.candidate_pnl}
        for candidate in candidates:
            expected[candidate.candidate_id] += scenario.probability * rows[candidate.candidate_id][0]
    return expected


def _tradable_step(candidate: CandidateRiskInput) -> float | None:
    larger = max(candidate.quantity_increment, candidate.lot_size)
    smaller = min(candidate.quantity_increment, candidate.lot_size)
    ratio = larger / smaller
    return larger if abs(ratio - round(ratio)) <= 1e-9 else None


def _candidate_row(
    candidate: CandidateRiskInput,
    target_quantity: float,
    expected_pnl: float,
    policy: EmergencyPolicy,
) -> EmergencyCandidateRow | None:
    step = _tradable_step(candidate)
    if step is None:
        return None
    count = math.floor(abs(target_quantity) / step + 1e-10)
    if count <= 0:
        return None
    protection = (
        policy.protection_penalty_per_unit
        if candidate.candidate_id in policy.protected_candidate_ids
        else 0.0
    )
    signed_expected = expected_pnl * (1.0 if target_quantity > 0 else -1.0)
    economic = max(0.0, signed_expected)
    objective = step * (
        candidate.transaction_cost_per_unit
        + protection
        + policy.economic_preservation_weight * economic
    )
    return EmergencyCandidateRow(
        candidate_id=candidate.candidate_id,
        step=step,
        direction=-1.0 if target_quantity > 0 else 1.0,
        maximum_count=count,
        objective_cost=objective,
    )


def _candidate_rows(
    active: list[CandidateRiskInput],
    target: dict[str, float],
    expected: dict[str, float],
    policy: EmergencyPolicy,
) -> list[EmergencyCandidateRow]:
    rows = [
        _candidate_row(candidate, target[candidate.candidate_id], expected[candidate.candidate_id], policy)
        for candidate in active
    ]
    return [row for row in rows if row is not None]


def _relief_constraints(
    state: EmergencyState,
    rows: list[EmergencyCandidateRow],
    candidates: dict[str, CandidateRiskInput],
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    matrix: list[np.ndarray] = []
    lower: list[float] = []
    specs = (
        (state.required_margin_relief, "margin_per_unit"),
        (state.required_capital_relief, "capital_per_unit"),
        (state.required_maximum_loss_relief, "maximum_loss_per_unit"),
    )
    for required, field_name in specs:
        if required <= 0:
            continue
        coefficients = [
            getattr(candidates[row.candidate_id], field_name) * row.step
            for row in rows
        ]
        matrix.append(np.asarray(coefficients, dtype=float))
        lower.append(required)
    if not matrix:
        return None
    return np.asarray(lower), np.asarray(matrix), np.full(len(matrix), np.inf)


def build_emergency_problem(
    bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
    state: EmergencyState,
    policy: EmergencyPolicy,
) -> tuple[LinearMixedIntegerProblem, EmergencyProblemMetadata] | None:
    active = _active_candidates(bundle, target)
    if not active:
        return None
    expected = _expected_pnl(bundle, active)
    rows = _candidate_rows(active, target, expected, policy)
    if not rows:
        return None
    candidate_map = {candidate.candidate_id: candidate for candidate in active}
    constraints = _relief_constraints(state, rows, candidate_map)
    if constraints is None:
        return None
    a_lower, a_matrix, a_upper = constraints
    problem = LinearMixedIntegerProblem(
        objective=np.asarray([row.objective_cost for row in rows]),
        lower_bounds=np.zeros(len(rows)),
        upper_bounds=np.asarray([row.maximum_count for row in rows], dtype=float),
        integrality=np.ones(len(rows), dtype=int),
        a_lower=a_lower,
        a_matrix=a_matrix,
        a_upper=a_upper,
        time_limit_seconds=policy.time_limit_seconds,
        mip_relative_gap=policy.mip_relative_gap,
    )
    metadata = EmergencyProblemMetadata(
        candidate_ids=tuple(row.candidate_id for row in rows),
        steps=tuple(row.step for row in rows),
        directions=tuple(row.direction for row in rows),
    )
    return problem, metadata

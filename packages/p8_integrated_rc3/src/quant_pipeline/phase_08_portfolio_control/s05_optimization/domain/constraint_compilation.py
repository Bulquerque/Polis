from __future__ import annotations

import math

from ..contracts.canonicalization import canonical_sha256
from ..errors import ContradictoryConstraintError
from ..models.artifacts import CompiledConstraintSet, ConstraintConflict
from ..models.inputs import CandidateRiskInput, DecisionReadyRiskPayload
from .arrays import RiskArrays, payload_to_arrays


def compile_constraints(payload: DecisionReadyRiskPayload) -> CompiledConstraintSet:
    arrays = payload_to_arrays(payload)
    candidates = tuple(sorted(payload.candidates, key=lambda item: item.candidate_id))
    conflicts = _collect_conflicts(payload, arrays, candidates)
    result = _compiled_constraint_set(payload, arrays, candidates, conflicts)
    if conflicts:
        raise ContradictoryConstraintError("; ".join(item.reason_code for item in conflicts))
    return result


def _collect_conflicts(
    payload: DecisionReadyRiskPayload,
    arrays: RiskArrays,
    candidates: tuple[CandidateRiskInput, ...],
) -> tuple[ConstraintConflict, ...]:
    return (
        *_bound_conflicts(arrays, candidates),
        *_capital_conflicts(payload, candidates),
        *_unbounded_conflicts(arrays),
    )


def _bound_conflicts(
    arrays: RiskArrays,
    candidates: tuple[CandidateRiskInput, ...],
) -> tuple[ConstraintConflict, ...]:
    return tuple(
        ConstraintConflict(
            conflict_id=f"BOUNDS_{candidate.candidate_id}",
            reason_code="CONTRADICTORY_EFFECTIVE_BOUNDS",
            candidate_id=candidate.candidate_id,
            detail="effective lower bound exceeds upper bound",
        )
        for index, candidate in enumerate(candidates)
        if arrays.lower[index] > arrays.upper[index]
    )


def _capital_conflicts(
    payload: DecisionReadyRiskPayload,
    candidates: tuple[CandidateRiskInput, ...],
) -> tuple[ConstraintConflict, ...]:
    mandatory = _mandatory_capital(candidates)
    return tuple(
        ConstraintConflict(
            conflict_id=f"CAPITAL_{horizon}",
            reason_code="MINIMUM_POSITIONS_EXCEED_CAPITAL",
            detail=f"mandatory={mandatory}, limit={limit}",
        )
        for horizon, limit in enumerate(payload.risk_limits.maximum_capital_by_horizon)
        if mandatory > limit + 1e-12
    )


def _mandatory_capital(candidates: tuple[CandidateRiskInput, ...]) -> float:
    total = 0.0
    for candidate in candidates:
        if candidate.minimum_quantity > 0:
            mandatory_quantity = candidate.minimum_quantity
        elif candidate.maximum_quantity < 0:
            mandatory_quantity = abs(candidate.maximum_quantity)
        else:
            mandatory_quantity = 0.0
        if mandatory_quantity <= 0:
            continue
        if candidate.capital_per_unit is None:
            return math.inf
        total += candidate.capital_per_unit * mandatory_quantity
    return total


def _unbounded_conflicts(arrays: RiskArrays) -> tuple[ConstraintConflict, ...]:
    values = (*arrays.lower, *arrays.upper)
    if not any(math.isinf(value) for value in values):
        return ()
    return (
        ConstraintConflict(
            conflict_id="UNBOUNDED_QUANTITY",
            reason_code="UNBOUNDED_DECISION_VARIABLE",
            detail="all candidate bounds must be finite",
        ),
    )


def _compiled_constraint_set(
    payload: DecisionReadyRiskPayload,
    arrays: RiskArrays,
    candidates: tuple[CandidateRiskInput, ...],
    conflicts: tuple[ConstraintConflict, ...],
) -> CompiledConstraintSet:
    draft = CompiledConstraintSet(
        candidate_ids=arrays.candidate_ids,
        horizon_ids=arrays.horizon_ids,
        candidate_bounds=tuple(
            (float(arrays.lower[index]), float(arrays.upper[index]))
            for index in range(len(candidates))
        ),
        quantity_increments=tuple(float(value) for value in arrays.increments),
        capital_limits=payload.risk_limits.maximum_capital_by_horizon,
        margin_limits=payload.risk_limits.maximum_margin_by_horizon,
        maximum_loss_limits=payload.risk_limits.maximum_loss_by_horizon,
        liquidity_caps=tuple(tuple(float(value) for value in row) for row in arrays.liquidity),
        maximum_turnover=payload.risk_limits.maximum_turnover,
        maximum_cvar=payload.risk_limits.maximum_cvar,
        constraint_count=_estimate_constraint_count(payload),
        conflicts=conflicts,
        constraint_hash="0" * 64,
    )
    hash_input = draft.model_copy(update={"constraint_hash": "0" * 64})
    return draft.model_copy(update={"constraint_hash": canonical_sha256(hash_input)})


def _estimate_constraint_count(payload: DecisionReadyRiskPayload) -> int:
    horizons = len(payload.horizons)
    candidates = len(payload.candidates)
    scenarios = len(payload.scenarios)
    greek_limits = len(payload.risk_limits.greek_limits)
    stresses = len(payload.mandatory_stresses)
    return 4 * horizons * candidates + 3 * horizons + 2 * horizons * greek_limits + scenarios + stresses + 1

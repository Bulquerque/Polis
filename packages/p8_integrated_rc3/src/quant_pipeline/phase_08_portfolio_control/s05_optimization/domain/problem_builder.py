from __future__ import annotations

import numpy as np

from ..contracts.canonicalization import canonical_sha256
from ..models.artifacts import CompiledConstraintSet, CompiledPortfolioObjective
from ..models.inputs import DecisionReadyRiskPayload
from .arrays import RiskArrays, payload_to_arrays
from .problem import LinearOptimizationProblem, VariableLayout


def build_linear_problem(
    payload: DecisionReadyRiskPayload,
    objective: CompiledPortfolioObjective,
    constraints: CompiledConstraintSet,
    *,
    robust: bool = False,
) -> LinearOptimizationProblem:
    arrays = payload_to_arrays(payload)
    probabilities, expected = _probabilities_and_expectation(payload, arrays, robust)
    layout = VariableLayout.create(len(arrays.horizon_ids), len(arrays.candidate_ids), len(arrays.scenario_ids), len(payload.ordinal_preferences))
    c = np.zeros(layout.total_size, dtype=float)
    policy = payload.policy_context.objective
    for h in range(layout.horizon_count):
        for i in range(layout.candidate_count):
            c[layout.q_index(h, i)] = -policy.return_weight * expected[h, i]
            c[layout.trade_index(h, i)] = policy.transaction_cost_weight * arrays.transaction_cost[i] + policy.turnover_weight
            c[layout.position_index(h, i)] = policy.funding_weight * arrays.funding[h, i]
    if layout.scenario_count:
        c[layout.zeta] = policy.cvar_weight
        c[layout.xi] = policy.cvar_weight * probabilities / (1.0 - payload.risk_limits.cvar_alpha)
    for j in range(layout.ordinal_count):
        c[layout.inversion.start + j] = policy.ordinal_penalty_weight * payload.ordinal_preferences[j].strength
    rows: list[np.ndarray] = []
    rhs: list[float] = []
    names: list[str] = []
    _add_absolute_trade_constraints(rows, rhs, names, layout, arrays)
    _add_absolute_position_constraints(rows, rhs, names, layout)
    _add_resource_constraints(rows, rhs, names, layout, arrays, payload)
    _add_greek_constraints(rows, rhs, names, layout, arrays, payload)
    _add_concentration_constraints(rows, rhs, names, layout, arrays, payload)
    _add_scenario_constraints(rows, rhs, names, layout, arrays, payload, probabilities)
    _add_stress_constraints(rows, rhs, names, layout, arrays, payload)
    _add_ordinal_constraints(rows, rhs, names, layout, arrays, payload)
    bounds = _build_bounds(layout, arrays)
    input_hash = canonical_sha256({
        "payload_hash": canonical_sha256(payload),
        "objective_hash": objective.objective_hash,
        "constraint_hash": constraints.constraint_hash,
    })
    return LinearOptimizationProblem(
        c=c,
        a_ub=np.vstack(rows) if rows else np.zeros((0, layout.total_size)),
        b_ub=np.asarray(rhs, dtype=float),
        a_eq=np.zeros((0, layout.total_size)),
        b_eq=np.zeros(0),
        bounds=tuple(bounds),
        layout=layout,
        constraint_names=tuple(names),
        candidate_ids=arrays.candidate_ids,
        horizon_ids=arrays.horizon_ids,
        input_hash=input_hash,
    )


def _probabilities_and_expectation(
    payload: DecisionReadyRiskPayload,
    arrays: RiskArrays,
    robust: bool,
) -> tuple[np.ndarray, np.ndarray]:
    probabilities = arrays.probabilities.copy()
    if not robust:
        return probabilities, _expected_pnl(probabilities, arrays)
    probabilities = _robust_probabilities(payload, arrays)
    expected = _expected_pnl(probabilities, arrays)
    return probabilities, _apply_lower_expectation_overrides(payload, arrays, expected)


def _expected_pnl(probabilities: np.ndarray, arrays: RiskArrays) -> np.ndarray:
    shape = (len(arrays.horizon_ids), len(arrays.candidate_ids))
    if not len(probabilities):
        return np.zeros(shape)
    return (probabilities[:, None, None] * arrays.scenario_pnl).sum(axis=0)


def _robust_probabilities(payload: DecisionReadyRiskPayload, arrays: RiskArrays) -> np.ndarray:
    ambiguity = payload.ambiguity
    if ambiguity is None or not ambiguity.calibrated:
        raise ValueError("calibrated robust probabilities are required")
    values = ambiguity.robust_scenario_probabilities
    if values is None:
        raise ValueError("calibrated robust probabilities are required")
    probabilities = np.asarray(values, dtype=float)
    if len(probabilities) != len(arrays.scenario_ids):
        raise ValueError("invalid robust scenario probabilities")
    if abs(probabilities.sum() - 1.0) > 1e-9:
        raise ValueError("invalid robust scenario probabilities")
    return probabilities


def _apply_lower_expectation_overrides(
    payload: DecisionReadyRiskPayload,
    arrays: RiskArrays,
    expected: np.ndarray,
) -> np.ndarray:
    ambiguity = payload.ambiguity
    if ambiguity is None:
        return expected
    overrides = {
        row.candidate_id: row.incremental_pnl_by_horizon
        for row in ambiguity.lower_expected_pnl_by_candidate_horizon
    }
    for index, candidate_id in enumerate(arrays.candidate_ids):
        if candidate_id in overrides:
            expected[:, index] = overrides[candidate_id]
    return expected


def _add_absolute_trade_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays) -> None:
    for h in range(layout.horizon_count):
        for i in range(layout.candidate_count):
            previous = arrays.current[i] if h == 0 else None
            row = np.zeros(layout.total_size); row[layout.q_index(h, i)] = 1; row[layout.trade_index(h, i)] = -1
            if h == 0: bound = previous
            else: row[layout.q_index(h - 1, i)] = -1; bound = 0.0
            rows.append(row); rhs.append(float(bound)); names.append(f"TRADE_ABS_POS:{h}:{i}")
            row = -row
            rows.append(row); rhs.append(float(-bound)); names.append(f"TRADE_ABS_NEG:{h}:{i}")


def _add_absolute_position_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout) -> None:
    for h in range(layout.horizon_count):
        for i in range(layout.candidate_count):
            row = np.zeros(layout.total_size); row[layout.q_index(h, i)] = 1; row[layout.position_index(h, i)] = -1
            rows.append(row); rhs.append(0.0); names.append(f"POSITION_ABS_POS:{h}:{i}")
            rows.append(-row); rhs.append(0.0); names.append(f"POSITION_ABS_NEG:{h}:{i}")


def _add_resource_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays, payload: DecisionReadyRiskPayload) -> None:
    limits = payload.risk_limits
    for h in range(layout.horizon_count):
        for label, vector, limit in (
            ("CAPITAL", arrays.capital, limits.maximum_capital_by_horizon[h]),
            ("MARGIN", arrays.margin, limits.maximum_margin_by_horizon[h]),
            ("MAXIMUM_LOSS", arrays.maximum_loss, limits.maximum_loss_by_horizon[h]),
        ):
            row = np.zeros(layout.total_size)
            for i, coefficient in enumerate(vector): row[layout.position_index(h, i)] = coefficient
            rows.append(row); rhs.append(float(limit)); names.append(f"{label}:{h}")
    row = np.zeros(layout.total_size); row[layout.trade_abs] = 1
    rows.append(row); rhs.append(float(limits.maximum_turnover)); names.append("TURNOVER")


def _add_greek_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays, payload: DecisionReadyRiskPayload) -> None:
    greek_index = {name: i for i, name in enumerate(arrays.greek_names)}
    for limit in payload.risk_limits.greek_limits:
        if limit.greek_name not in greek_index:
            raise ValueError(f"mandatory Greek limit has no exposure data: {limit.greek_name}")
        values = arrays.greeks[greek_index[limit.greek_name]]
        for h in range(layout.horizon_count):
            row = np.zeros(layout.total_size)
            for i, value in enumerate(values): row[layout.q_index(h, i)] = value
            rows.append(row); rhs.append(float(limit.maximum_by_horizon[h])); names.append(f"GREEK_MAX:{limit.greek_name}:{h}")
            rows.append(-row); rhs.append(float(-limit.minimum_by_horizon[h])); names.append(f"GREEK_MIN:{limit.greek_name}:{h}")


def _add_concentration_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays, payload: DecisionReadyRiskPayload) -> None:
    for kind, limits, attr in (
        ("UNDERLYING", payload.risk_limits.underlying_concentration, "underlying_bucket"),
        ("EXPIRATION", payload.risk_limits.expiration_concentration, "expiration_bucket"),
    ):
        for limit in limits:
            by_id = {c.candidate_id: c for c in payload.candidates}
            member_indexes = [i for i, candidate_id in enumerate(arrays.candidate_ids) if getattr(by_id[candidate_id], attr) == limit.bucket_id]
            for h in range(layout.horizon_count):
                row = np.zeros(layout.total_size)
                for i in member_indexes: row[layout.position_index(h, i)] = arrays.capital[i]
                rows.append(row); rhs.append(float(limit.maximum_capital_by_horizon[h])); names.append(f"{kind}_CONCENTRATION:{limit.bucket_id}:{h}")


def _add_scenario_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays, payload: DecisionReadyRiskPayload, probabilities: np.ndarray) -> None:
    if not layout.scenario_count: return
    for s in range(layout.scenario_count):
        row = np.zeros(layout.total_size)
        for h in range(layout.horizon_count):
            for i in range(layout.candidate_count): row[layout.q_index(h, i)] = -arrays.scenario_pnl[s, h, i]
        row[layout.zeta] = -1; row[layout.xi.start + s] = -1
        rows.append(row); rhs.append(0.0); names.append(f"CVAR_EXCESS:{s}")
    if payload.risk_limits.maximum_cvar is not None:
        row = np.zeros(layout.total_size); row[layout.zeta] = 1
        row[layout.xi] = probabilities / (1.0 - payload.risk_limits.cvar_alpha)
        rows.append(row); rhs.append(float(payload.risk_limits.maximum_cvar)); names.append("CVAR_LIMIT")


def _add_stress_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays, payload: DecisionReadyRiskPayload) -> None:
    candidate_index = {candidate_id: i for i, candidate_id in enumerate(arrays.candidate_ids)}
    for stress in payload.mandatory_stresses:
        row = np.zeros(layout.total_size)
        for item in stress.candidate_pnl:
            i = candidate_index[item.candidate_id]
            for h, pnl in enumerate(item.incremental_pnl_by_horizon): row[layout.q_index(h, i)] = -pnl
        rows.append(row); rhs.append(float(stress.portfolio_loss_limit)); names.append(f"STRESS:{stress.stress_id}")


def _add_ordinal_constraints(rows: list[np.ndarray], rhs: list[float], names: list[str], layout: VariableLayout, arrays: RiskArrays, payload: DecisionReadyRiskPayload) -> None:
    candidate_index = {candidate_id: i for i, candidate_id in enumerate(arrays.candidate_ids)}
    for j, pref in enumerate(payload.ordinal_preferences):
        high = candidate_index[pref.preferred_candidate_id]; low = candidate_index[pref.lower_candidate_id]
        for h in range(layout.horizon_count):
            row = np.zeros(layout.total_size)
            row[layout.position_index(h, low)] = 1; row[layout.position_index(h, high)] = -1; row[layout.inversion.start + j] = -1
            rows.append(row); rhs.append(0.0); names.append(f"ORDINAL_INVERSION:{j}:{h}")


def _build_bounds(layout: VariableLayout, arrays: RiskArrays) -> list[tuple[float | None, float | None]]:
    bounds: list[tuple[float | None, float | None]] = [(None, None)] * layout.total_size
    for h in range(layout.horizon_count):
        for i in range(layout.candidate_count):
            bounds[layout.q_index(h, i)] = (float(arrays.lower[i]), float(arrays.upper[i]))
            bounds[layout.trade_index(h, i)] = (0.0, float(arrays.liquidity[h, i]))
            bounds[layout.position_index(h, i)] = (0.0, float(max(abs(arrays.lower[i]), abs(arrays.upper[i]))))
    bounds[layout.zeta] = (None, None)
    for i in range(layout.xi.start, layout.xi.stop): bounds[i] = (0.0, None)
    for i in range(layout.inversion.start, layout.inversion.stop): bounds[i] = (0.0, None)
    return bounds

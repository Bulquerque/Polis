from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models.enums import ActionabilityState
from ..models.inputs import CandidateRiskInput, DecisionReadyRiskPayload, ScenarioPath


@dataclass(frozen=True)
class RiskArrays:
    candidate_ids: tuple[str, ...]
    horizon_ids: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    probabilities: np.ndarray
    scenario_pnl: np.ndarray
    current: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    increments: np.ndarray
    capital: np.ndarray
    margin: np.ndarray
    maximum_loss: np.ndarray
    transaction_cost: np.ndarray
    funding: np.ndarray
    liquidity: np.ndarray
    greek_names: tuple[str, ...]
    greeks: np.ndarray


def payload_to_arrays(payload: DecisionReadyRiskPayload) -> RiskArrays:
    candidates = _ordered_candidates(payload)
    candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
    horizon_ids = tuple(horizon.horizon_id for horizon in payload.horizons)
    scenario_pnl = _scenario_pnl_matrix(payload.scenarios, candidate_ids, len(horizon_ids))
    greek_names, greeks = _greek_matrix(candidates, candidate_ids)
    lower, upper = _effective_bounds(candidates)
    return RiskArrays(
        candidate_ids=candidate_ids,
        horizon_ids=horizon_ids,
        scenario_ids=tuple(scenario.scenario_id for scenario in payload.scenarios),
        probabilities=_float_vector(scenario.probability for scenario in payload.scenarios),
        scenario_pnl=scenario_pnl,
        current=_candidate_vector(candidates, "current_quantity"),
        lower=lower,
        upper=upper,
        increments=_candidate_vector(candidates, "quantity_increment"),
        capital=_qualified_economic_vector(candidates, "capital_per_unit"),
        margin=_qualified_economic_vector(candidates, "margin_per_unit"),
        maximum_loss=_qualified_economic_vector(candidates, "maximum_loss_per_unit"),
        transaction_cost=_candidate_vector(candidates, "transaction_cost_per_unit"),
        funding=_horizon_matrix(candidates, "funding_cost_per_unit_by_horizon"),
        liquidity=_qualified_liquidity_matrix(candidates),
        greek_names=greek_names,
        greeks=greeks,
    )


def _ordered_candidates(payload: DecisionReadyRiskPayload) -> tuple[CandidateRiskInput, ...]:
    return tuple(sorted(payload.candidates, key=lambda item: item.candidate_id))


def _scenario_pnl_matrix(
    scenarios: tuple[ScenarioPath, ...],
    candidate_ids: tuple[str, ...],
    horizon_count: int,
) -> np.ndarray:
    index = {candidate_id: position for position, candidate_id in enumerate(candidate_ids)}
    matrix = np.zeros((len(scenarios), horizon_count, len(candidate_ids)), dtype=float)
    for scenario_index, scenario in enumerate(scenarios):
        for row in scenario.candidate_pnl:
            matrix[scenario_index, :, index[row.candidate_id]] = row.incremental_pnl_by_horizon
    return matrix


def _greek_matrix(
    candidates: tuple[CandidateRiskInput, ...],
    candidate_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], np.ndarray]:
    names = tuple(sorted({greek.greek_name for candidate in candidates for greek in candidate.greeks}))
    matrix = np.zeros((len(names), len(candidate_ids)), dtype=float)
    name_index = {name: index for index, name in enumerate(names)}
    for candidate_index, candidate in enumerate(candidates):
        for greek in candidate.greeks:
            matrix[name_index[greek.greek_name], candidate_index] = greek.value_per_unit
    return names, matrix


def _float_vector(values) -> np.ndarray:
    return np.asarray(tuple(values), dtype=float)


def _candidate_vector(candidates: tuple[CandidateRiskInput, ...], attribute: str) -> np.ndarray:
    return _float_vector(getattr(candidate, attribute) for candidate in candidates)


def _horizon_matrix(candidates: tuple[CandidateRiskInput, ...], attribute: str) -> np.ndarray:
    rows = tuple(getattr(candidate, attribute) for candidate in candidates)
    return np.asarray(rows, dtype=float).T


def _is_structurally_inactive(candidate: CandidateRiskInput) -> bool:
    lower, upper = _candidate_effective_bounds(candidate)
    return (
        abs(candidate.current_quantity) <= 1e-12
        and abs(lower) <= 1e-12
        and abs(upper) <= 1e-12
    )


def _qualified_economic_vector(
    candidates: tuple[CandidateRiskInput, ...], attribute: str,
) -> np.ndarray:
    values: list[float] = []
    for candidate in candidates:
        value = getattr(candidate, attribute)
        if value is None:
            if not _is_structurally_inactive(candidate):
                raise ValueError(
                    f"{attribute} unavailable for active candidate {candidate.candidate_id}"
                )
            values.append(0.0)
        else:
            values.append(float(value))
    return np.asarray(values, dtype=float)


def _qualified_liquidity_matrix(candidates: tuple[CandidateRiskInput, ...]) -> np.ndarray:
    rows: list[tuple[float, ...]] = []
    for candidate in candidates:
        row: list[float] = []
        for value in candidate.liquidity_trade_cap_by_horizon:
            if value is None:
                if not _is_structurally_inactive(candidate):
                    raise ValueError(
                        f"liquidity unavailable for active candidate {candidate.candidate_id}"
                    )
                row.append(0.0)
            else:
                row.append(float(value))
        rows.append(tuple(row))
    return np.asarray(rows, dtype=float).T


def _effective_bounds(
    candidates: tuple[CandidateRiskInput, ...],
) -> tuple[np.ndarray, np.ndarray]:
    bounds = tuple(_candidate_effective_bounds(candidate) for candidate in candidates)
    lower, upper = zip(*bounds, strict=True) if bounds else ((), ())
    return np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)


def _candidate_effective_bounds(candidate: CandidateRiskInput) -> tuple[float, float]:
    lower = candidate.minimum_quantity
    upper = candidate.maximum_quantity
    if candidate.actionability == ActionabilityState.NO_ACTION_VALID:
        return float(candidate.current_quantity), float(candidate.current_quantity)
    if candidate.actionability in {ActionabilityState.CLOSE_ONLY, ActionabilityState.NO_NEW_RISK}:
        return _close_only_bounds(candidate, lower, upper)
    return float(lower), float(upper)


def _close_only_bounds(
    candidate: CandidateRiskInput,
    lower: float,
    upper: float,
) -> tuple[float, float]:
    current = candidate.current_quantity
    if current >= 0:
        return float(max(lower, 0.0)), float(min(upper, current))
    return float(max(lower, current)), float(min(upper, 0.0))

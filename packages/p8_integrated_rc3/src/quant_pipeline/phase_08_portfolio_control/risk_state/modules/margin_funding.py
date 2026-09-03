"""P8.S4.M05 margin, collateral, funding, and capital-state builder."""
from __future__ import annotations

import numpy as np

from ..arrays import ScenarioPnLCube
from ..contracts import (
    AccountState,
    BorrowRecord,
    CandidateEconomicPackage,
    CandidateMarginState,
    ComponentQuality,
    MarginFidelity,
    MarginFundingSummary,
    MarginPolicy,
    MarginRules,
)
from ..hashing import canonical_sha256
from ..ports import BrokerMarginEstimatorPort

MODULE_ID = "P8.S4.M05"


def _short_borrow_available(
    candidate: CandidateEconomicPackage,
    borrow_map: dict[str, BorrowRecord],
) -> bool:
    for leg in candidate.legs:
        if leg.quantity_per_unit >= 0.0:
            continue
        record = borrow_map.get(leg.instrument_id)
        if record is None or not record.available:
            return False
        if record.quantity_available is not None and record.quantity_available < abs(leg.quantity_per_unit):
            return False
    return True


def _span_like_margin(
    candidate_index: int,
    cube: ScenarioPnLCube,
    margin_buffer: float,
    policy: MarginPolicy,
) -> float:
    stress_values = cube.stress_candidate_pnl[:, -1, candidate_index]
    nominal_values = cube.candidate_pnl[:, -1, candidate_index]
    worst_loss = max(0.0, -float(np.min(stress_values, initial=0.0)))
    nominal_tail_loss = max(0.0, -float(np.quantile(nominal_values, 0.01)))
    core = max(worst_loss, nominal_tail_loss) * policy.stress_loss_multiplier
    return core * (1.0 + margin_buffer + policy.liquidity_addon_rate)


def _rule_based_margin(
    candidate: CandidateEconomicPackage,
    policy: MarginPolicy,
    rules: MarginRules,
) -> float | None:
    if candidate.maximum_loss_per_unit is not None and candidate.maximum_loss_proof_status == "PROVEN":
        return candidate.maximum_loss_per_unit * policy.stress_loss_multiplier
    if candidate.gross_notional_per_unit is None:
        return None
    has_short_option = any(
        leg.kind == "EUROPEAN_OPTION" and leg.quantity_per_unit < 0.0
        for leg in candidate.legs
    )
    rate = rules.short_option_margin_rate if has_short_option else rules.base_margin_rate
    return candidate.gross_notional_per_unit * rate


def _recognized_offset_fraction(candidate: CandidateEconomicPackage, rules: MarginRules) -> float:
    if candidate.margin_offset_group is None:
        return 0.0
    for rule in rules.recognized_offsets:
        if rule.group_id == candidate.margin_offset_group:
            return rule.offset_fraction
    return 0.0


def _estimate_margin(
    index: int,
    candidate: CandidateEconomicPackage,
    cube: ScenarioPnLCube,
    rules: MarginRules,
    margin_buffer: float,
    policy: MarginPolicy,
    broker_estimator: BrokerMarginEstimatorPort | None,
) -> tuple[float | None, MarginFidelity, ComponentQuality, list[str]]:
    reasons: list[str] = []
    if broker_estimator is not None:
        estimate = broker_estimator.estimate_margin(candidate.candidate_id)
        quality = (
            ComponentQuality.FULLY_QUALIFIED
            if estimate.quality_status == "QUALIFIED"
            else ComponentQuality.DEGRADED
        )
        return estimate.margin_per_unit, MarginFidelity.EXACT_BROKER_MODEL, quality, list(estimate.reason_codes)
    if rules.fidelity == MarginFidelity.EXACT_BROKER_MODEL:
        margin = rules.exact_margin_per_candidate.get(candidate.candidate_id)
        if margin is None:
            return None, rules.fidelity, ComponentQuality.UNAVAILABLE, ["MARGIN_MODEL_UNAVAILABLE"]
        return margin, rules.fidelity, ComponentQuality.FULLY_QUALIFIED, reasons
    if rules.fidelity == MarginFidelity.SPAN_LIKE_MODEL and policy.allow_span_like:
        return (
            _span_like_margin(index, cube, margin_buffer, policy),
            rules.fidelity,
            ComponentQuality.DEGRADED,
            ["SPAN_LIKE_PROXY"],
        )
    if policy.allow_rule_based:
        margin = _rule_based_margin(candidate, policy, rules)
        quality = ComponentQuality.DEGRADED if margin is not None else ComponentQuality.UNAVAILABLE
        return margin, MarginFidelity.CONSERVATIVE_RULE_BASED, quality, ["CONSERVATIVE_RULE_BASED"]
    return None, rules.fidelity, ComponentQuality.UNAVAILABLE, ["MARGIN_MODEL_UNAVAILABLE"]


def _apply_margin_adjustments(
    margin: float,
    candidate: CandidateEconomicPackage,
    deployable_capital: float,
    rules: MarginRules,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    margin *= 1.0 - _recognized_offset_fraction(candidate, rules)
    threshold = deployable_capital * rules.concentration_threshold
    if (
        candidate.gross_notional_per_unit is not None
        and candidate.gross_notional_per_unit > threshold
    ):
        margin *= 1.0 + rules.concentration_addon_rate
        reasons.append("CONCENTRATION_ADDON_APPLIED")
    return max(margin, 0.0), reasons


def _candidate_margin_state(
    index: int,
    candidate: CandidateEconomicPackage,
    cube: ScenarioPnLCube,
    borrow_map: dict[str, BorrowRecord],
    deployable_capital: float,
    rules: MarginRules,
    margin_buffer: float,
    policy: MarginPolicy,
    broker_estimator: BrokerMarginEstimatorPort | None,
) -> CandidateMarginState:
    borrow_available = _short_borrow_available(candidate, borrow_map)
    margin, fidelity, quality, reasons = _estimate_margin(
        index, candidate, cube, rules, margin_buffer, policy, broker_estimator,
    )
    if not borrow_available:
        reasons.append("BORROW_UNAVAILABLE")
    if margin is None:
        return CandidateMarginState(
            candidate_id=candidate.candidate_id,
            borrow_available=borrow_available,
            fidelity=fidelity,
            quality=ComponentQuality.UNAVAILABLE,
            capital_quality=ComponentQuality.UNAVAILABLE,
            reason_codes=tuple(reasons),
        )
    margin, adjustment_reasons = _apply_margin_adjustments(
        margin, candidate, deployable_capital, rules,
    )
    reasons.extend(adjustment_reasons)
    if candidate.entry_cash_flow_per_unit is None:
        reasons.append("ENTRY_CASH_FLOW_UNAVAILABLE")
        return CandidateMarginState(
            candidate_id=candidate.candidate_id,
            margin_per_unit=margin,
            capital_capacity_units=0.0 if not borrow_available else None,
            borrow_available=borrow_available,
            fidelity=fidelity,
            quality=(ComponentQuality.UNAVAILABLE if not borrow_available else quality),
            capital_quality=ComponentQuality.UNAVAILABLE,
            reason_codes=tuple(reasons),
        )
    settlement_reserve = abs(candidate.entry_cash_flow_per_unit) * policy.settlement_reserve_rate
    capital_required = margin + max(-candidate.entry_cash_flow_per_unit, 0.0) + settlement_reserve
    capacity = None if capital_required == 0.0 else deployable_capital / capital_required
    capital_quality = quality
    if capital_required == 0.0:
        capital_quality = ComponentQuality.UNAVAILABLE
        reasons.append("ZERO_CAPITAL_REQUIREMENT_UNQUALIFIED")
    if not borrow_available:
        capacity = 0.0
        quality = ComponentQuality.UNAVAILABLE
        capital_quality = ComponentQuality.UNAVAILABLE
    return CandidateMarginState(
        candidate_id=candidate.candidate_id,
        margin_per_unit=margin,
        capital_required_per_unit=capital_required,
        capital_capacity_units=capacity,
        borrow_available=borrow_available,
        fidelity=fidelity,
        quality=quality,
        capital_quality=capital_quality,
        reason_codes=tuple(reasons),
    )


def build_margin_funding_state(
    cube: ScenarioPnLCube,
    candidates: tuple[CandidateEconomicPackage, ...],
    account: AccountState,
    borrow_records: tuple[BorrowRecord, ...],
    rules: MarginRules,
    margin_buffer: float,
    policy: MarginPolicy,
    broker_estimator: BrokerMarginEstimatorPort | None = None,
) -> MarginFundingSummary:
    free_cash = max(account.available_cash - account.cash_buffer_required, 0.0)
    margin_headroom = max(account.margin_limit - account.current_margin_used, 0.0)
    deployable_capital = min(
        account.max_new_risk_capital,
        free_cash + account.eligible_collateral,
        margin_headroom + free_cash,
    )
    borrow_map = {record.instrument_id: record for record in borrow_records}
    states = tuple(
        _candidate_margin_state(
            index, candidate, cube, borrow_map, deployable_capital,
            rules, margin_buffer, policy, broker_estimator,
        ) for index, candidate in enumerate(candidates)
    )
    portfolio_margin = (
        rules.exact_portfolio_margin
        if rules.fidelity == MarginFidelity.EXACT_BROKER_MODEL
        and rules.exact_portfolio_margin is not None
        else account.current_margin_used
    )
    payload = {
        "candidate_states": states,
        "portfolio_margin_current": portfolio_margin,
        "margin_headroom": margin_headroom,
        "free_cash_after_buffer": free_cash,
        "eligible_collateral": account.eligible_collateral,
    }
    return MarginFundingSummary(**payload, content_sha256=canonical_sha256(payload))

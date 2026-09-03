from __future__ import annotations

import math

import numpy as np

from .contracts import EvidenceClass, S6State
from .models import CapacityPoint, CapacityRequest, CapacityResult
from .numerics import linear_interpolate_zero


def _capacity_point(request: CapacityRequest, aum: float) -> CapacityPoint:
    annual_traded_notional = request.annual_turnover_ratio * aum
    total_cost = 0.0
    maximum_participation = 0.0
    maximum_liquidation = 0.0
    margin_requirement = 0.0
    evidence_rank = 0
    evidence_order = {
        EvidenceClass.OBSERVED_LIVE: 0,
        EvidenceClass.OBSERVED_HISTORICAL: 1,
        EvidenceClass.TRANSLATED_FACTOR: 2,
        EvidenceClass.MODELLED: 3,
        EvidenceClass.PARAMETRIC: 4,
        EvidenceClass.STRESS_EXTRAPOLATED: 5,
        EvidenceClass.UNAVAILABLE: 6,
    }
    feasible = True
    for leg in request.legs:
        leg_traded = annual_traded_notional * leg.trade_weight
        daily_traded = leg_traded / request.policy.trading_days_per_year
        participation = daily_traded / leg.average_daily_volume
        maximum_participation = max(maximum_participation, participation)
        spread_cost = leg_traded * leg.spread_bps * 1e-4
        impact_bps = leg.impact_coefficient_bps * participation ** leg.impact_exponent
        impact_cost = leg_traded * impact_bps * 1e-4
        carrying_cost = (
            aum
            * leg.gross_exposure_multiple
            * (leg.borrow_bps + leg.funding_bps)
            * 1e-4
        )
        total_cost += spread_cost + impact_cost + carrying_cost
        position_notional = aum * leg.gross_exposure_multiple
        liquidation = position_notional / (
            leg.average_daily_volume * leg.max_participation_rate
        )
        maximum_liquidation = max(maximum_liquidation, liquidation)
        margin_requirement += position_notional * leg.margin_rate
        if participation > leg.max_participation_rate:
            feasible = False
        evidence_rank = max(evidence_rank, evidence_order[leg.evidence_class])

    evidence_class = next(
        evidence for evidence, rank in evidence_order.items() if rank == evidence_rank
    )
    if aum > request.base_aum and evidence_class in {
        EvidenceClass.OBSERVED_LIVE,
        EvidenceClass.OBSERVED_HISTORICAL,
    }:
        evidence_class = EvidenceClass.STRESS_EXTRAPOLATED
    annual_cost_fraction = total_cost / aum
    net_return = request.annual_gross_return - annual_cost_fraction
    margin_usage = margin_requirement / aum
    feasible = feasible and margin_usage <= request.policy.margin_limit_fraction
    return CapacityPoint(
        aum=aum,
        net_return=net_return,
        annual_cost_fraction=annual_cost_fraction,
        maximum_participation_rate=maximum_participation,
        liquidation_horizon_days=maximum_liquidation,
        margin_usage_fraction=margin_usage,
        evidence_class=evidence_class,
        feasible=feasible,
    )


def _network_diagnostics(
    request: CapacityRequest,
) -> tuple[float | None, float | None, tuple[str, ...]]:
    if request.network_stress is None:
        return None, None, ()
    matrix = np.asarray(request.network_stress.overlap_matrix, dtype=np.float64)
    shock = np.asarray(request.network_stress.initial_forced_sale, dtype=np.float64)
    spectral_radius = float(max(abs(np.linalg.eigvals(matrix))))
    if spectral_radius >= request.policy.network_spectral_radius_limit:
        return spectral_radius, None, ("P9_STRESS_NETWORK_AMPLIFICATION_UNSTABLE",)
    amplified = np.linalg.solve(np.eye(matrix.shape[0]) - matrix, shock)
    baseline = float(np.sum(shock))
    amplification = 0.0 if baseline == 0 else float(np.sum(amplified)) / baseline
    return spectral_radius, amplification, ()


def _find_break_even(
    points: tuple[CapacityPoint, ...],
    tolerance: float,
) -> float | None:
    for left, right in zip(points, points[1:]):
        candidate = linear_interpolate_zero(
            left.aum,
            left.net_return,
            right.aum,
            right.net_return,
        )
        if candidate is not None:
            return candidate
    return next(
        (point.aum for point in points if abs(point.net_return) <= tolerance),
        None,
    )


def _capacity_status(
    request: CapacityRequest,
    points: tuple[CapacityPoint, ...],
    capacity_limit: float | None,
    break_even: float | None,
    network_reasons: tuple[str, ...],
) -> tuple[S6State, tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = list(network_reasons)
    limitations: list[str] = []
    if break_even is None:
        reasons.append("P9_STRESS_BREAK_EVEN_AUM_NOT_IDENTIFIED")
        limitations.append("net return does not cross zero inside the qualified AUM grid")
    if any(
        point.evidence_class is EvidenceClass.STRESS_EXTRAPOLATED
        for point in points
    ):
        reasons.append("P9_STRESS_CAPACITY_EXTRAPOLATION_MATERIAL")
        limitations.append("part of the capacity curve is extrapolated beyond observed scale")
    if capacity_limit is None or capacity_limit < max(request.aum_grid):
        reasons.append("P9_STRESS_CAPACITY_LIMITED")
        status = S6State.CAPACITY_LIMITED
    elif network_reasons:
        status = S6State.NETWORK_STRESS_RESEARCH_ONLY
        limitations.append("network fire-sale amplification is unstable or research-only")
    elif limitations:
        status = S6State.QUALIFIED_WITH_LIMITATIONS
    else:
        status = S6State.QUALIFIED
    return status, tuple(dict.fromkeys(reasons)), tuple(limitations)


def evaluate_capacity(request: CapacityRequest) -> CapacityResult:
    """Compute nonlinear implementation cost and feasibility curves over AUM."""

    points = tuple(_capacity_point(request, aum) for aum in request.aum_grid)
    break_even = _find_break_even(points, request.policy.break_even_tolerance)
    feasible_points = [point for point in points if point.feasible]
    capacity_limit = max((point.aum for point in feasible_points), default=None)
    spectral_radius, amplification, network_reasons = _network_diagnostics(request)
    status, reasons, limitations = _capacity_status(
        request,
        points,
        capacity_limit,
        break_even,
        network_reasons,
    )
    maximum_liquidation = max(point.liquidation_horizon_days for point in points)
    minimum_margin_buffer = min(
        request.policy.margin_limit_fraction - point.margin_usage_fraction
        for point in points
    )
    if not all(math.isfinite(point.net_return) for point in points):
        raise ValueError("capacity calculation produced non-finite values")
    return CapacityResult(
        status=status,
        points=points,
        break_even_aum=break_even,
        capacity_limit_aum=capacity_limit,
        maximum_liquidation_horizon_days=maximum_liquidation,
        minimum_margin_buffer=minimum_margin_buffer,
        network_spectral_radius=spectral_radius,
        network_loss_amplification=amplification,
        reason_codes=reasons,
        limitations=limitations,
    )

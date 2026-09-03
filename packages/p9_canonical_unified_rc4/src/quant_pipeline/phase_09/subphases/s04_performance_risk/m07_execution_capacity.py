"""P9.S4.M07 — execution quality, cost drag, leverage, margin, and capacity."""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    CashCategory,
    OrderStatus,
    Side,
)

from .common import EvidenceClass, GrossNet, MetricRecord, MetricStatus, Unit, content_sha256
from .execution_models import (
    CapacityCurvePanel,
    CapacityPoint,
    CostDragPanel,
    ExecutionCapacityRequest,
    ExecutionCapacityResult,
    ExecutionMetricPanel,
    ExecutionMetricRecord,
)
from .reason_codes import ReasonCode


def _cost_outflow(entries, category):
    total = sum((entry.amount for entry in entries if entry.category is category), Decimal("0"))
    return -total if total < 0 else Decimal("0")


def compute_execution_capacity(request: ExecutionCapacityRequest) -> ExecutionCapacityResult:
    """Measure target-to-fill execution and extrapolate capacity with explicit evidence class."""

    handoff = request.handoff
    context_by_order = {context.order_id: context for context in request.target_contexts}
    order_by_id = {order.order_id: order for order in handoff.orders}
    filled_by_order: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    filled_notional = Decimal("0")
    slippage_cost = Decimal("0")
    priced_fill_count = 0
    for fill in handoff.fills:
        filled_by_order[fill.order_id] += fill.quantity
        filled_notional += fill.quantity * fill.price
        context = context_by_order.get(fill.order_id)
        if context is not None:
            signed_difference = (
                fill.price - context.arrival_price
                if fill.side is Side.BUY
                else context.arrival_price - fill.price
            )
            slippage_cost += fill.quantity * signed_difference
            priced_fill_count += 1

    total_target_quantity = sum((abs(context.target_quantity) for context in request.target_contexts), Decimal("0"))
    total_filled_quantity = sum(filled_by_order.values(), Decimal("0"))
    fill_rate = float(total_filled_quantity / total_target_quantity) if total_target_quantity > 0 else None
    partial_count = 0
    for order_id, quantity in filled_by_order.items():
        order = order_by_id.get(order_id)
        if order is not None and Decimal("0") < quantity < order.quantity:
            partial_count += 1
    order_count = len(handoff.orders)
    rejected = sum(order.status is OrderStatus.REJECTED for order in handoff.orders)
    partial_rate = partial_count / order_count if order_count else None
    rejection_rate = rejected / order_count if order_count else None
    average_nav = (
        sum((snapshot.nav for snapshot in request.exposures), Decimal("0")) / len(request.exposures)
        if request.exposures
        else None
    )
    turnover = float(filled_notional / average_nav) if average_nav not in (None, Decimal("0")) else None
    average_leverage = (
        sum((float(snapshot.gross_exposure / snapshot.nav) for snapshot in request.exposures), 0.0) / len(request.exposures)
        if request.exposures
        else None
    )
    peak_leverage = max((float(snapshot.gross_exposure / snapshot.nav) for snapshot in request.exposures), default=None)
    average_margin = (
        sum((float(snapshot.margin_used / snapshot.nav) for snapshot in request.exposures), 0.0) / len(request.exposures)
        if request.exposures
        else None
    )
    peak_margin = max((float(snapshot.margin_used / snapshot.nav) for snapshot in request.exposures), default=None)

    observed_class = EvidenceClass.OBSERVED_HISTORICAL
    execution_metrics = (
        ExecutionMetricRecord(metric_id="execution.fill_rate", value=fill_rate, status=MetricStatus.QUALIFIED.value if fill_rate is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=len(request.target_contexts), limitations=() if fill_rate is not None else (ReasonCode.EXECUTION_CONTEXT_INCOMPLETE.value,)),
        ExecutionMetricRecord(metric_id="execution.partial_fill_rate", value=partial_rate, status=MetricStatus.QUALIFIED.value if partial_rate is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=order_count),
        ExecutionMetricRecord(metric_id="execution.rejection_rate", value=rejection_rate, status=MetricStatus.QUALIFIED.value if rejection_rate is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=order_count),
        ExecutionMetricRecord(metric_id="execution.turnover", value=turnover, status=MetricStatus.QUALIFIED.value if turnover is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=len(request.exposures)),
        ExecutionMetricRecord(metric_id="execution.average_leverage", value=average_leverage, status=MetricStatus.QUALIFIED.value if average_leverage is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=len(request.exposures)),
        ExecutionMetricRecord(metric_id="execution.peak_leverage", value=peak_leverage, status=MetricStatus.QUALIFIED.value if peak_leverage is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=len(request.exposures)),
        ExecutionMetricRecord(metric_id="execution.average_margin_utilization", value=average_margin, status=MetricStatus.QUALIFIED.value if average_margin is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=len(request.exposures)),
        ExecutionMetricRecord(metric_id="execution.peak_margin_utilization", value=peak_margin, status=MetricStatus.QUALIFIED.value if peak_margin is not None else MetricStatus.UNAVAILABLE.value, evidence_class=observed_class, observation_count=len(request.exposures)),
    )
    panel_metrics = tuple(
        MetricRecord(
            metric_id=record.metric_id,
            metric_version="1.0.0",
            producer_module_id="P9.S4.M07",
            value=record.value,
            unit=Unit.RATIO,
            status=MetricStatus(record.status),
            gross_net=GrossNet.NOT_APPLICABLE,
            sample_count=record.observation_count,
            method="ledger_reconciliation",
            limitations=record.limitations,
        )
        for record in execution_metrics
    )
    if priced_fill_count:
        slippage_fraction = float(slippage_cost / filled_notional) if filled_notional else 0.0
        panel_metrics += (
            MetricRecord(metric_id="execution.slippage_fraction", metric_version="1.0.0", producer_module_id="P9.S4.M07", value=slippage_fraction, unit=Unit.FRACTION, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NOT_APPLICABLE, sample_count=priced_fill_count, method="arrival_price_implementation_shortfall"),
        )

    liquidity_by_instrument = {item.instrument_id: item for item in request.liquidity}
    capacity_points: list[CapacityPoint] = []
    for multiplier in request.policy.aum_multipliers:
        weighted_impact = 0.0
        total_weight = 0.0
        maximum_participation = 0.0
        complete = bool(handoff.fills)
        for fill in handoff.fills:
            liquidity = liquidity_by_instrument.get(fill.instrument_id)
            if liquidity is None:
                complete = False
                continue
            scaled_quantity = float(fill.quantity) * multiplier
            participation = scaled_quantity / float(liquidity.average_daily_volume)
            maximum_participation = max(maximum_participation, participation)
            impact = request.policy.impact.eta * liquidity.daily_volatility * math.sqrt(max(participation, 0.0))
            weight = float(fill.quantity * fill.price)
            weighted_impact += impact * weight
            total_weight += weight
        impact_fraction = weighted_impact / total_weight if total_weight > 0 else 0.0
        status = MetricStatus.QUALIFIED.value if complete and maximum_participation <= request.policy.impact.maximum_participation else MetricStatus.LIMITED.value if total_weight > 0 else MetricStatus.UNAVAILABLE.value
        capacity_points.append(
            CapacityPoint(
                aum_multiplier=multiplier,
                estimated_impact_fraction=impact_fraction,
                estimated_net_return_after_impact=request.baseline_net_return - impact_fraction if request.baseline_net_return is not None and total_weight > 0 else None,
                maximum_participation_fraction=maximum_participation,
                status=status,
            )
        )

    execution_body = {
        "panel_id": f"execution-{request.identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": request.identity,
        "metrics": panel_metrics,
        "diagnostics": (),
        "limitations": () if request.target_contexts else (ReasonCode.EXECUTION_CONTEXT_INCOMPLETE.value,),
        "execution_metrics": execution_metrics,
    }
    execution_panel = ExecutionMetricPanel(**execution_body, content_sha256=content_sha256(execution_body))
    financing = _cost_outflow(handoff.cash_entries, CashCategory.FINANCING)
    borrow = _cost_outflow(handoff.cash_entries, CashCategory.BORROW)
    fees = sum((fill.fee for fill in handoff.fills), Decimal("0"))
    costs_body = {
        "panel_id": f"costs-{request.identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": request.identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": () if priced_fill_count else (ReasonCode.EXECUTION_CONTEXT_INCOMPLETE.value,),
        "total_fees": fees,
        "total_financing": financing,
        "total_borrow": borrow,
        "observed_slippage": slippage_cost if priced_fill_count else None,
    }
    cost_panel = CostDragPanel(**costs_body, content_sha256=content_sha256(costs_body))
    capacity_body = {
        "panel_id": f"capacity-{request.identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": request.identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": () if request.liquidity else (ReasonCode.CAPACITY_MODEL_UNAVAILABLE.value,),
        "points": tuple(capacity_points),
        "evidence_class": request.policy.impact.evidence_class,
    }
    capacity_panel = CapacityCurvePanel(**capacity_body, content_sha256=content_sha256(capacity_body))
    return ExecutionCapacityResult(execution=execution_panel, costs=cost_panel, capacity=capacity_panel)

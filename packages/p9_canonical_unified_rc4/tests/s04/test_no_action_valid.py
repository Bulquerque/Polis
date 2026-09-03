from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    P8EvaluationHandoff,
    ValuationRecord,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m04_integrity_replay import (
    finalize_handoff_replay_hash,
    qualify_backtest,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import (
    QualifiedBacktestInput,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.service import (
    S4AnalyticsRequest,
    S4AnalyticsService,
)


def test_no_action_valid_produces_zero_return_without_fabricated_trades(
    policies,
    registries,
):
    base = datetime(2024, 1, 1, tzinfo=UTC)
    valuations = tuple(
        ValuationRecord(
            valuation_time=base + timedelta(days=index),
            cash=Decimal("1000"),
            market_value=Decimal("0"),
            gross_pnl=Decimal("0"),
            costs=Decimal("0"),
            net_pnl=Decimal("0"),
            nav=Decimal("1000"),
        )
        for index in range(1, 80)
    )
    handoff = P8EvaluationHandoff(
        handoff_id="handoff:no-action:outer-000",
        schema_version="1.0.0",
        run_id="run-no-action",
        cycle_id="cycle-no-action",
        trial_id="trial-no-action",
        fold_id="outer-000",
        capability="PRODUCTION",
        start_cash=Decimal("1000"),
        end_cash=Decimal("1000"),
        p6_candidate_ids=(),
        p7_terminal_records=(),
        p8_terminal_records=(),
        orders=(),
        fills=(),
        cash_entries=(),
        lifecycle_events=(),
        final_positions=(),
        valuations=valuations,
        required_lifecycle_supported=True,
        replay_sha256="0" * 64,
    )
    handoff = finalize_handoff_replay_hash(handoff)
    qualified = QualifiedBacktestInput(
        configuration_id="cfg-no-action",
        handoff=handoff,
        qualification=qualify_backtest(handoff),
    )
    result = S4AnalyticsService().run(
        S4AnalyticsRequest(
            qualified_backtest=qualified,
            return_policy=policies["return"],
            distribution_policy=policies["distribution"],
            tail_policy=policies["tail"],
            drawdown_policy=policies["drawdown"],
            risk_adjusted_policy=policies["risk_adjusted"],
            capacity_policy=policies["capacity"],
            metric_registry=registries[0],
            metric_quality_policy=policies["quality"],
        )
    )
    cumulative = [
        metric
        for metric in result.returns.return_metrics.metrics
        if metric.metric_id == "return.cumulative"
    ]
    assert all(metric.value == 0.0 for metric in cumulative)
    assert result.execution.execution.execution_metrics
    assert all(
        record.status == "UNAVAILABLE"
        for record in result.execution.execution.execution_metrics[:3]
    )
    assert not qualified.handoff.orders
    assert not qualified.handoff.fills

from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m08_reality_gap import (
    ExecutionStage,
    RealityGapPolicy,
    StageExecutionRecord,
    TransportabilityState,
    evaluate_reality_gap,
)

pytestmark = pytest.mark.unit


def record(base_time, decision: str, stage: ExecutionStage, fill: float, price: float | None, pnl: float):
    return StageExecutionRecord(
        decision_id=decision,
        cohort_id=f"cohort-{decision}",
        policy_id="champion",
        instrument_id="ABC",
        horizon_id="1d",
        stage=stage,
        decision_time=base_time - timedelta(days=2),
        forecast_value=0.1,
        signal_value=1.0,
        target_quantity=10.0,
        order_quantity=10.0,
        fill_quantity=fill,
        benchmark_price=100.0,
        average_fill_price=price,
        fees=1.0,
        margin_used=100.0,
        pnl=pnl,
        evidence_class=(
            EvidenceClass.FACTUAL_EXECUTED
            if stage is ExecutionStage.LIVE
            else EvidenceClass.MODEL_BASED_COUNTERFACTUAL
        ),
    )


def test_transportable_when_stages_match(base_time):
    rows = []
    for i in range(3):
        rows.extend(
            [
                record(base_time, f"d{i}", ExecutionStage.BACKTEST, 10.0, 100.1, 5.0),
                record(base_time, f"d{i}", ExecutionStage.SHADOW, 10.0, 100.1, 5.0),
                record(base_time, f"d{i}", ExecutionStage.LIVE, 10.0, 100.1, 5.0),
            ]
        )
    result = evaluate_reality_gap(tuple(rows), RealityGapPolicy(minimum_live_pairs=3))
    assert result.state is TransportabilityState.TRANSPORTABLE
    assert result.mean_abs_fill_rate_gap == pytest.approx(0.0)


def test_fill_gap_detects_execution_misspecification(base_time):
    rows = []
    for i in range(3):
        rows.extend(
            [
                record(base_time, f"d{i}", ExecutionStage.BACKTEST, 10.0, 100.1, 5.0),
                record(base_time, f"d{i}", ExecutionStage.LIVE, 2.0, 101.0, -3.0),
            ]
        )
    result = evaluate_reality_gap(
        tuple(rows),
        RealityGapPolicy(
            minimum_live_pairs=3,
            maximum_mean_abs_fill_rate_gap=0.1,
            maximum_mean_abs_slippage_gap_bps=5.0,
        ),
    )
    assert result.state is TransportabilityState.EXECUTION_MODEL_MISSPECIFIED
    assert "P9_LIVE_REALITY_GAP_MATERIAL" in result.reason_codes


def test_no_live_data_is_insufficient(base_time):
    rows = (record(base_time, "d", ExecutionStage.BACKTEST, 10.0, 100.1, 5.0),)
    result = evaluate_reality_gap(rows, RealityGapPolicy(minimum_live_pairs=1))
    assert result.state is TransportabilityState.SHADOW_EVIDENCE_INSUFFICIENT

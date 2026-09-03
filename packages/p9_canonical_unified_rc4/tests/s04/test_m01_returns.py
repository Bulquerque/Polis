from __future__ import annotations

from decimal import Decimal

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    BacktestQualificationReceipt,
    QualificationState,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.m01_returns import compute_returns
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import (
    QualifiedBacktestInput,
    ReturnEngineRequest,
)


def metric(panel, metric_id, gross_net):
    return next(item for item in panel.metrics if item.metric_id == metric_id and item.gross_net.value == gross_net)


def test_return_engine_reconciles_gross_net(qualified, policies, benchmark, risk_free):
    result = compute_returns(
        ReturnEngineRequest(
            qualified_backtest=qualified,
            policy=policies["return"],
            benchmark=benchmark,
            risk_free=risk_free,
        )
    )
    assert len(result.return_series.net_returns) == len(qualified.handoff.valuations) - 1
    assert result.wealth_path.points[-1].gross_wealth == qualified.handoff.valuations[-1].nav + Decimal("1")
    gross = metric(result.return_metrics, "return.cumulative", "GROSS")
    net = metric(result.return_metrics, "return.cumulative", "NET")
    assert gross.value is not None and net.value is not None
    assert gross.value != net.value
    assert result.return_metrics.total_cost == Decimal("1")
    assert result.return_series.active_returns is not None
    assert result.return_series.excess_returns is not None


def test_return_engine_hash_is_stable(qualified, policies):
    request = ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"])
    first = compute_returns(request)
    second = compute_returns(request)
    assert first == second
    assert first.reconciliation_sha256 == second.reconciliation_sha256


def test_return_engine_rejects_unqualified_handoff(handoff):
    invalid = BacktestQualificationReceipt(
        handoff_id=handoff.handoff_id,
        state=QualificationState.INVALID,
        checks=(),
        reason_codes=("INVALID",),
        qualified_handoff_sha256=None,
        content_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="S4 accepts only"):
        QualifiedBacktestInput(
            configuration_id="cfg",
            handoff=handoff,
            qualification=invalid,
        )


def test_return_engine_benchmark_gap_becomes_limitation(qualified, policies, benchmark):
    shortened = benchmark.model_copy(
        update={
            "points": benchmark.points[:-1],
            "content_sha256": "0" * 64,
        }
    )
    # Rebuild via validation to obtain a correct hash for the shortened series.
    body = shortened.model_dump(mode="python", exclude={"content_sha256"})
    from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
    shortened = shortened.model_copy(update={"content_sha256": content_sha256(body)})
    result = compute_returns(
        ReturnEngineRequest(
            qualified_backtest=qualified,
            policy=policies["return"],
            benchmark=shortened,
        )
    )
    assert result.return_series.active_returns is None
    assert "P9_S4_BENCHMARK_UNAVAILABLE" in result.return_series.limitations

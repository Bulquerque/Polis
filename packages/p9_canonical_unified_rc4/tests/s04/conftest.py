from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    CandidateTerminalRecord,
    CandidateTerminalState,
    CashCategory,
    CashLedgerEntry,
    FillRecord,
    OrderRecord,
    OrderStatus,
    P8EvaluationHandoff,
    PositionSnapshot,
    Side,
    ValuationRecord,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m04_integrity_replay import (
    finalize_handoff_replay_hash,
    qualify_backtest,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.base_models import (
    AnnualizationPolicy,
    FrequencyMode,
    PointInTimeSeries,
    SeriesPoint,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.bundle_models import (
    MetricQualityPolicy,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
from quant_pipeline.phase_09.subphases.s04_performance_risk.distribution_models import (
    DistributionPolicy,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.drawdown_models import DrawdownPolicy
from quant_pipeline.phase_09.subphases.s04_performance_risk.execution_models import (
    CapacityPolicy,
    ExposureSnapshot,
    ImpactPolicy,
    LiquidityObservation,
    TargetOrderContext,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.factor_models import (
    BenchmarkAndFactorPanel,
    FactorObservation,
    FactorValue,
    RegressionCovariance,
    RegressionPolicy,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.registries import (
    default_factor_registry,
    default_metric_registry,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import (
    QualifiedBacktestInput,
    ReturnPolicy,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.risk_adjusted_models import (
    RiskAdjustedMetricPolicy,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.tail_models import TailRiskPolicy
from quant_pipeline.phase_09.subphases.s04_performance_risk.base_models import MinimumSamplePolicy

BASE = datetime(2024, 1, 1, tzinfo=UTC)
ZERO_HASH = "0" * 64


def day(index: int) -> datetime:
    return BASE + timedelta(days=index)


def build_trade_handoff(days: int = 140) -> P8EvaluationHandoff:
    order = OrderRecord(
        order_id="order-1",
        candidate_id="candidate-1",
        instrument_id="ABC",
        side=Side.BUY,
        quantity=Decimal("10"),
        decision_time=day(0),
        available_at=day(0),
        status=OrderStatus.FILLED,
    )
    fill = FillRecord(
        fill_id="fill-1",
        order_id="order-1",
        instrument_id="ABC",
        side=Side.BUY,
        quantity=Decimal("10"),
        price=Decimal("10"),
        fee=Decimal("1"),
        fill_time=day(0),
        available_at=day(0),
    )
    cash = CashLedgerEntry(
        entry_id="cash-fill",
        event_time=day(0),
        amount=Decimal("-101"),
        category=CashCategory.FILL,
        related_fill_id="fill-1",
    )
    valuations = []
    final_price = Decimal("10")
    for index in range(days):
        # Deterministic trend + cyclical volatility + one drawdown region.
        price = 10.0 + 0.018 * index + 0.25 * math.sin(index / 5)
        if 55 <= index <= 70:
            price -= 0.055 * (index - 54)
        if index > 70:
            price -= 0.88 * math.exp(-(index - 70) / 15)
        final_price = Decimal(str(round(price, 8)))
        market = final_price * Decimal("10")
        nav = Decimal("899") + market
        net_pnl = nav - Decimal("1000")
        gross_pnl = net_pnl + Decimal("1")
        valuations.append(
            ValuationRecord(
                valuation_time=day(index + 1),
                cash=Decimal("899"),
                market_value=market,
                gross_pnl=gross_pnl,
                costs=Decimal("1"),
                net_pnl=net_pnl,
                nav=nav,
            )
        )
    handoff = P8EvaluationHandoff(
        handoff_id="handoff:trial-1:outer-000",
        schema_version="1.0.0",
        run_id="run-1",
        cycle_id="cycle-1",
        trial_id="trial-1",
        fold_id="outer-000",
        capability="PRODUCTION",
        start_cash=Decimal("1000"),
        end_cash=Decimal("899"),
        p6_candidate_ids=("candidate-1",),
        p7_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.RANKED),
        ),
        p8_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.EXECUTED),
        ),
        orders=(order,),
        fills=(fill,),
        cash_entries=(cash,),
        lifecycle_events=(),
        final_positions=(
            PositionSnapshot(
                instrument_id="ABC",
                quantity=Decimal("10"),
                market_value=final_price * Decimal("10"),
            ),
        ),
        valuations=tuple(valuations),
        required_lifecycle_supported=True,
        replay_sha256=ZERO_HASH,
    )
    return finalize_handoff_replay_hash(handoff)


def make_series(series_id: str, timestamps: tuple[datetime, ...], values: list[float]) -> PointInTimeSeries:
    body = {
        "series_id": series_id,
        "series_version": "1.0.0",
        "points": tuple(
            SeriesPoint(timestamp=timestamp, value=float(value), available_at=timestamp)
            for timestamp, value in zip(timestamps, values)
        ),
    }
    return PointInTimeSeries(**body, content_sha256=content_sha256(body))


@pytest.fixture
def handoff() -> P8EvaluationHandoff:
    return build_trade_handoff()


@pytest.fixture
def qualified(handoff: P8EvaluationHandoff) -> QualifiedBacktestInput:
    receipt = qualify_backtest(handoff)
    return QualifiedBacktestInput(
        configuration_id="cfg-1",
        handoff=handoff,
        qualification=receipt,
    )


@pytest.fixture
def timestamps(handoff: P8EvaluationHandoff) -> tuple[datetime, ...]:
    return tuple(record.valuation_time for record in handoff.valuations[1:])


@pytest.fixture
def benchmark(timestamps: tuple[datetime, ...]) -> PointInTimeSeries:
    return make_series("benchmark", timestamps, [0.0002 + 0.0001 * math.sin(i / 10) for i in range(len(timestamps))])


@pytest.fixture
def risk_free(timestamps: tuple[datetime, ...]) -> PointInTimeSeries:
    return make_series("risk-free", timestamps, [0.00005 for _ in timestamps])


@pytest.fixture
def factor_panel(timestamps: tuple[datetime, ...]) -> BenchmarkAndFactorPanel:
    observations = []
    for index, timestamp in enumerate(timestamps):
        values = (
            FactorValue(factor_id="MKT_RF", value=0.001 * math.sin(index / 7)),
            FactorValue(factor_id="SMB", value=0.0007 * math.cos(index / 9)),
            FactorValue(factor_id="HML", value=0.0005 * math.sin(index / 11)),
            FactorValue(factor_id="RMW", value=0.0004 * math.cos(index / 13)),
            FactorValue(factor_id="CMA", value=0.0003 * math.sin(index / 15)),
            FactorValue(factor_id="MOM", value=0.0006 * math.cos(index / 8)),
        )
        observations.append(FactorObservation(timestamp=timestamp, available_at=timestamp, values=values))
    body = {"panel_id": "factors", "panel_version": "1.0.0", "observations": tuple(observations)}
    return BenchmarkAndFactorPanel(**body, content_sha256=content_sha256(body))


@pytest.fixture
def policies():
    minimum = MinimumSamplePolicy(
        policy_id="minimum",
        policy_version="1.0.0",
        minimum_return_observations=20,
        minimum_tail_observations=50,
        minimum_regression_observations=30,
        minimum_rolling_observations=20,
    )
    return {
        "return": ReturnPolicy(
            policy_id="return",
            policy_version="1.0.0",
            annualization=AnnualizationPolicy(
                policy_id="annual",
                policy_version="1.0.0",
                mode=FrequencyMode.EXPLICIT,
                periods_per_year=252.0,
            ),
        ),
        "distribution": DistributionPolicy(
            policy_id="distribution",
            policy_version="1.0.0",
            minimum_samples=minimum,
            rolling_windows=(20, 60),
        ),
        "tail": TailRiskPolicy(
            policy_id="tail",
            policy_version="1.0.0",
            confidence_levels=(0.95, 0.99),
            minimum_samples=minimum,
        ),
        "drawdown": DrawdownPolicy(policy_id="drawdown", policy_version="1.0.0"),
        "risk_adjusted": RiskAdjustedMetricPolicy(
            policy_id="risk-adjusted",
            policy_version="1.0.0",
            minimum_observations=20,
        ),
        "capacity": CapacityPolicy(
            policy_id="capacity",
            policy_version="1.0.0",
            impact=ImpactPolicy(policy_id="impact", policy_version="1.0.0"),
        ),
        "quality": MetricQualityPolicy(policy_id="quality", policy_version="1.0.0"),
        "regression": RegressionPolicy(
            policy_id="regression",
            policy_version="1.0.0",
            factor_model_ids=(("CAPM", "1.0.0"),),
            covariance=RegressionCovariance.HAC,
            hac_max_lags=3,
            rolling_window=40,
        ),
    }


@pytest.fixture
def execution_inputs(handoff: P8EvaluationHandoff):
    target = TargetOrderContext(
        target_id="target-1",
        order_id="order-1",
        instrument_id="ABC",
        target_quantity=Decimal("10"),
        arrival_price=Decimal("9.95"),
        decision_time=day(0),
        bid_price=Decimal("9.94"),
        ask_price=Decimal("9.96"),
    )
    liquidity = LiquidityObservation(
        instrument_id="ABC",
        timestamp=day(0),
        available_at=day(0),
        average_daily_volume=Decimal("100000"),
        daily_volatility=0.02,
        mid_price=Decimal("9.95"),
    )
    exposures = tuple(
        ExposureSnapshot(
            timestamp=record.valuation_time,
            gross_exposure=record.market_value,
            net_exposure=record.market_value,
            margin_used=record.market_value * Decimal("0.25"),
            nav=record.nav,
        )
        for record in handoff.valuations
    )
    return (target,), (liquidity,), exposures


@pytest.fixture
def registries():
    return default_metric_registry(), default_factor_registry()

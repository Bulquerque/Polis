from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path

import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.api import run_s3
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ArtifactRef,
    BeliefRecord,
    DistributionType,
    EmpiricalPayload,
    HorizonSpec,
    HorizonUnit,
    PathPayload,
    ProbabilityMeasure,
    QualityPolicy,
    RealizedSamplePanel,
    ReductionPolicy,
    S3Request,
    ScenarioPolicy,
    StressPolicy,
    StressTemplate,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import (
    AccountState,
    BorrowRecord,
    CandidateEconomicPackage,
    DependencePolicy,
    EuropeanOptionLeg,
    FactorDefinition,
    GreekPolicy,
    GreekVector,
    LinearLeg,
    LiquidityPolicy,
    LiquidityQuote,
    MarginFidelity,
    MarginPolicy,
    MarginRules,
    MarketLiquiditySnapshot,
    OptionType,
    PnLPolicy,
    ReconciliationPolicy,
    S4Request,
    ScenarioArtifactBundle,
    ShockKind,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)


def _source_ref(name: str) -> ArtifactRef:
    return ArtifactRef(artifact_id=name, content_sha256=hashlib.sha256(name.encode()).hexdigest())


@pytest.fixture
def linear_candidate() -> CandidateEconomicPackage:
    return CandidateEconomicPackage(
        candidate_id="C-LINEAR",
        canonical_candidate_id="CAN-LINEAR",
        strategy_family="LINEAR",
        currency="USD",
        unit_definition="one strategy unit",
        gross_notional_per_unit=1_000.0,
        maximum_loss_per_unit=1_000.0,
        maximum_loss_proof_status="PROVEN",
        legs=(LinearLeg(
            leg_id="L-LINEAR",
            instrument_id="INST-LINEAR",
            factor_id="B",
            quantity_per_unit=1.0,
            pnl_per_factor_unit=1_000.0,
            currency="USD",
            greeks_per_unit=GreekVector(
                delta=1_000.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0,
            ),
        ),),
        source_ref=_source_ref("p6-linear"),
    )


@pytest.fixture
def option_candidate() -> CandidateEconomicPackage:
    return CandidateEconomicPackage(
        candidate_id="C-CALL",
        canonical_candidate_id="CAN-CALL",
        strategy_family="LONG_OPTION",
        currency="USD",
        unit_definition="one call contract",
        entry_cash_flow_per_unit=-500.0,
        gross_notional_per_unit=10_000.0,
        maximum_loss_per_unit=500.0,
        maximum_loss_proof_status="PROVEN",
        legs=(EuropeanOptionLeg(
            leg_id="L-CALL",
            instrument_id="INST-CALL",
            underlying_factor_id="A",
            volatility_factor_id="VOL_A",
            rate_factor_id="RATE",
            option_type=OptionType.CALL,
            quantity_per_unit=1.0,
            spot=100.0,
            strike=100.0,
            volatility=0.20,
            risk_free_rate=0.03,
            dividend_yield=0.0,
            time_to_expiry_years=0.25,
            contract_multiplier=100.0,
            currency="USD",
        ),),
        source_ref=_source_ref("p6-call"),
    )


@pytest.fixture
def factor_definitions() -> tuple[FactorDefinition, ...]:
    return (
        FactorDefinition(factor_id="A", shock_kind=ShockKind.LOG_RETURN, unit="LOG_RETURN"),
        FactorDefinition(factor_id="VOL_A", shock_kind=ShockKind.ABSOLUTE, unit="VOL_POINTS"),
        FactorDefinition(factor_id="RATE", shock_kind=ShockKind.ABSOLUTE, unit="DECIMAL_RATE"),
        FactorDefinition(factor_id="B", shock_kind=ShockKind.SIMPLE_RETURN, unit="SIMPLE_RETURN"),
    )


@pytest.fixture
def s3_artifacts(tmp_path: Path, now: datetime):
    rng = np.random.default_rng(42)
    covariance = np.diag([0.02**2, 0.03**2, 0.002**2, 0.025**2])
    samples = rng.multivariate_normal(np.zeros(4), covariance, size=400)
    belief = BeliefRecord(
        belief_state_id="belief-s4",
        target_id="RISK_FACTORS",
        factor_ids=("A", "VOL_A", "RATE", "B"),
        distribution_type=DistributionType.EMPIRICAL,
        probability_measure=ProbabilityMeasure.PHYSICAL,
        forecast_horizon=HorizonSpec(value=1, unit=HorizonUnit.TRADING_SESSIONS),
        holding_horizon=HorizonSpec(value=1, unit=HorizonUnit.TRADING_SESSIONS),
        evaluation_horizon=HorizonSpec(value=1, unit=HorizonUnit.TRADING_SESSIONS),
        payload=EmpiricalPayload(samples=tuple(tuple(float(x) for x in row) for row in samples)),
        calibration_score=0.95,
        ood_score=0.05,
        disagreement_score=0.05,
        available_at=now,
        decision_time=now,
        source_ref=_source_ref("p5-s4"),
    )
    realized = RealizedSamplePanel(
        factor_ids=belief.factor_ids,
        samples=tuple(tuple(float(x) for x in row) for row in samples[:200]),
        available_at=now,
        decision_time=now,
    )
    request = S3Request(
        run_id="run-s4",
        cycle_id="cycle-s4",
        belief=belief,
        realized_samples=realized,
        strategy_families=("LINEAR", "LONG_OPTION"),
        scenario_policy=ScenarioPolicy(scenario_count=128, seed_entropy=2026),
        quality_policy=QualityPolicy(
            mean_relative_error_max=2.0,
            covariance_relative_error_max=2.0,
            quantile_absolute_error_max=2.0,
            tail_quantile_error_max=2.0,
        ),
        stress_policy=StressPolicy(templates=(StressTemplate(
            stress_id="joint-stress",
            factor_shocks={"A": -0.25, "VOL_A": 0.15, "RATE": 0.01, "B": -0.20},
            tags=("TAIL", "MARGIN"),
        ),)),
        reduction_policy=ReductionPolicy(
            target_count=48,
            preserve_tail_count=8,
            mean_error_max=2.0,
            covariance_error_max=2.0,
            tail_error_max=2.0,
        ),
    )
    root = tmp_path / "s3"
    result = run_s3(request, root)
    bundle = ScenarioArtifactBundle(
        root_path=str(root),
        full_scenarios_file="full_scenarios.npz",
        reduced_scenarios_file="reduced_scenarios.npz",
        stress_scenarios_file="stress_scenarios.npz",
        full_scenarios_sha256=result.full_scenarios.content_sha256,
        reduced_scenarios_sha256=result.reduced_scenarios.content_sha256,
        stress_scenarios_sha256=result.stress.stress_content_sha256,
    )
    return result, bundle


@pytest.fixture
def path_s3_artifacts(tmp_path: Path, now: datetime):
    rng = np.random.default_rng(99)
    paths = rng.normal(0.0, [0.02, 0.01, 0.001, 0.02], size=(120, 3, 4))
    belief = BeliefRecord(
        belief_state_id="belief-path",
        target_id="PATH_FACTORS",
        factor_ids=("A", "VOL_A", "RATE", "B"),
        distribution_type=DistributionType.PATH,
        probability_measure=ProbabilityMeasure.PHYSICAL,
        forecast_horizon=HorizonSpec(value=3, unit=HorizonUnit.TRADING_SESSIONS),
        holding_horizon=HorizonSpec(value=3, unit=HorizonUnit.TRADING_SESSIONS),
        evaluation_horizon=HorizonSpec(value=3, unit=HorizonUnit.TRADING_SESSIONS),
        payload=PathPayload(
            paths=tuple(tuple(tuple(float(x) for x in row) for row in path) for path in paths),
            step_labels=("D1", "D2", "D3"),
        ),
        calibration_score=0.95,
        ood_score=0.02,
        disagreement_score=0.02,
        available_at=now,
        decision_time=now,
        source_ref=_source_ref("p5-path"),
    )
    request = S3Request(
        run_id="run-path",
        cycle_id="cycle-path",
        belief=belief,
        strategy_families=("LINEAR",),
        scenario_policy=ScenarioPolicy(scenario_count=96, seed_entropy=45),
        stress_policy=StressPolicy(templates=(StressTemplate(
            stress_id="path-stress", factor_shocks={"A": -0.1, "B": -0.1},
        ),)),
        reduction_policy=ReductionPolicy(
            target_count=32, preserve_tail_count=4,
            mean_error_max=2.0, covariance_error_max=2.0, tail_error_max=2.0,
        ),
    )
    root = tmp_path / "s3-path"
    result = run_s3(request, root)
    bundle = ScenarioArtifactBundle(
        root_path=str(root),
        full_scenarios_file="full_scenarios.npz",
        reduced_scenarios_file="reduced_scenarios.npz",
        stress_scenarios_file="stress_scenarios.npz",
        full_scenarios_sha256=result.full_scenarios.content_sha256,
        reduced_scenarios_sha256=result.reduced_scenarios.content_sha256,
        stress_scenarios_sha256=result.stress.stress_content_sha256,
    )
    return result, bundle


@pytest.fixture
def liquidity_snapshot(now: datetime) -> MarketLiquiditySnapshot:
    return MarketLiquiditySnapshot(
        decision_time=now,
        quotes=(
            LiquidityQuote(
                instrument_id="INST-LINEAR", bid=99.9, ask=100.1,
                bid_size=500, ask_size=400, daily_volume=10_000, open_interest=50_000,
                quote_time=now, available_at=now,
            ),
            LiquidityQuote(
                instrument_id="INST-CALL", bid=4.9, ask=5.1,
                bid_size=100, ask_size=80, daily_volume=1_000, open_interest=5_000,
                quote_time=now, available_at=now,
            ),
        ),
    )


@pytest.fixture
def account_state() -> AccountState:
    return AccountState(
        currency="USD",
        available_cash=100_000.0,
        eligible_collateral=25_000.0,
        current_margin_used=5_000.0,
        margin_limit=75_000.0,
        cash_buffer_required=10_000.0,
        max_new_risk_capital=50_000.0,
    )


@pytest.fixture
def s4_request(
    now,
    s3_artifacts,
    linear_candidate,
    option_candidate,
    factor_definitions,
    liquidity_snapshot,
    account_state,
) -> S4Request:
    s3_result, bundle = s3_artifacts
    return S4Request(
        run_id="run-s4",
        cycle_id="cycle-s4",
        decision_time=now,
        s3_result=s3_result,
        scenario_artifacts=bundle,
        candidates=(linear_candidate, option_candidate),
        factor_definitions=factor_definitions,
        step_year_fractions=(1.0 / 252.0,),
        liquidity_snapshot=liquidity_snapshot,
        account_state=account_state,
        borrow_records=(
            BorrowRecord(instrument_id="INST-LINEAR", available=True, quantity_available=10_000, annual_rate=0.02),
            BorrowRecord(instrument_id="INST-CALL", available=True, quantity_available=10_000, annual_rate=0.02),
        ),
        margin_rules=MarginRules(fidelity=MarginFidelity.SPAN_LIKE_MODEL),
        pnl_policy=PnLPolicy(use_reduced_scenarios=True),
        dependence_policy=DependencePolicy(minimum_effective_samples=10),
        greek_policy=GreekPolicy(),
        liquidity_policy=LiquidityPolicy(),
        margin_policy=MarginPolicy(),
        reconciliation_policy=ReconciliationPolicy(require_physical_reconciliation=True),
    )

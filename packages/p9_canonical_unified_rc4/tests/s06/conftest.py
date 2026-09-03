from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    BreachDirection,
    EvidenceClass,
    OutputSemantics,
    RunContext,
    S5QualificationReference,
    ScenarioClass,
    SeedPolicy,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    CapacityRequest,
    ConstraintDefinition,
    DRORequest,
    EmpiricalScenarioDistribution,
    EVTRequest,
    ExecutionLeg,
    ExposureRecord,
    FactorAxis,
    FactorBound,
    FactorPath,
    FactorShock,
    FailureCondition,
    MaterialRiskDefinition,
    QuadraticResponseModel,
    S6RunRequest,
    ScenarioProposal,
    ScenarioRegistryRequest,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import (
    AmbiguitySetPolicy,
    EVTPolicy,
    ReverseStressPolicy,
)

H = "0" * 64


@pytest.fixture
def context() -> RunContext:
    decision = datetime(2026, 1, 10, tzinfo=UTC)
    return RunContext(
        run_id="run-1",
        cycle_id="cycle-1",
        experiment_id="exp-1",
        configuration_id="cfg-1",
        decision_time=decision,
        available_at=decision - timedelta(days=1),
        code_sha256=H,
        data_sha256=H,
    )


@pytest.fixture
def response_model() -> QuadraticResponseModel:
    payload = {
        "factor_ids": ("equity", "volatility"),
        "baseline": 0.0,
        "linear": (-1.0, -0.5),
        "quadratic": ((-0.2, -0.1), (-0.1, -0.1)),
    }
    return QuadraticResponseModel(
        model_id="quadratic-pnl-v1",
        factor_ids=("equity", "volatility"),
        units=("decimal", "decimal"),
        baseline_value=0.0,
        linear_coefficients=(-1.0, -0.5),
        quadratic_matrix=((-0.2, -0.1), (-0.1, -0.1)),
        semantics=OutputSemantics.PNL,
        model_sha256=content_sha256(payload),
    )


@pytest.fixture
def scenario_request(context: RunContext) -> ScenarioRegistryRequest:
    proposal = ScenarioProposal(
        scenario_id="historical-crisis-1",
        name="Synthetic equity-volatility crisis",
        scenario_class=ScenarioClass.HISTORICAL_REPLAY,
        created_at=context.decision_time - timedelta(days=2),
        purpose="structural stress qualification",
        approved_uses=("RESEARCH", "QUALIFICATION"),
        shocks=(
            FactorShock(factor_id="equity", value=-1.0, unit="decimal"),
            FactorShock(factor_id="volatility", value=1.0, unit="decimal"),
        ),
        horizon_days=4,
        severity_label="SEVERE",
        plausibility_label="PLAUSIBLE",
    )
    return ScenarioRegistryRequest(
        context=context,
        s5_qualification=S5QualificationReference(
            bundle_id="s5-bundle",
            bundle_sha256=H,
            qualification_status="PROVISIONALLY_ROBUST",
        ),
        proposals=(proposal,),
        material_risks=(
            MaterialRiskDefinition(
                risk_id="market-risk",
                factor_ids=("equity", "volatility"),
                materiality_weight=1.0,
            ),
        ),
    )


@pytest.fixture
def factor_path(context: RunContext) -> FactorPath:
    start = context.decision_time - timedelta(days=10)
    return FactorPath(
        path_id="crisis-path",
        timestamps=tuple(start + timedelta(days=index) for index in range(4)),
        factor_ids=("equity", "volatility"),
        values=((0.0, 0.0), (-0.8, 0.5), (-0.4, 0.3), (0.9, -0.2)),
        units=("decimal", "decimal"),
        evidence_classes=(
            EvidenceClass.OBSERVED_HISTORICAL,
            EvidenceClass.OBSERVED_HISTORICAL,
        ),
    )


@pytest.fixture
def capacity_request(context: RunContext) -> CapacityRequest:
    return CapacityRequest(
        context=context,
        base_aum=1_000_000.0,
        annual_gross_return=0.18,
        annual_turnover_ratio=4.0,
        aum_grid=(250_000.0, 1_000_000.0, 4_000_000.0, 12_000_000.0),
        legs=(
            ExecutionLeg(
                instrument_id="asset-a",
                trade_weight=0.6,
                gross_exposure_multiple=0.8,
                average_daily_volume=2_000_000.0,
                spread_bps=4.0,
                impact_coefficient_bps=40.0,
                impact_exponent=1.5,
                max_participation_rate=0.15,
                margin_rate=0.2,
                evidence_class=EvidenceClass.OBSERVED_HISTORICAL,
            ),
            ExecutionLeg(
                instrument_id="asset-b",
                trade_weight=0.4,
                gross_exposure_multiple=0.5,
                average_daily_volume=1_000_000.0,
                spread_bps=6.0,
                impact_coefficient_bps=55.0,
                impact_exponent=1.6,
                max_participation_rate=0.12,
                margin_rate=0.25,
                evidence_class=EvidenceClass.OBSERVED_HISTORICAL,
            ),
        ),
    )


@pytest.fixture
def full_request(
    context: RunContext,
    scenario_request: ScenarioRegistryRequest,
    factor_path: FactorPath,
    response_model: QuadraticResponseModel,
    capacity_request: CapacityRequest,
) -> S6RunRequest:
    generator = np.random.default_rng(123)
    body = generator.normal(0.1, 0.15, 900)
    tail = 0.6 + generator.pareto(3.0, 100) * 0.25
    losses = tuple(float(value) for value in np.concatenate([body, tail]))
    evt = EVTRequest(
        context=context,
        loss_series_id="portfolio-loss",
        losses=losses,
        seed_policy=SeedPolicy(root_entropy=4321),
        policy=EVTPolicy(
            threshold_quantile=0.9,
            minimum_exceedances=50,
            parameter_bootstrap_replicates=80,
            maximum_absolute_residual_autocorrelation=0.25,
        ),
    )
    dro = DRORequest(
        context=context,
        distribution=EmpiricalScenarioDistribution(
            distribution_id="joint-scenarios",
            scenario_ids=("s1", "s2", "s3", "s4"),
            state_vectors=((-1.0, 0.2), (-0.3, 0.1), (0.2, -0.1), (0.8, -0.2)),
            losses=(1.2, 0.5, -0.1, -0.4),
            scores=(-1.0, 0.0, 0.5, 1.0),
        ),
        policy=AmbiguitySetPolicy(
            radius_grid=(0.0, 0.1, 0.3),
            radius_calibration_id="bootstrap-radius-v1",
        ),
    )
    return S6RunRequest(
        scenario_registry=scenario_request,
        crisis_factor_path=factor_path,
        crisis_exposures=(
            ExposureRecord(
                exposure_id="exp-equity",
                position_id="pos-1",
                current_factor_id="equity",
                notional=1_000_000.0,
                linear_sensitivity=1.0,
                quadratic_sensitivity=-0.05,
                evidence_class=EvidenceClass.OBSERVED_HISTORICAL,
            ),
            ExposureRecord(
                exposure_id="exp-vol",
                position_id="pos-2",
                current_factor_id="volatility",
                notional=500_000.0,
                linear_sensitivity=-0.4,
                quadratic_sensitivity=-0.02,
                evidence_class=EvidenceClass.OBSERVED_HISTORICAL,
            ),
        ),
        crisis_scenario_id="historical-crisis-1",
        sensitivity_response_model=response_model,
        sensitivity_axes=(
            FactorAxis(
                factor_id="equity",
                grid_values=(-1.0, -0.5, 0.0, 0.5, 1.0),
                observed_min=-0.8,
                observed_max=0.8,
            ),
            FactorAxis(
                factor_id="volatility",
                grid_values=(-1.0, 0.0, 1.0),
                observed_min=-1.0,
                observed_max=1.0,
            ),
        ),
        sensitivity_constraints=(
            ConstraintDefinition(
                constraint_id="loss-limit",
                threshold=-0.8,
                breach_direction=BreachDirection.LESS_THAN_OR_EQUAL,
            ),
        ),
        evt=evt,
        dro=dro,
        capacity=capacity_request,
        reverse_bounds=(
            FactorBound(factor_id="equity", lower=-2.0, upper=2.0, norm_weight=1.0),
            FactorBound(factor_id="volatility", lower=-2.0, upper=2.0, norm_weight=1.0),
        ),
        reverse_failure_condition=FailureCondition(
            condition_id="portfolio-loss-limit",
            threshold=-0.8,
            breach_direction=BreachDirection.LESS_THAN_OR_EQUAL,
        ),
        reverse_seed_policy=SeedPolicy(root_entropy=9876),
        reverse_policy=ReverseStressPolicy(minimum_safe_distance=0.2),
    )

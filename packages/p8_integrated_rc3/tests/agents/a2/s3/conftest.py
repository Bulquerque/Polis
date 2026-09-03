from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ArtifactRef, BeliefRecord, DistributionType, EmpiricalPayload, HorizonSpec,
    HorizonUnit, ParametricPayload, ProbabilityMeasure, QualityPolicy,
    RealizedSamplePanel, ReductionPolicy, S3Request, ScenarioPolicy, StressPolicy,
    StressTemplate,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def normal_belief(now: datetime) -> BeliefRecord:
    return BeliefRecord(
        belief_state_id="belief-1", target_id="RETURNS", factor_ids=("A", "B"),
        distribution_type=DistributionType.PARAMETRIC,
        probability_measure=ProbabilityMeasure.PHYSICAL,
        forecast_horizon=HorizonSpec(value=24, unit=HorizonUnit.HOURS),
        holding_horizon=HorizonSpec(value=24, unit=HorizonUnit.HOURS),
        evaluation_horizon=HorizonSpec(value=24, unit=HorizonUnit.HOURS),
        payload=ParametricPayload(
            family="NORMAL", mean=(0.01, -0.005),
            covariance=((0.04, 0.01), (0.01, 0.09)),
        ),
        calibration_score=0.95, ood_score=0.05, disagreement_score=0.10,
        available_at=now, decision_time=now,
        source_ref=ArtifactRef(artifact_id="p5-belief", content_sha256=hashlib.sha256(b"p5").hexdigest()),
    )


@pytest.fixture
def empirical_belief(now: datetime) -> BeliefRecord:
    samples = tuple((float(x), float(y)) for x, y in np.random.default_rng(7).normal(size=(100, 2)))
    return BeliefRecord(
        belief_state_id="belief-emp", target_id="RETURNS", factor_ids=("A", "B"),
        distribution_type=DistributionType.EMPIRICAL,
        probability_measure=ProbabilityMeasure.PHYSICAL,
        forecast_horizon=HorizonSpec(value=1, unit=HorizonUnit.TRADING_SESSIONS),
        holding_horizon=HorizonSpec(value=1, unit=HorizonUnit.TRADING_SESSIONS),
        evaluation_horizon=HorizonSpec(value=1, unit=HorizonUnit.TRADING_SESSIONS),
        payload=EmpiricalPayload(samples=samples), calibration_score=0.9,
        ood_score=0.1, disagreement_score=0.1, available_at=now, decision_time=now,
        source_ref=ArtifactRef(artifact_id="p5-emp", content_sha256=hashlib.sha256(b"emp").hexdigest()),
    )


@pytest.fixture
def realized(now: datetime) -> RealizedSamplePanel:
    rng = np.random.default_rng(44)
    values = rng.multivariate_normal((0.01, -0.005), ((0.04, 0.01), (0.01, 0.09)), size=300)
    return RealizedSamplePanel(
        factor_ids=("A", "B"), samples=tuple(tuple(float(v) for v in row) for row in values),
        available_at=now, decision_time=now,
    )


@pytest.fixture
def s3_request(normal_belief: BeliefRecord, realized: RealizedSamplePanel) -> S3Request:
    return S3Request(
        run_id="run-1", cycle_id="cycle-1", belief=normal_belief,
        realized_samples=realized, scenario_policy=ScenarioPolicy(scenario_count=128, seed_entropy=99),
        quality_policy=QualityPolicy(mean_relative_error_max=2.0, covariance_relative_error_max=0.8, quantile_absolute_error_max=0.8, tail_quantile_error_max=0.8),
        stress_policy=StressPolicy(templates=(StressTemplate(stress_id="gap", factor_shocks={"A": -0.2, "B": -0.3}, tags=("TAIL",)),)),
        reduction_policy=ReductionPolicy(target_count=32, preserve_tail_count=4, mean_error_max=0.5, covariance_error_max=0.7, tail_error_max=0.7),
    )

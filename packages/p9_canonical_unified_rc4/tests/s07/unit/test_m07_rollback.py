from __future__ import annotations

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m05_drift import CrossChannelAgreement
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m06_sequential import SequentialModelSet
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m07_rollback import (
    LiveExecutionMetrics,
    LiveHealthState,
    RollbackPolicy,
    StressCapacityQualification,
    evaluate_live_health,
)

from tests.s07.conftest import h

pytestmark = pytest.mark.unit


def comparison_set():
    return SequentialModelSet(
        champion_policy_id="champion",
        retained_policy_ids=("champion",),
        comparisons=(),
        result_sha256=h("comparison"),
    )


def drift(confirmed: bool = False):
    return CrossChannelAgreement(
        alerted_channel_ids=("cost",) if confirmed else (),
        confirmed=confirmed,
        hard_breach_present=False,
        agreement_ratio=0.5 if confirmed else 0.0,
    )


def stress(hard=()):
    return StressCapacityQualification(
        qualification_state="STRESS_RESILIENT",
        reverse_stress_distance=2.0,
        capacity_limit_ratio=1.0,
        hard_blocking_reason_codes=hard,
    )


def test_healthy_state():
    result = evaluate_live_health(
        LiveExecutionMetrics(
            observation_count=100,
            realized_net_alpha=0.02,
            reference_net_alpha=0.01,
            mean_cost_error_bps=1.0,
            capacity_ratio_to_approved=1.0,
        ),
        drift(),
        comparison_set(),
        stress(),
        RollbackPolicy(minimum_live_observations=20),
    )
    assert result.state is LiveHealthState.HEALTHY
    assert result.p0_authorization_required


def test_hard_breach_recommends_quarantine():
    result = evaluate_live_health(
        LiveExecutionMetrics(
            observation_count=100,
            realized_net_alpha=0.02,
            reference_net_alpha=0.01,
            mean_cost_error_bps=1.0,
            capacity_ratio_to_approved=1.0,
            hard_risk_breach_codes=("RISK_LIMIT",),
        ),
        drift(),
        comparison_set(),
        stress(),
        RollbackPolicy(),
    )
    assert result.state is LiveHealthState.QUARANTINE_RECOMMENDED


def test_large_cost_error_recommends_rollback():
    result = evaluate_live_health(
        LiveExecutionMetrics(
            observation_count=100,
            realized_net_alpha=0.02,
            reference_net_alpha=0.02,
            mean_cost_error_bps=25.0,
            capacity_ratio_to_approved=1.0,
        ),
        drift(),
        comparison_set(),
        stress(),
        RollbackPolicy(),
    )
    assert result.state is LiveHealthState.ROLLBACK_RECOMMENDED

from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import build_prequential_stream
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m02_shadow import (
    DeploymentStage,
    PolicyExecutionOutput,
    PolicyRole,
    PolicySpecification,
    build_shadow_execution_plan,
    evaluate_shadow_comparability,
)

from tests.s07.conftest import h, prediction

pytestmark = pytest.mark.unit


def policy(policy_id: str, role: PolicyRole) -> PolicySpecification:
    return PolicySpecification(
        policy_id=policy_id,
        policy_version="1.0.0",
        role=role,
        code_sha256=h(policy_id),
        resource_budget_units=10,
        seed_entropy=7,
        authorized_stage=DeploymentStage.SHADOW_ONLY,
    )


def test_shadow_plan_uses_common_snapshot(base_time):
    record = build_prequential_stream((prediction("p", base_time - timedelta(days=2)),), ()).records[0]
    plan = build_shadow_execution_plan(
        (record,),
        policy("champion", PolicyRole.CHAMPION),
        (policy("challenger", PolicyRole.CHALLENGER),),
    )
    assert len(plan.entries) == 2
    assert len({entry.information_set_hash for entry in plan.entries}) == 1


def test_comparability_detects_complete_cohort(base_time):
    record = build_prequential_stream((prediction("p", base_time - timedelta(days=2)),), ()).records[0]
    plan = build_shadow_execution_plan(
        (record,),
        policy("champion", PolicyRole.CHAMPION),
        (policy("challenger", PolicyRole.CHALLENGER),),
    )
    outputs = tuple(
        PolicyExecutionOutput(
            cohort_id=entry.cohort_id,
            prediction_event_id=entry.prediction_event_id,
            policy_id=entry.policy_id,
            policy_version=entry.policy_version,
            information_set_hash=entry.information_set_hash,
            stage=entry.stage,
            started_at=base_time,
            completed_at=base_time,
            output_artifact_id=f"output-{entry.policy_id}",
            output_sha256=h(f"output-{entry.policy_id}"),
            execution_status="SUCCESS",
            resource_units_used=5,
        )
        for entry in plan.entries
    )
    receipt = evaluate_shadow_comparability(plan, outputs)
    assert receipt.comparable_cohort_count == 1
    assert receipt.common_snapshot_verified


def test_incomplete_policy_outputs_are_limited(base_time):
    record = build_prequential_stream((prediction("p", base_time - timedelta(days=2)),), ()).records[0]
    plan = build_shadow_execution_plan(
        (record,),
        policy("champion", PolicyRole.CHAMPION),
        (policy("challenger", PolicyRole.CHALLENGER),),
    )
    entry = plan.entries[0]
    output = PolicyExecutionOutput(
        cohort_id=entry.cohort_id,
        prediction_event_id=entry.prediction_event_id,
        policy_id=entry.policy_id,
        policy_version=entry.policy_version,
        information_set_hash=entry.information_set_hash,
        stage=entry.stage,
        started_at=base_time,
        completed_at=base_time,
        output_artifact_id="only-one",
        output_sha256=h("only-one"),
        execution_status="SUCCESS",
        resource_units_used=1,
    )
    receipt = evaluate_shadow_comparability(plan, (output,))
    assert receipt.incomplete_cohort_count == 1
    assert "P9_LIVE_SHADOW_EVIDENCE_INCOMPLETE" in receipt.reason_codes

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_pipeline.phase_05_underlying_forecasts import (
    ExecutionMode,
    ModuleAction,
    ModuleRequest,
    P5ExecutionContext,
    RunIdentity,
    run_module,
)
from quant_pipeline.phase_05_underlying_forecasts.domain.core import ModuleStatus


def context(tmp_path, mode=ExecutionMode.RUNTIME_INFERENCE):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return P5ExecutionContext(
        identity=RunIdentity(
            run_id="run",
            cycle_id="cycle",
            as_of_time=now,
            generated_at=now + timedelta(hours=1),
        ),
        mode=mode,
        artifact_root=tmp_path,
    )


def test_missing_required_input_is_rejected(tmp_path):
    result = run_module(
        ModuleRequest(module_id="P5.S3.M01", action=ModuleAction.PREDICT),
        context(tmp_path),
    )
    assert result.status is ModuleStatus.REJECTED
    assert result.errors[0].code == "P5-CONTRACT-002"


def test_wrong_action_is_rejected(tmp_path):
    result = run_module(
        ModuleRequest(module_id="P5.S3.M01", action=ModuleAction.FIT),
        context(tmp_path),
    )
    assert result.status is ModuleStatus.REJECTED
    assert result.errors[0].code == "P5-CONTRACT-003"


def test_wrong_execution_mode_is_rejected(tmp_path):
    result = run_module(
        ModuleRequest(
            module_id="P5.S2.M04",
            action=ModuleAction.FIT,
            payload={
                "resolver_spec_registry": {},
                "resolver_view_binding_registry": {},
                "training_target_panel": {},
                "authorized_consumer_view_registry": {},
                "temporal_evaluation_plan": {},
            },
        ),
        context(tmp_path, ExecutionMode.RUNTIME_INFERENCE),
    )
    assert result.status is ModuleStatus.REJECTED
    assert result.errors[0].code == "P5-CONTRACT-004"


def test_optional_capability_is_skipped_without_fake_output(tmp_path):
    result = run_module(
        ModuleRequest(
            module_id="P5.S3.M04",
            action=ModuleAction.PREDICT,
            payload={
                "qualified_resolver_registry": {"records": []},
                "authorized_consumer_view_registry": {"views": []},
            },
        ),
        context(tmp_path),
    )
    assert result.status is ModuleStatus.SKIPPED
    assert not result.outputs
    assert result.warnings


def test_p4_native_hash_mismatch_is_rejected(tmp_path):
    from copy import deepcopy
    from .fixtures import build_fixture

    fixture = build_fixture()
    handoff = deepcopy(fixture["phase5_feature_handoff_manifest"])
    handoff["records"][0]["record_count"] += 1
    result = run_module(
        ModuleRequest(
            module_id="P5.S1.M01",
            action=ModuleAction.RUN,
            payload={
                "phase5_feature_handoff_manifest": handoff,
                "model_consumer_view_manifest": fixture["model_consumer_view_manifest"],
                "model_consumer_view_bundle": fixture["model_consumer_view_bundle"],
                "p4_quality_gate_decision": fixture["p4_quality_gate_decision"],
                "p4_artifact_catalog": fixture["p4_artifact_catalog"],
            },
        ),
        P5ExecutionContext(
            identity=RunIdentity(
                run_id="run", cycle_id="cycle-001",
                as_of_time=fixture["as_of_time"], generated_at=fixture["generated_at"],
            ),
            mode=ExecutionMode.VALIDATION,
            artifact_root=tmp_path,
        ),
    )
    assert result.status is ModuleStatus.REJECTED
    assert not result.outputs

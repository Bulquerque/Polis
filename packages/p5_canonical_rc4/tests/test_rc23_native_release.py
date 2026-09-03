from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from quant_pipeline.phase_05_underlying_forecasts import ExecutionMode, PhaseRunner
from quant_pipeline.phase_05_underlying_forecasts.boundary import canonical_sha256
from quant_pipeline.phase_05_underlying_forecasts.domain.core import ModuleStatus
from quant_pipeline.phase_05_underlying_forecasts.errors import ContractError, DataQualityError
from quant_pipeline.phase_05_underlying_forecasts.registry import list_modules
from quant_pipeline.phase_05_underlying_forecasts.services.p4_boundary import normalize_passports
from quant_pipeline.phase_05_underlying_forecasts.subphases import s2

from .fixtures import build_fixture
from .test_full_pipeline import (
    _context,
    offline_requests,
    publication_requests,
    runtime_requests,
)


def test_native_p4_v149_full_45_module_execution(tmp_path):
    fixture = build_fixture(days=160)
    offline = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(
        offline_requests(fixture)
    )
    runtime = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.RUNTIME_INFERENCE)).run(
        runtime_requests(), initial_artifacts=offline.artifacts
    )
    publication = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.PUBLICATION)).run(
        publication_requests(), initial_artifacts=runtime.artifacts
    )
    results = offline.results + runtime.results + publication.results
    assert {result.module_id for result in results} == {module.module_id for module in list_modules()}
    assert len(results) == 45
    assert all(result.status not in {ModuleStatus.FAILED, ModuleStatus.REJECTED} for result in results)
    assert "underlying_forecast_panel" in publication.artifacts
    assert "phase5_consumption_receipt" in offline.artifacts


def test_native_view_bundle_is_reference_only_and_horizon_preserved(tmp_path):
    fixture = build_fixture()
    offline = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(
        offline_requests(fixture)[:2]
    )
    assert offline.status in {ModuleStatus.SUCCESS, ModuleStatus.DEGRADED}
    context = _context(tmp_path, fixture, ExecutionMode.VALIDATION)
    registry = context.artifact_store.read(offline.artifacts["authorized_consumer_view_registry"])
    assert registry["views"]
    assert all(view["horizon_preserved"] for view in registry["views"])
    assert all(row["payload_copied"] is False for row in fixture["model_consumer_view_bundle"]["records"])


def test_native_reference_mismatch_fails_closed(tmp_path):
    fixture = build_fixture()
    bundle = deepcopy(fixture["model_consumer_view_bundle"])
    bundle["records"][0]["artifact_references"][0]["record_count"] += 1
    bundle["content_hash"] = canonical_sha256({
        "records": bundle["records"], "metadata": bundle["metadata"], "alias_of": bundle["alias_of"]
    })
    requests = list(offline_requests(fixture))
    payload = dict(requests[0].payload)
    payload["model_consumer_view_bundle"] = bundle
    requests[0] = requests[0].model_copy(update={"payload": payload})
    result = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run((requests[0],))
    assert result.status is ModuleStatus.FAILED
    assert result.results[0].status is ModuleStatus.REJECTED


def test_passport_requires_explicit_budget():
    fixture = build_fixture()
    with pytest.raises(DataQualityError, match="lacks budget record"):
        normalize_passports(
            fixture["approved_hypothesis_passport_registry"],
            {"records": []},
            fixture["research_attempt_ledger"],
        )


def test_purging_and_holdout_remain_sealed_under_native_grain():
    fixture = build_fixture(days=100)
    targets, registry, manifest, _ = s2.m01({
        "p5_offline_training_outcome_bundle": fixture["p5_offline_training_outcome_bundle"],
        "p5_hypothesis_confirmation_registry": {"records": []},
    }).values
    plan, receipt = s2.m02({
        "training_dataset_manifest": manifest,
        "training_target_panel": targets,
        "target_definition_registry": registry,
    }).values
    assert receipt["sealed_holdout"] == "TEST"
    assert receipt["excluded_from_development_metrics"] is True
    assert set(plan["partitions"]) == {"TRAIN", "VALIDATION", "CALIBRATION", "TEST"}
    assert all(plan["partitions"][name] for name in plan["partitions"])


def test_p4_future_handoff_clock_is_rejected(tmp_path):
    fixture = build_fixture()
    handoff = deepcopy(fixture["phase5_feature_handoff_manifest"])
    handoff["created_at"] = (fixture["generated_at"] + timedelta(seconds=1)).isoformat()
    handoff["content_hash"] = canonical_sha256({
        "records": handoff["records"], "metadata": handoff["metadata"], "alias_of": handoff["alias_of"]
    })
    requests = list(offline_requests(fixture))
    payload = dict(requests[0].payload)
    payload["phase5_feature_handoff_manifest"] = handoff
    requests[0] = requests[0].model_copy(update={"payload": payload})
    result = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run((requests[0],))
    assert result.status is ModuleStatus.FAILED
    assert result.results[0].status is ModuleStatus.REJECTED

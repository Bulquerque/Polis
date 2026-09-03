from __future__ import annotations

from quant_pipeline.phase_05_underlying_forecasts import (
    ExecutionMode,
    ModuleAction,
    ModuleRequest,
    P5ExecutionContext,
    PhaseRunner,
    RunIdentity,
)
from quant_pipeline.phase_05_underlying_forecasts.domain.core import ModuleStatus

from .fixtures import build_fixture


def _context(tmp_path, fixture, mode):
    return P5ExecutionContext(
        identity=RunIdentity(
            run_id=f"run-{mode.value.lower()}",
            cycle_id="cycle-001",
            as_of_time=fixture["as_of_time"],
            generated_at=fixture["generated_at"],
            seed=42,
        ),
        mode=mode,
        artifact_root=tmp_path / "artifacts",
    )


def _request(module_id, action, payload=None):
    return ModuleRequest(module_id=module_id, action=action, payload=payload or {})


def offline_requests(fixture):
    return (
        _request("P5.S1.M01", ModuleAction.RUN, {
            "phase5_feature_handoff_manifest": fixture["phase5_feature_handoff_manifest"],
            "model_consumer_view_manifest": fixture["model_consumer_view_manifest"],
            "model_consumer_view_bundle": fixture["model_consumer_view_bundle"],
            "p4_quality_gate_decision": fixture["p4_quality_gate_decision"],
            "p4_artifact_catalog": fixture["p4_artifact_catalog"],
        }),
        _request("P5.S1.M02", ModuleAction.RUN),
        _request("P5.S1.M03", ModuleAction.RUN, {
            "approved_hypothesis_passport_registry": fixture["approved_hypothesis_passport_registry"],
            "hypothesis_budget_report": fixture["hypothesis_budget_report"],
            "research_attempt_ledger": fixture["research_attempt_ledger"],
            "rejected_feature_graveyard": fixture["rejected_feature_graveyard"],
            "feature_observer_registry": fixture["feature_observer_registry"],
            "perspective_conflict_panel": fixture["perspective_conflict_panel"],
        }),
        _request("P5.S1.M04", ModuleAction.RUN),
        _request("P5.S1.M05", ModuleAction.RUN),
        _request("P5.S2.M01", ModuleAction.RUN, {
            "p5_offline_training_outcome_bundle": fixture["p5_offline_training_outcome_bundle"],
        }),
        _request("P5.S2.M02", ModuleAction.RUN, {
            "representation_fold_plan": fixture["representation_fold_plan"],
        }),
        _request("P5.S2.M03", ModuleAction.RUN),
        _request("P5.S2.M04", ModuleAction.FIT, {
            "representation_quality_report": fixture["representation_quality_report"],
        }),
        _request("P5.S2.M05", ModuleAction.VALIDATE, {
            "hypothesis_budget_report": fixture["hypothesis_budget_report"],
        }),
    )


def runtime_requests():
    return tuple(
        [_request(f"P5.S3.M0{index}", ModuleAction.PREDICT) for index in range(1, 6)]
        + [_request(f"P5.S4.M0{index}", ModuleAction.PREDICT) for index in range(1, 6)]
        + [_request(f"P5.S5.M0{index}", ModuleAction.PREDICT) for index in range(1, 6)]
        + [_request("P5.S5.M06", ModuleAction.VALIDATE)]
        + [_request(f"P5.S6.M0{index}", ModuleAction.PREDICT) for index in range(1, 4)]
        + [_request("P5.S6.M04", ModuleAction.VALIDATE)]
        + [_request(f"P5.S7.M0{index}", ModuleAction.PREDICT) for index in range(1, 4)]
        + [_request("P5.S7.M04", ModuleAction.RUN), _request("P5.S7.M05", ModuleAction.RUN)]
        + [_request("P5.S8.M01", ModuleAction.RUN), _request("P5.S8.M02", ModuleAction.VALIDATE)]
        + [_request("P5.S8.M03", ModuleAction.RUN), _request("P5.S8.M04", ModuleAction.RUN)]
        + [_request("P5.S8.M05", ModuleAction.RUN)]
    )


def publication_requests():
    return (
        _request("P5.S9.M01", ModuleAction.PUBLISH),
        _request("P5.S9.M02", ModuleAction.PUBLISH),
        _request("P5.S9.M03", ModuleAction.PUBLISH),
        _request("P5.S9.M04", ModuleAction.PUBLISH),
        _request("P5.S9.M05", ModuleAction.PUBLISH),
    )


def test_full_offline_runtime_publication_pipeline(tmp_path):
    fixture = build_fixture()
    offline = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(
        offline_requests(fixture)
    )
    assert offline.status in {ModuleStatus.SUCCESS, ModuleStatus.DEGRADED}
    assert "qualified_resolver_registry" in offline.artifacts
    assert "oof_validation_observation_panel" in offline.artifacts

    runtime = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.RUNTIME_INFERENCE)).run(
        runtime_requests(), initial_artifacts=offline.artifacts
    )
    assert runtime.status in {ModuleStatus.SUCCESS, ModuleStatus.DEGRADED}
    assert "ensemble_forecast_panel" in runtime.artifacts
    assert "covariance_forecast_registry" in runtime.artifacts
    assert all(result.status not in {ModuleStatus.FAILED, ModuleStatus.REJECTED} for result in runtime.results)
    for result in runtime.results:
        if result.status in {ModuleStatus.SUCCESS, ModuleStatus.DEGRADED}:
            assert result.outputs
        if result.status is ModuleStatus.SKIPPED:
            assert not result.outputs

    publication = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.PUBLICATION)).run(
        publication_requests(), initial_artifacts=runtime.artifacts
    )
    assert publication.status in {ModuleStatus.SUCCESS, ModuleStatus.DEGRADED}
    assert "underlying_forecast_panel" in publication.artifacts
    assert "phase5_output_handoff_manifest" in publication.artifacts

    context = _context(tmp_path, fixture, ExecutionMode.VALIDATION)
    panel = context.artifact_store.read(publication.artifacts["underlying_forecast_panel"])
    assert panel["records"]
    assert all(row["q05"] <= row["q50"] <= row["q95"] for row in panel["records"])
    assert all(row["underlying"] != "UNKNOWN" for row in panel["records"])


def test_replay_is_byte_deterministic(tmp_path):
    fixture = build_fixture()
    first = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(
        offline_requests(fixture)
    )
    second = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(
        offline_requests(fixture)
    )
    for name in first.artifacts:
        assert first.artifacts[name].content_hash == second.artifacts[name].content_hash

"""P4-fed P5 OFFLINE→RUNTIME→PUBLICATION runner."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from typing import Any

from .data_projection import (
    adapt_p4_feature_matrix_for_p5,
    adapt_p4_research_for_p5,
    build_p5_outcome_bundle_from_p4,
)
from .temporal_policy import _p5_request, install_p5_5d_evidence_compatibility

def run_live_p5_publication(p5_source: Path, p4: dict[str, Any]) -> dict[str, Any]:
    p5_compatibility = install_p5_5d_evidence_compatibility()
    """Run P5 OFFLINE→RUNTIME→PUBLICATION using the current P4 outputs."""
    from quant_pipeline.phase_05_underlying_forecasts import (
        ExecutionMode,
        ModuleAction,
        P5ExecutionContext,
        PhaseRunner,
        RunIdentity,
    )

    outputs = p4["outputs"]
    handoff = outputs["phase5_feature_handoff_manifest"]
    as_of = datetime.fromisoformat(handoff["as_of_time"].replace("Z", "+00:00"))
    generated = datetime.fromisoformat(handoff["created_at"].replace("Z", "+00:00")) + timedelta(minutes=1)
    research = adapt_p4_research_for_p5(outputs)
    outcome_bundle = build_p5_outcome_bundle_from_p4(outputs)
    feature_adapter = adapt_p4_feature_matrix_for_p5(p4, outcome_bundle, p5_source)
    outputs = p4["outputs"]
    handoff = outputs["phase5_feature_handoff_manifest"]
    base = {
        "phase5_feature_handoff_manifest": handoff,
        "model_consumer_view_manifest": outputs["model_consumer_view_manifest"],
        "model_consumer_view_bundle": outputs["model_consumer_view_bundle"],
        "p4_quality_gate_decision": outputs["p4_quality_gate_decision"],
        "p4_artifact_catalog": p4["catalog"],
    }
    from quant_pipeline.phase_05_underlying_forecasts.services.tabular import target_rows
    from quant_pipeline.phase_05_underlying_forecasts.services.temporal_evaluation import build_evaluation_plan
    preflight_targets = target_rows(outcome_bundle, training_cutoff=as_of)
    try:
        evaluation_plan, _receipt = build_evaluation_plan(preflight_targets, window_type="EXPANDING")
        fold_shape = [
            {
                "fold_id": fold["fold_id"],
                "timestamps": {part["name"]: len(part["timestamps"]) for part in fold["partitions"]},
            }
            for target_plan in evaluation_plan["target_plans"]
            for fold in target_plan["folds"]
        ]
        print(f"[p3-p9] P5 temporal plan rows={len(preflight_targets)} folds={fold_shape}", flush=True)
    except Exception as exc:
        import quant_pipeline.phase_05_underlying_forecasts.services.temporal_evaluation as temporal
        timestamps = sorted({row["prediction_timestamp"] for row in preflight_targets})
        test_size = max(3, int(round(len(timestamps) * 0.12)))
        development = timestamps[:-test_size]
        validation_size = max(3, min(10, len(development) // 12))
        embargo = temporal._embargo_sessions(timestamps, preflight_targets)
        print(
            "[p3-p9] P5 temporal preflight failed "
            f"count={len(preflight_targets)} timestamps={len({row['prediction_timestamp'] for row in preflight_targets})} "
            f"validation_size={validation_size} embargo={embargo} "
            f"first={preflight_targets[0]['prediction_timestamp'] if preflight_targets else None} "
            f"last={preflight_targets[-1]['prediction_timestamp'] if preflight_targets else None}: {exc}",
            flush=True,
        )
        raise
    offline_requests = (
        _p5_request("P5.S1.M01", ModuleAction.RUN, base),
        _p5_request("P5.S1.M02", ModuleAction.RUN),
        _p5_request("P5.S1.M03", ModuleAction.RUN, research),
        _p5_request("P5.S1.M04", ModuleAction.RUN),
        _p5_request("P5.S1.M05", ModuleAction.RUN),
        _p5_request("P5.S2.M01", ModuleAction.RUN, {"p5_offline_training_outcome_bundle": outcome_bundle}),
        _p5_request("P5.S2.M02", ModuleAction.RUN, {"representation_fold_plan": outputs["representation_fold_plan"]}),
        _p5_request("P5.S2.M03", ModuleAction.RUN),
        _p5_request("P5.S2.M04", ModuleAction.FIT, {"representation_quality_report": outputs["representation_quality_report"]}),
        _p5_request("P5.S2.M05", ModuleAction.VALIDATE, {"hypothesis_budget_report": outputs["hypothesis_budget_report"]}),
    )
    runtime_requests = tuple(
        [_p5_request(f"P5.S3.M0{index}", ModuleAction.PREDICT) for index in range(1, 6)]
        + [_p5_request(f"P5.S5.M0{index}", ModuleAction.PREDICT) for index in range(1, 6)]
        + [_p5_request("P5.S5.M06", ModuleAction.VALIDATE)]
        + [_p5_request(f"P5.S6.M0{index}", ModuleAction.PREDICT) for index in range(1, 4)]
        + [_p5_request("P5.S6.M04", ModuleAction.VALIDATE)]
        + [_p5_request(f"P5.S7.M0{index}", ModuleAction.PREDICT) for index in range(1, 4)]
        + [_p5_request("P5.S7.M04", ModuleAction.RUN), _p5_request("P5.S7.M05", ModuleAction.RUN)]
        + [_p5_request("P5.S8.M01", ModuleAction.RUN), _p5_request("P5.S8.M02", ModuleAction.VALIDATE)]
        + [_p5_request("P5.S8.M03", ModuleAction.RUN)]
        + [_p5_request("P5.S8.M04", ModuleAction.RUN), _p5_request("P5.S8.M05", ModuleAction.RUN)]
    )
    publication_requests = (
        _p5_request("P5.S9.M01", ModuleAction.PUBLISH),
        _p5_request("P5.S9.M02", ModuleAction.PUBLISH),
        _p5_request("P5.S9.M03", ModuleAction.PUBLISH),
        _p5_request("P5.S9.M04", ModuleAction.PUBLISH),
        _p5_request("P5.S9.M05", ModuleAction.PUBLISH),
    )

    with tempfile.TemporaryDirectory(prefix="p4-p5-live-") as directory:
        artifact_root = Path(directory) / "artifacts"

        def context(mode: Any) -> Any:
            return P5ExecutionContext(
                identity=RunIdentity(
                    run_id=handoff["run_id"],
                    cycle_id=handoff["cycle_id"],
                    as_of_time=as_of,
                    generated_at=generated,
                    seed=42,
                ),
                mode=mode,
                artifact_root=artifact_root,
            )

        offline_context = context(ExecutionMode.OFFLINE_TRAINING)
        offline = PhaseRunner(offline_context).run(offline_requests)
        failures = [
            {"module_id": item.module_id, "status": item.status.value, "errors": [str(error) for error in item.errors]}
            for item in offline.results if item.status.value in {"FAILED", "REJECTED"}
        ]
        if failures:
            raise RuntimeError(f"live P5 offline failed: {failures}")
        runtime_context = context(ExecutionMode.RUNTIME_INFERENCE)
        runtime = PhaseRunner(runtime_context).run(runtime_requests, initial_artifacts=offline.artifacts)
        failures = [
            {"module_id": item.module_id, "status": item.status.value, "errors": [str(error) for error in item.errors]}
            for item in runtime.results if item.status.value in {"FAILED", "REJECTED"}
        ]
        if failures:
            from collections import Counter
            for name in (
                "forecast_scoring_panel",
                "forecast_calibration_diagnostics",
                "calibrated_forecast_member_panel",
                "oof_validation_observation_panel",
            ):
                reference = runtime.artifacts.get(name)
                if reference is None:
                    continue
                value = runtime_context.artifact_store.read(reference)
                records = value.get("records", []) if isinstance(value, dict) else []
                if name == "oof_validation_observation_panel":
                    print(
                        f"[p3-p9] P5 runtime diagnostic {name} "
                        f"partitions={Counter(row.get('partition_id') for row in records)} "
                        f"rows={len(records)}",
                        flush=True,
                    )
                else:
                    statuses = Counter(str(row.get("status")) for row in records)
                    print(
                        f"[p3-p9] P5 runtime diagnostic {name} "
                        f"rows={len(records)} statuses={dict(statuses)}",
                        flush=True,
                    )
            raise RuntimeError(f"live P5 runtime failed: {failures}")
        publication_context = context(ExecutionMode.PUBLICATION)
        publication = PhaseRunner(publication_context).run(publication_requests, initial_artifacts=runtime.artifacts)
        failures = [
            {"module_id": item.module_id, "status": item.status.value, "errors": [str(error) for error in item.errors]}
            for item in publication.results if item.status.value in {"FAILED", "REJECTED"}
        ]
        if failures:
            raise RuntimeError(f"live P5 publication failed: {failures}")
        required = {"phase5_output_handoff_manifest", "phase6_strategy_scenario_manifest"}
        missing = sorted(required - set(publication.artifacts))
        if missing:
            raise RuntimeError(f"live P5 publication missing {missing}")
        return {
            name: publication_context.artifact_store.read(publication.artifacts[name])
            for name in sorted(required)
        } | {
            "p4_feature_adapter": feature_adapter,
            "p5_temporal_compatibility": p5_compatibility,
        }



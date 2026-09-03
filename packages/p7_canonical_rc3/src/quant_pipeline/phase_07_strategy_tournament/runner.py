from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from .empty_runtime import build_empty_runtime_outputs
from .finalization.runner import run_finalization_pipeline
from .foundation.runner import run_subphase_s1, run_subphase_s2
from .learning.runner_s5 import run_s5_pipeline
from .learning.runner_s6 import run_s6_pipeline
from .finalization.modules.P7_S8_M04_phase8_handoff_and_release_publisher import (
    run_module as run_release_publisher,
)
from .tournament.pipeline import run_tournament_pipeline
from .foundation.compatibility import adapt_native_p6_handoff, is_native_p6_manifest
from .handoffs import (
    prepare_finalization_inputs,
    prepare_learning_inputs,
    prepare_tournament_inputs,
)

JsonMapping = Mapping[str, Any]


def run_foundation_from_p6(
    *,
    phase6_manifest: JsonMapping,
    phase6_artifacts: list[dict[str, Any]],
    module_config: JsonMapping,
    eligibility_policy_registry: JsonMapping,
    comparison_group_policy: JsonMapping,
    metric_semantics_registry: JsonMapping,
    objective_family_registry: JsonMapping,
    ranking_feedback_report: JsonMapping | None = None,
    ranking_feedback_manifest: JsonMapping | None = None,
) -> dict[str, Any]:
    """Execute P7.S1-P7.S2 and preserve verified P6 source references."""
    manifest_payload = _json_mapping(phase6_manifest)
    artifact_payloads = [_json_mapping(item) for item in phase6_artifacts]
    foundation_config = dict(module_config)
    compatibility_report: dict[str, Any] | None = None
    if is_native_p6_manifest(manifest_payload):
        adaptation = adapt_native_p6_handoff(
            manifest_payload, artifact_payloads, foundation_config
        )
        manifest_payload = adaptation.manifest
        artifact_payloads = adaptation.artifacts
        foundation_config = adaptation.module_config
        compatibility_report = adaptation.compatibility_report
    boundary = run_subphase_s1(
        phase6_manifest=manifest_payload,
        phase6_artifacts=artifact_payloads,
        module_config=foundation_config,
        ranking_feedback_report=(dict(ranking_feedback_report) if ranking_feedback_report else None),
        ranking_feedback_manifest=(dict(ranking_feedback_manifest) if ranking_feedback_manifest else None),
    )
    comparison = run_subphase_s2(
        temporally_safe_candidate_bundle=boundary["outputs"]["temporally_safe_candidate_bundle"],
        ranking_feedback_context=boundary["outputs"]["ranking_feedback_context"],
        eligibility_policy_registry=dict(eligibility_policy_registry),
        comparison_group_policy=dict(comparison_group_policy),
        metric_semantics_registry=dict(metric_semantics_registry),
        objective_family_registry=dict(objective_family_registry),
        module_config=foundation_config,
    )
    outputs = {**boundary["outputs"], **comparison["outputs"]}
    if compatibility_report is not None:
        outputs["p6_native_compatibility_report"] = compatibility_report
    result = {
        "status": "PASS",
        "boundary": boundary,
        "comparison": comparison,
        "outputs": outputs,
    }
    if compatibility_report is not None:
        result["p6_native_compatibility_report"] = compatibility_report
    return result


def run_runtime_from_foundation(
    foundation_outputs: JsonMapping,
    *,
    tournament_config: JsonMapping,
    learning_config: JsonMapping,
    safety_config: JsonMapping,
    publication_config: JsonMapping,
) -> dict[str, Any]:
    """Execute P7.S3-P7.S8 from a validated foundation bundle."""
    eligible = foundation_outputs.get("eligible_strategy_candidate_panel")
    if _is_empty_artifact(eligible):
        empty_status, reason = _empty_runtime_disposition(foundation_outputs, eligible)
        if empty_status != "EMPTY_VALID":
            return _run_blocked_empty_runtime(
                foundation_outputs=foundation_outputs,
                status=empty_status,
                reason_code=reason,
            )
        return _run_empty_runtime(
            foundation_outputs=foundation_outputs,
            publication_config=publication_config,
        )
    return _run_standard_runtime(
        foundation_outputs=foundation_outputs,
        tournament_config=tournament_config,
        learning_config=learning_config,
        safety_config=safety_config,
        publication_config=publication_config,
    )


def _is_empty_artifact(value: Any) -> bool:
    return isinstance(value, Mapping) and int(value.get("record_count", 0)) == 0



def _empty_runtime_disposition(
    foundation_outputs: JsonMapping, eligible: Any,
) -> tuple[str, str | None]:
    capability = str(eligible.get("capability_status", "AVAILABLE")) if isinstance(eligible, Mapping) else "UNAVAILABLE"
    compatibility = foundation_outputs.get("p6_native_compatibility_report")
    p5_status = None
    if isinstance(compatibility, Mapping):
        raw = compatibility.get("p5_provenance_status")
        p5_status = None if raw is None else str(raw)
    received = foundation_outputs.get("temporally_safe_candidate_bundle")
    received_count = int(received.get("record_count", 0)) if isinstance(received, Mapping) else 0
    if capability in {"DEGRADED", "UNAVAILABLE"}:
        return "EMPTY_UPSTREAM_DEGRADED", "P7_EMPTY_ELIGIBLE_PANEL_NOT_HEALTHY"
    # If candidates reached P7 and were all rejected by P7's own eligibility
    # gates, the empty result is legitimate even when upstream provenance was
    # degraded.  The dangerous case is zero candidates reaching P7 at all.
    if received_count > 0:
        return "EMPTY_VALID", None
    if p5_status is not None and p5_status not in {"COMPLETE", "COMPLETE_CANONICAL"}:
        return "EMPTY_UPSTREAM_DEGRADED", "P7_EMPTY_P5_PROVENANCE_NOT_CANONICAL"
    return "EMPTY_VALID", None


def _run_blocked_empty_runtime(
    *, foundation_outputs: JsonMapping, status: str, reason_code: str | None,
) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "runtime_status": status,
        "reason_code": reason_code or "P7_EMPTY_UPSTREAM_DEGRADED",
        "tournament": {"status": "NOT_RUN"},
        "learning": {"status": "NOT_RUN"},
        "finalization": {"status": "NOT_RUN"},
        "release": {"status": "NOT_PUBLISHED", "outputs": {}},
        "handoffs": {},
        "outputs": {},
        "production_promotion_allowed": False,
    }

def _run_empty_runtime(
    *,
    foundation_outputs: JsonMapping,
    publication_config: JsonMapping,
) -> dict[str, Any]:
    outputs = build_empty_runtime_outputs(foundation_outputs, publication_config)
    release = _publish_release(
        outputs,
        foundation_outputs=foundation_outputs,
        publication_config=publication_config,
    )
    skipped = {"status": "SKIPPED_NO_ELIGIBLE_CANDIDATES"}
    return {
        "status": "PASS",
        "runtime_status": "EMPTY_VALID",
        "tournament": skipped,
        "learning": skipped,
        "finalization": {"status": "EMPTY_VALID", "s8": outputs},
        "release": release,
        "handoffs": {},
        "outputs": {**outputs, **release["outputs"]},
    }


def _run_standard_runtime(
    *,
    foundation_outputs: JsonMapping,
    tournament_config: JsonMapping,
    learning_config: JsonMapping,
    safety_config: JsonMapping,
    publication_config: JsonMapping,
) -> dict[str, Any]:
    tournament_inputs = prepare_tournament_inputs(foundation_outputs)
    tournament_result = run_tournament_pipeline(tournament_inputs, tournament_config)
    learning_inputs = prepare_learning_inputs(tournament_result["outputs"], foundation_outputs)
    supplied_models = learning_config.get("model_artifacts", {})
    if isinstance(supplied_models, Mapping):
        for name in (
            "ltr_model_artifact", "ltr_model_qualification_registry",
            "ltr_model_qualification_report", "governed_model_registry",
        ):
            if name in supplied_models:
                learning_inputs[name] = supplied_models[name]
    learning_result = run_s6_pipeline(
        learning_inputs,
        _bind_learning_context(learning_config, learning_inputs),
    )
    finalization_inputs = prepare_finalization_inputs(
        learning_result["outputs"],
        foundation_outputs,
        learning_inputs,
        created_at=str(safety_config["runtime"]["run_timestamp"]),
    )
    finalization_result = run_finalization_pipeline(
        finalization_inputs,
        safety_config,
        publication_config,
    )
    release = _publish_release(
        finalization_result["s8"],
        foundation_outputs=foundation_outputs,
        publication_config=publication_config,
    )
    return _assemble_standard_runtime_result(
        tournament_result=tournament_result,
        learning_result=learning_result,
        finalization_result=finalization_result,
        release=release,
        tournament_inputs=tournament_inputs,
        learning_inputs=learning_inputs,
        finalization_inputs=finalization_inputs,
    )



def _bind_learning_context(config: JsonMapping, learning_inputs: JsonMapping) -> dict[str, Any]:
    """Bind S6 execution to the tournament handoff produced in this exact run."""
    artifact = learning_inputs["interpretable_tournament_handoff_manifest"]
    effective = _json_mapping(config)
    effective["context"] = {
        "run_id": str(artifact["run_id"]),
        "cycle_id": str(artifact["cycle_id"]),
        "decision_time": str(artifact["decision_time"]),
        "available_at": str(artifact["available_at"]),
        "created_at": str(artifact["created_at"]),
        "pipeline_version": str(artifact["pipeline_version"]),
        "lineage_id": str(artifact["lineage_id"]),
    }
    return effective

def _assemble_standard_runtime_result(
    *,
    tournament_result: JsonMapping,
    learning_result: JsonMapping,
    finalization_result: JsonMapping,
    release: JsonMapping,
    tournament_inputs: JsonMapping,
    learning_inputs: JsonMapping,
    finalization_inputs: JsonMapping,
) -> dict[str, Any]:
    s7 = {name: value for name, value in finalization_result["s7"].items()
          if name != "module_execution_receipts"}
    outputs = {**s7, **finalization_result["s8"], **release["outputs"]}
    return {
        "status": "PASS",
        "tournament": tournament_result,
        "learning": learning_result,
        "finalization": finalization_result,
        "release": release,
        "handoffs": {
            "foundation_to_tournament": tournament_inputs["runtime_foundation_handoff_manifest"],
            "tournament_to_learning": learning_inputs["interpretable_tournament_handoff_manifest"],
            "learning_to_finalization": finalization_inputs["hybrid_scoring_handoff_manifest"],
        },
        "outputs": outputs,
    }


def run_phase7(
    *,
    phase6_manifest: JsonMapping,
    phase6_artifacts: list[dict[str, Any]],
    foundation_config: JsonMapping,
    eligibility_policy_registry: JsonMapping,
    comparison_group_policy: JsonMapping,
    metric_semantics_registry: JsonMapping,
    objective_family_registry: JsonMapping,
    tournament_config: JsonMapping,
    learning_config: JsonMapping,
    safety_config: JsonMapping,
    publication_config: JsonMapping,
    ranking_feedback_report: JsonMapping | None = None,
    ranking_feedback_manifest: JsonMapping | None = None,
) -> dict[str, Any]:
    """Execute the full sequential P7 runtime from P6 handoff to P8 publication."""
    foundation = run_foundation_from_p6(
        phase6_manifest=phase6_manifest,
        phase6_artifacts=phase6_artifacts,
        module_config=foundation_config,
        eligibility_policy_registry=eligibility_policy_registry,
        comparison_group_policy=comparison_group_policy,
        metric_semantics_registry=metric_semantics_registry,
        objective_family_registry=objective_family_registry,
        ranking_feedback_report=ranking_feedback_report,
        ranking_feedback_manifest=ranking_feedback_manifest,
    )
    runtime = run_runtime_from_foundation(
        foundation["outputs"],
        tournament_config=tournament_config,
        learning_config=learning_config,
        safety_config=safety_config,
        publication_config=publication_config,
    )
    return {"status": runtime["status"], "foundation": foundation, **runtime}



def run_phase7_from_p6_result(
    phase6_result: Mapping[str, Any],
    **phase7_arguments: Any,
) -> dict[str, Any]:
    """Execute P7 from a native P6 ``run_phase`` result without wire reconstruction."""
    outputs = phase6_result.get("outputs", phase6_result)
    if not isinstance(outputs, Mapping):
        raise TypeError("phase6_result must expose an outputs mapping")
    manifest = outputs.get("phase7_strategy_handoff_manifest")
    if manifest is None:
        raise KeyError("phase7_strategy_handoff_manifest")
    manifest_payload = _json_mapping(manifest)
    records = manifest_payload.get("records", [])
    references = records[0].get("artifact_references", []) if len(records) == 1 else []
    referenced_ids = {str(reference.get("artifact_id")) for reference in references}
    artifacts = []
    seen_artifact_ids: set[str] = set()
    for key, value in outputs.items():
        if key == "phase7_strategy_handoff_manifest":
            continue
        payload = _json_mapping(value)
        artifact_id = str(payload.get("artifact_id"))
        if artifact_id in referenced_ids and artifact_id not in seen_artifact_ids:
            artifacts.append(payload)
            seen_artifact_ids.add(artifact_id)
    return run_phase7(
        phase6_manifest=manifest_payload,
        phase6_artifacts=artifacts,
        **phase7_arguments,
    )


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise TypeError(f"expected mapping-compatible P6 artifact, got {type(value).__name__}")


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value

def run_offline_ltr(inputs: JsonMapping, config: JsonMapping) -> dict[str, Any]:
    """Execute the isolated P7.S5 offline learning path."""
    return run_s5_pipeline(inputs, config)


def _interpretable_runtime_config(config: JsonMapping) -> dict[str, Any]:
    """Deprecated compatibility alias; runtime policy is no longer overwritten."""
    return _json_mapping(config)


def _publish_release(
    publication_outputs: JsonMapping,
    *,
    foundation_outputs: JsonMapping,
    publication_config: JsonMapping,
) -> dict[str, Any]:
    group_panel = foundation_outputs["candidate_comparison_group_panel"]
    release_context = {
        "context": {
            "run_id": publication_config["runtime"]["run_id"],
            "cycle_id": group_panel["cycle_id"],
            "decision_time": group_panel["decision_time"],
            "created_at": publication_config["runtime"]["run_timestamp"],
            "available_at": group_panel["available_at"],
            "lineage_id": group_panel["lineage_id"],
        }
    }
    release_inputs = dict(publication_outputs)
    blocked = foundation_outputs.get("eligibility_blocked_candidate_panel")
    if isinstance(blocked, Mapping):
        release_inputs["eligibility_blocked_candidate_panel"] = blocked
    return run_release_publisher(release_inputs, release_context)

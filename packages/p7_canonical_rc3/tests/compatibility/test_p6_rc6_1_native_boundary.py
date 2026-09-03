from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from quant_pipeline.phase_07_strategy_tournament import (
    run_foundation_from_p6,
    run_phase7,
    run_phase7_from_p6_result,
    run_runtime_from_foundation,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "compatibility" / "p6_rc6_1_native_subset.json"


def _load(path: str):
    return json.loads((ROOT / path).read_text())


def _bundle():
    return json.loads(FIXTURE.read_text())


def _foundation_config(bundle):
    config = _load("fixtures/foundation/minimal_s1_input.json")["module_config"]
    config["context"]["pipeline_version"] = "2.3.0"
    config["context"]["created_at"] = bundle["phase7_strategy_handoff_manifest"]["created_at"]
    return config


def _foundation_arguments(bundle):
    return {
        "phase6_manifest": bundle["phase7_strategy_handoff_manifest"],
        "phase6_artifacts": [value for key, value in bundle.items() if key != "phase7_strategy_handoff_manifest"],
        "module_config": _foundation_config(bundle),
        "eligibility_policy_registry": _load("configs/foundation/eligibility_policy_registry.json"),
        "comparison_group_policy": _load("configs/foundation/comparison_group_policy.json"),
        "metric_semantics_registry": _load("configs/foundation/metric_semantics_registry.json"),
        "objective_family_registry": _load("configs/foundation/objective_family_registry.json"),
    }


def _runtime_arguments(bundle):
    manifest = bundle["phase7_strategy_handoff_manifest"]
    decision_time = manifest["records"][0]["decision_time"]
    created_at = manifest["created_at"]
    run_id = manifest["run_id"]
    cycle_id = manifest["cycle_id"]
    tournament = {
        "execution_time": created_at,
        "strict_hash_validation": True,
        "emit_debug_events": False,
        "numerical_tolerance": 1e-10,
    }
    learning = yaml.safe_load((ROOT / "configs/learning/s6_default_config.yaml").read_text())
    learning["context"].update({
        "run_id": run_id, "cycle_id": cycle_id, "decision_time": decision_time,
        "created_at": created_at, "lineage_id": "p6-native-compatibility",
    })
    safety = _load("fixtures/finalization/input/s7_config_fixture.json")
    publication = _load("fixtures/finalization/input/s8_config_fixture.json")
    for config in (safety, publication):
        config["runtime"].update({
            "run_id": run_id, "trace_id": "trace-p6-native", "run_timestamp": created_at,
        })
    return {
        "tournament_config": tournament,
        "learning_config": learning,
        "safety_config": safety,
        "publication_config": publication,
    }


def test_native_p6_boundary_is_validated_and_normalized_without_fake_evidence():
    bundle = _bundle()
    result = run_foundation_from_p6(**_foundation_arguments(bundle))
    outputs = result["outputs"]
    assert result["p6_native_compatibility_report"]["status"] == "PASS"
    assert result["p6_native_compatibility_report"]["clock_normalization_basis"] == "P6_VALIDATED_DECISION_ANCHOR"
    assert outputs["eligible_strategy_candidate_panel"]["record_count"] == 1
    assert outputs["eligibility_blocked_candidate_panel"]["record_count"] == 1
    eligible = outputs["eligible_strategy_candidate_panel"]["records"][0]
    blocked = outputs["eligibility_blocked_candidate_panel"]["records"][0]
    assert eligible["horizon"] == "30_calendar_days"
    assert eligible["risk"]["maximum_loss_proven"] is True
    assert eligible["cost_liquidity"]["liquidity_score_method"] == "ONE_MINUS_MAXIMUM_RELATIVE_SPREAD"
    assert blocked["cost_liquidity"]["liquidity_score"] is None


def test_native_p6_full_runtime_conserves_eligibility_blocked_candidates():
    bundle = _bundle()
    arguments = _foundation_arguments(bundle)
    result = run_phase7(
        phase6_manifest=arguments.pop("phase6_manifest"),
        phase6_artifacts=arguments.pop("phase6_artifacts"),
        foundation_config=arguments.pop("module_config"),
        **arguments,
        **_runtime_arguments(bundle),
    )
    receipt = result["outputs"]["p7_phase_release_receipt"]["records"][0]
    assert result["status"] == "PASS"
    assert receipt["candidate_count_received"] == 2
    assert receipt["candidate_count_eligibility_blocked"] == 1
    assert receipt["candidate_count_blocked"] == 1
    assert receipt["candidate_count_abstained"] == 1
    assert receipt["candidate_count_ranked"] == 0


def test_native_p6_hash_tampering_is_rejected_before_normalization():
    bundle = deepcopy(_bundle())
    bundle["strategy_risk_panel"]["records"][0]["maximum_loss"] = "999999"
    with pytest.raises(P7S1Error) as captured:
        run_foundation_from_p6(**_foundation_arguments(bundle))
    assert captured.value.reason_code == "P7_P6_MANIFEST_INVALID"


def test_quant_pipeline_remains_an_implicit_namespace_package():
    assert not (ROOT / "src" / "quant_pipeline" / "__init__.py").exists()


def test_empty_valid_runtime_closes_when_all_candidates_are_eligibility_blocked():
    bundle = _bundle()
    foundation = run_foundation_from_p6(**_foundation_arguments(bundle))
    outputs = deepcopy(foundation["outputs"])
    eligible = outputs["eligible_strategy_candidate_panel"]
    blocked = outputs["eligibility_blocked_candidate_panel"]
    migrated = dict(eligible["records"][0])
    migrated["reason_codes"] = ["P7_REQUIRED_METRIC_UNAVAILABLE"]
    blocked["records"].append(migrated)
    blocked["record_count"] = len(blocked["records"])
    eligible["records"] = []
    eligible["record_count"] = 0
    from quant_pipeline.phase_07_strategy_tournament.foundation.artifacts import verify_artifact_hash
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
    from quant_pipeline.phase_07_strategy_tournament.foundation.models import ArtifactEnvelope
    for artifact in (blocked, eligible):
        envelope = ArtifactEnvelope.model_validate(artifact)
        artifact["content_sha256"] = content_sha256(envelope.hash_payload())
        assert verify_artifact_hash(ArtifactEnvelope.model_validate(artifact))

    result = run_runtime_from_foundation(outputs, **_runtime_arguments(bundle))
    receipt = result["outputs"]["p7_phase_release_receipt"]["records"][0]
    assert result["status"] == "PASS"
    assert result["runtime_status"] == "EMPTY_VALID"
    assert receipt["candidate_count_received"] == 2
    assert receipt["candidate_count_eligibility_blocked"] == 2
    assert receipt["candidate_count_ranked"] == 0
    assert receipt["technical_closure"] is True


def test_public_p6_result_entrypoint_consumes_native_output_mapping():
    bundle = _bundle()
    arguments = _foundation_arguments(bundle)
    result = run_phase7_from_p6_result(
        {"outputs": bundle},
        foundation_config=arguments["module_config"],
        eligibility_policy_registry=arguments["eligibility_policy_registry"],
        comparison_group_policy=arguments["comparison_group_policy"],
        metric_semantics_registry=arguments["metric_semantics_registry"],
        objective_family_registry=arguments["objective_family_registry"],
        **_runtime_arguments(bundle),
    )
    receipt = result["outputs"]["p7_phase_release_receipt"]["records"][0]
    assert result["status"] == "PASS"
    assert receipt["candidate_count_received"] == 2
    assert result["foundation"]["p6_native_compatibility_report"]["status"] == "PASS"


def test_empty_degraded_candidate_surface_blocks_instead_of_claiming_empty_valid() -> None:
    bundle = _bundle()
    foundation = run_foundation_from_p6(**_foundation_arguments(bundle))
    outputs = deepcopy(foundation["outputs"])
    eligible = outputs["eligible_strategy_candidate_panel"]
    eligible["records"] = []
    eligible["record_count"] = 0
    eligible["capability_status"] = "DEGRADED"

    result = run_runtime_from_foundation(outputs, **_runtime_arguments(bundle))
    assert result["status"] == "BLOCKED"
    assert result["runtime_status"] == "EMPTY_UPSTREAM_DEGRADED"
    assert result["reason_code"] == "P7_EMPTY_ELIGIBLE_PANEL_NOT_HEALTHY"
    assert result["release"]["status"] == "NOT_PUBLISHED"


def test_empty_with_degraded_p5_provenance_blocks_even_when_panel_is_available() -> None:
    bundle = _bundle()
    foundation = run_foundation_from_p6(**_foundation_arguments(bundle))
    outputs = deepcopy(foundation["outputs"])
    eligible = outputs["eligible_strategy_candidate_panel"]
    eligible["records"] = []
    eligible["record_count"] = 0
    eligible["capability_status"] = "AVAILABLE"
    outputs["p6_native_compatibility_report"] = {
        **foundation["p6_native_compatibility_report"],
        "p5_provenance_status": "DEGRADED",
    }
    outputs["temporally_safe_candidate_bundle"]["records"] = []
    outputs["temporally_safe_candidate_bundle"]["record_count"] = 0

    result = run_runtime_from_foundation(outputs, **_runtime_arguments(bundle))
    assert result["status"] == "BLOCKED"
    assert result["runtime_status"] == "EMPTY_UPSTREAM_DEGRADED"
    assert result["reason_code"] == "P7_EMPTY_P5_PROVENANCE_NOT_CANONICAL"

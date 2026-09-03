from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256, normalize_json
from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.models import (
    ArtifactEnvelope,
    FeedbackRecord,
    ManifestArtifactRef,
    P6HandoffManifest,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import (
    run_module as run_m01,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M02_candidate_artifact_reconciliation_engine import (
    run_module as run_m02,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M03_temporal_integrity_and_forbidden_field_firewall import (
    run_module as run_m03,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M04_promoted_ranking_feedback_loader import (
    run_module as run_m04,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.s1_boundary.common import parse_aware_datetime, records_by_key
from tests.foundation.tests.test_m04_feedback import feedback_pair


def _rehash_artifact_and_ref(manifest, artifact):
    payload = {key: value for key, value in artifact.items() if key != "content_sha256"}
    artifact["content_sha256"] = content_sha256(payload)
    ref = next(row for row in manifest["artifacts"] if row["artifact_name"] == artifact["artifact_name"])
    ref["content_sha256"] = artifact["content_sha256"]
    ref["record_count"] = artifact["record_count"]
    ref["schema_version"] = artifact["schema_version"]
    ref["grain"] = artifact["grain"]


def _verified_index(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    return run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]


def _candidate_bundle(p6_fixture, module_config):
    return run_m02(
        {"verified_p6_artifact_index": _verified_index(p6_fixture, module_config)},
        module_config,
    )["outputs"]["validated_strategy_candidate_bundle"]


def _feedback_rehash(report, manifest):
    report["content_sha256"] = content_sha256({k: v for k, v in report.items() if k != "content_sha256"})
    manifest["report_content_sha256"] = report["content_sha256"]


class _TinyModel(BaseModel):
    value: int


def test_canonical_handles_models_aware_datetimes_and_rejects_bad_values():
    assert normalize_json(_TinyModel(value=3)) == {"value": 3}
    assert normalize_json(datetime(2026, 1, 1, tzinfo=timezone.utc)).endswith("Z")
    with pytest.raises(ValueError, match="naive"):
        normalize_json(datetime(2026, 1, 1))
    with pytest.raises(TypeError, match="unsupported"):
        normalize_json({1, 2})


def test_boundary_models_reject_duplicate_refs_count_mismatch_and_empty_evidence(p6_fixture):
    manifest, artifacts = deepcopy(p6_fixture)
    manifest["artifacts"].append(deepcopy(manifest["artifacts"][0]))
    with pytest.raises(ValueError, match="unique"):
        P6HandoffManifest.model_validate(manifest)

    bad = deepcopy(artifacts[0])
    bad["record_count"] += 1
    with pytest.raises(ValueError, match="record_count"):
        ArtifactEnvelope.model_validate(bad)

    record = {
        "feedback_id": "fb",
        "source_cycle_id": "c1",
        "source_cycle_sequence": 1,
        "target_cycle_id": "c2",
        "target_cycle_sequence": 2,
        "promotion_status": "PROMOTED",
        "scope": {},
        "evidence_ids": [],
        "valid_from_cycle_sequence": 2,
        "adjustments": [],
    }
    with pytest.raises(ValueError, match="evidence_ids"):
        FeedbackRecord.model_validate(record)


def test_common_helpers_skip_invalid_keys_and_parse_timestamp_variants():
    grouped = records_by_key([{"candidate_id": "a"}, {"candidate_id": ""}, {"candidate_id": 4}], "candidate_id")
    assert list(grouped) == ["a"]
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_aware_datetime(aware) is aware
    assert parse_aware_datetime("2026-01-01T00:00:00Z").tzinfo is not None
    with pytest.raises(TypeError):
        parse_aware_datetime(1)
    with pytest.raises(ValueError):
        parse_aware_datetime("2026-01-01T00:00:00")


def test_m01_rejects_invalid_config_and_duplicate_supplied_artifact(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    invalid_config = deepcopy(module_config)
    invalid_config["policy"] = {"unknown": True}
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, invalid_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"

    artifacts.append(deepcopy(artifacts[0]))
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"


def test_m01_rejects_missing_required_and_bad_required_flag(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    missing_name = "strategy_risk_panel"
    manifest["artifacts"] = [row for row in manifest["artifacts"] if row["artifact_name"] != missing_name]
    artifacts = [row for row in artifacts if row["artifact_name"] != missing_name]
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"

    manifest, artifacts = deepcopy(p6_fixture)
    next(row for row in manifest["artifacts"] if row["artifact_name"] == missing_name)["required"] = False
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"


def test_m01_rejects_versions_identity_reference_and_clock(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    manifest["contract_version"] = "3.0.0"
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_SCHEMA_INCOMPATIBLE"

    manifest, artifacts = deepcopy(p6_fixture)
    manifest["run_id"] = "another-run"
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_CLOCK_MISMATCH"

    manifest, artifacts = deepcopy(p6_fixture)
    manifest["artifacts"][0]["grain"] = "wrong_grain"
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"

    manifest, artifacts = deepcopy(p6_fixture)
    artifacts[0]["destination_phase"] = "P8"
    _rehash_artifact_and_ref(manifest, artifacts[0])
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_CLOCK_MISMATCH"


def test_m01_rejects_artifact_schema_major(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    artifacts[0]["schema_version"] = "3.0.0"
    _rehash_artifact_and_ref(manifest, artifacts[0])
    with pytest.raises(P7S1Error) as exc:
        run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)
    assert exc.value.code == "P7_P6_SCHEMA_INCOMPATIBLE"


def test_module_wrappers_reject_missing_or_wrong_input_shapes(module_config):
    with pytest.raises(TypeError):
        run_m01({}, module_config)
    with pytest.raises(TypeError):
        run_m02({}, module_config)
    with pytest.raises(TypeError):
        run_m03({}, module_config)
    with pytest.raises(TypeError):
        run_m04({"ranking_feedback_report": [], "ranking_feedback_manifest": None}, module_config)
    with pytest.raises(TypeError):
        run_m04({"ranking_feedback_report": None, "ranking_feedback_manifest": []}, module_config)


def test_m02_rejects_wrong_index_and_missing_artifact_list(p6_fixture, module_config):
    index = _verified_index(p6_fixture, module_config)
    wrong = deepcopy(index)
    wrong["artifact_name"] = "something_else"
    with pytest.raises(P7S1Error) as exc:
        run_m02({"verified_p6_artifact_index": wrong}, module_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"

    malformed = deepcopy(index)
    malformed["records"][0]["artifacts"] = "not-a-list"
    with pytest.raises(P7S1Error) as exc:
        run_m02({"verified_p6_artifact_index": malformed}, module_config)
    assert exc.value.code == "P7_P6_MANIFEST_INVALID"


def test_m02_rejects_missing_relation_keys_and_candidate_identity(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    candidate = next(row for row in artifacts if row["artifact_name"] == "strategy_candidate_panel")
    del candidate["records"][0]["candidate_id"]
    _rehash_artifact_and_ref(manifest, candidate)
    index = run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc.value.code == "P7_CANDIDATE_ID_MISMATCH"

    manifest, artifacts = deepcopy(p6_fixture)
    candidate = next(row for row in artifacts if row["artifact_name"] == "strategy_candidate_panel")
    del candidate["records"][0]["objective_family"]
    _rehash_artifact_and_ref(manifest, candidate)
    index = run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc.value.code == "P7_CANDIDATE_ID_MISMATCH"


def test_m02_rejects_child_identity_mismatch_and_duplicate_singleton(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    leg = next(row for row in artifacts if row["artifact_name"] == "strategy_leg_panel")
    leg["records"][0]["underlying_id"] = "OTHER"
    _rehash_artifact_and_ref(manifest, leg)
    index = run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc.value.code == "P7_CANDIDATE_ID_MISMATCH"

    manifest, artifacts = deepcopy(p6_fixture)
    risk = next(row for row in artifacts if row["artifact_name"] == "strategy_risk_panel")
    risk["records"].append(deepcopy(risk["records"][0]))
    risk["record_count"] = 2
    _rehash_artifact_and_ref(manifest, risk)
    index = run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc.value.code == "P7_CANDIDATE_MANDATORY_RECORD_MISSING"


def test_m02_accepts_optional_capability_and_non_mapping_capabilities(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    candidate = next(row for row in artifacts if row["artifact_name"] == "strategy_candidate_panel")
    candidate["records"][0]["capabilities"]["greeks"] = "AVAILABLE"
    _rehash_artifact_and_ref(manifest, candidate)
    from tests.foundation.tests.conftest import envelope
    greek = envelope("strategy_greek_panel", [{"candidate_id": "cand-1", "delta": 0.1}])
    artifacts.append(greek)
    manifest["artifacts"].append({
        "artifact_name": greek["artifact_name"],
        "artifact_id": greek["artifact_id"],
        "content_sha256": greek["content_sha256"],
        "schema_version": greek["schema_version"],
        "record_count": greek["record_count"],
        "required": False,
        "grain": greek["grain"],
    })
    index = run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)["outputs"]["verified_p6_artifact_index"]
    result = run_m02({"verified_p6_artifact_index": index}, module_config)
    assert result["outputs"]["validated_strategy_candidate_bundle"]["records"][0]["greeks"]

    manifest, artifacts = deepcopy(p6_fixture)
    candidate = next(row for row in artifacts if row["artifact_name"] == "strategy_candidate_panel")
    candidate["records"][0]["capabilities"] = "legacy-unknown"
    _rehash_artifact_and_ref(manifest, candidate)
    index = run_m01({"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts}, module_config)["outputs"]["verified_p6_artifact_index"]
    result = run_m02({"verified_p6_artifact_index": index}, module_config)
    assert result["outputs"]["validated_strategy_candidate_bundle"]["record_count"] == 1


def test_m03_rejects_invalid_config_wrong_bundle_clock_and_bad_timestamp(p6_fixture, module_config):
    bundle = _candidate_bundle(p6_fixture, module_config)
    invalid_config = deepcopy(module_config)
    invalid_config["policy"] = {"not_allowed": True}
    with pytest.raises(P7S1Error) as exc:
        run_m03({"validated_strategy_candidate_bundle": bundle}, invalid_config)
    assert exc.value.code == "P7_P6_SCHEMA_INCOMPATIBLE"

    wrong_name = deepcopy(bundle)
    wrong_name["artifact_name"] = "wrong"
    with pytest.raises(P7S1Error) as exc:
        run_m03({"validated_strategy_candidate_bundle": wrong_name}, module_config)
    assert exc.value.code == "P7_P6_SCHEMA_INCOMPATIBLE"

    wrong_clock = deepcopy(bundle)
    wrong_clock["decision_time"] = "2026-01-04T14:30:00Z"
    with pytest.raises(P7S1Error) as exc:
        run_m03({"validated_strategy_candidate_bundle": wrong_clock}, module_config)
    assert exc.value.code == "P7_P6_CLOCK_MISMATCH"

    bad_timestamp = deepcopy(bundle)
    bad_timestamp["records"][0]["candidate"]["quote_time"] = 5
    with pytest.raises(P7S1Error) as exc:
        run_m03({"validated_strategy_candidate_bundle": bad_timestamp}, module_config)
    assert exc.value.code == "P7_P6_SCHEMA_INCOMPATIBLE"


def test_m03_rejects_future_runtime_and_mismatched_nested_decision(p6_fixture, module_config):
    bundle = _candidate_bundle(p6_fixture, module_config)
    future = deepcopy(bundle)
    future["records"][0]["candidate"]["quote_time"] = "2026-01-05T15:30:00Z"
    with pytest.raises(P7S1Error) as exc:
        run_m03({"validated_strategy_candidate_bundle": future}, module_config)
    assert exc.value.code == "P7_FUTURE_INFORMATION"

    mismatch = deepcopy(bundle)
    mismatch["records"][0]["candidate"]["decision_time"] = "2026-01-05T13:30:00Z"
    with pytest.raises(P7S1Error) as exc:
        run_m03({"validated_strategy_candidate_bundle": mismatch}, module_config)
    assert exc.value.code == "P7_FUTURE_INFORMATION"


def test_m04_rejects_bad_config_partial_pair_and_invalid_record(module_config):
    bad_config = deepcopy(module_config)
    bad_config["policy"] = {"unknown": 1}
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": None, "ranking_feedback_manifest": None}, bad_config)
    assert exc.value.code == "P7_FEEDBACK_SCOPE_MISMATCH"

    report, manifest = feedback_pair(module_config)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": None}, module_config)
    assert exc.value.code == "P7_FEEDBACK_EVIDENCE_MISSING"

    report, manifest = feedback_pair(module_config)
    report["records"][0]["evidence_ids"] = []
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_EVIDENCE_MISSING"


def test_m04_rejects_duplicate_and_empty_valid_feedback(module_config):
    report, manifest = feedback_pair(module_config)
    report["records"].append(deepcopy(report["records"][0]))
    report["record_count"] = 2
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_DUPLICATE"

    report, manifest = feedback_pair(module_config)
    report["records"] = []
    report["record_count"] = 0
    _feedback_rehash(report, manifest)
    result = run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert result["outputs"]["ranking_feedback_context"]["capability_status"] == "UNAVAILABLE"
    assert result["outputs"]["feedback_validation_report"]["records"][0]["feedback_status"] == "EMPTY_VALID"


def test_m04_rejects_manifest_target_id_hash_and_expiry(module_config):
    report, manifest = feedback_pair(module_config)
    manifest["target_cycle_id"] = "other"
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_SCOPE_MISMATCH"

    report, manifest = feedback_pair(module_config)
    manifest["report_artifact_id"] = "other"
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_EVIDENCE_MISSING"

    report, manifest = feedback_pair(module_config)
    report["records"][0]["scope"]["note"] = "changed"
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_EVIDENCE_MISSING"

    report, manifest = feedback_pair(module_config)
    report["records"][0]["expires_at"] = "2026-01-01T00:00:00Z"
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_EXPIRED"


def test_m04_rejects_record_promotion_cycle_and_scope_mismatches(module_config):
    report, manifest = feedback_pair(module_config)
    report["records"][0]["promotion_status"] = "DRAFT"
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_NOT_PROMOTED"

    report, manifest = feedback_pair(module_config)
    report["records"][0]["source_cycle_sequence"] = 2
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_CURRENT_CYCLE"

    report, manifest = feedback_pair(module_config)
    report["records"][0]["source_cycle_id"] = "wrong"
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc.value.code == "P7_FEEDBACK_SCOPE_MISMATCH"

    report, manifest = feedback_pair(module_config)
    config = deepcopy(module_config)
    config["policy"] = {"allowed_scope": {"phase": "P7", "universe": "US"}}
    report["records"][0]["scope"]["universe"] = "BR"
    _feedback_rehash(report, manifest)
    with pytest.raises(P7S1Error) as exc:
        run_m04({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, config)
    assert exc.value.code == "P7_FEEDBACK_SCOPE_MISMATCH"


def test_structured_error_to_issue():
    from quant_pipeline.phase_07_strategy_tournament.foundation.reason_codes import ReasonCode

    error = P7S1Error(ReasonCode.P6_MANIFEST_INVALID, "bad manifest", "P7.S1.M01", {"x": 1})
    issue = error.to_issue()
    assert issue["code"] == "P7_P6_MANIFEST_INVALID"
    assert issue["severity"] == "FATAL"

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from quant_pipeline.phase_05_underlying_forecasts.boundary import canonical_sha256
from quant_pipeline.phase_05_underlying_forecasts.boundary.materialization import materialize_consumer_views
from quant_pipeline.phase_05_underlying_forecasts.boundary.validation import build_boundary_catalog
from quant_pipeline.phase_05_underlying_forecasts.errors import ContractError, DataQualityError
from quant_pipeline.phase_05_underlying_forecasts.services.horizon_policy import (
    allowed_horizon_groups,
    passport_target_scope,
    primary_horizon_group,
)
from quant_pipeline.phase_05_underlying_forecasts.services.p4_boundary import (
    normalize_conflicts,
    normalize_passports,
    plain_records,
)

from .fixtures import build_fixture


def _rehash(envelope: dict) -> None:
    envelope["record_count"] = len(envelope["records"])
    envelope["content_hash"] = canonical_sha256({
        "records": envelope["records"],
        "metadata": envelope["metadata"],
        "alias_of": envelope["alias_of"],
    })
    envelope["artifact_id"] = f"{envelope['artifact_name']}:{envelope['content_hash'][:16]}"


def _catalog(fixture: dict):
    return build_boundary_catalog(
        handoff=fixture["phase5_feature_handoff_manifest"],
        view_manifest=fixture["model_consumer_view_manifest"],
        view_bundle=fixture["model_consumer_view_bundle"],
        quality_gate=fixture["p4_quality_gate_decision"],
        artifact_catalog=fixture["p4_artifact_catalog"],
        expected_cycle_id="cycle-001",
        p5_as_of_time=fixture["as_of_time"],
        p5_generated_at=fixture["generated_at"],
    )


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda f: f["phase5_feature_handoff_manifest"].update({"artifact_name": "wrong"}), "expected P4 artifact"),
        (lambda f: f.update({"p4_artifact_catalog": {}}), "non-empty mapping"),
        (lambda f: f["p4_artifact_catalog"].update({"bad": []}), "must be an object"),
        (lambda f: f["p4_artifact_catalog"].update({"wrong-key": f["p4_artifact_catalog"]["feature_selection_report"]}), "key/name mismatch"),
        (lambda f: f["phase5_feature_handoff_manifest"].update({"cycle_id": "other"}), "share run/cycle/as_of"),
        (lambda f: f["phase5_feature_handoff_manifest"]["metadata"].update({"destination_phase": "phase_06"}), "destination_phase"),
    ],
)
def test_boundary_rejects_invalid_topology(mutation, match):
    fixture = build_fixture(days=20)
    mutation(fixture)
    for name in ("phase5_feature_handoff_manifest", "model_consumer_view_manifest", "model_consumer_view_bundle", "p4_quality_gate_decision"):
        _rehash(fixture[name])
    with pytest.raises(ContractError, match=match):
        _catalog(fixture)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("execution_status", "UNKNOWN", "unsupported execution_status"),
        ("materialized", True, "reference-only"),
        ("grain", ["entity_id"], "incompatible grain"),
        ("artifact_ids", "bad", "must be an array"),
    ],
)
def test_view_declaration_fail_closed(field, value, match):
    fixture = build_fixture(days=20)
    fixture["model_consumer_view_manifest"]["records"][0][field] = value
    _rehash(fixture["model_consumer_view_manifest"])
    fixture["phase5_feature_handoff_manifest"]["metadata"]["consumer_view_manifest_id"] = fixture["model_consumer_view_manifest"]["artifact_id"]
    fixture["phase5_feature_handoff_manifest"]["metadata"]["consumer_view_manifest_hash"] = fixture["model_consumer_view_manifest"]["content_hash"]
    _rehash(fixture["phase5_feature_handoff_manifest"])
    with pytest.raises(ContractError, match=match):
        _catalog(fixture)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda r: r.update({"payload_copied": True}), "copied payloads"),
        (lambda r: r.update({"execution_status": "UNAVAILABLE_UPSTREAM"}), "status differs"),
        (lambda r: r.update({"artifact_references": "bad"}), "must be an array"),
        (lambda r: r.update({"artifact_references": ["bad"]}), "reference must be an object"),
        (lambda r: r["artifact_references"][0].update({"artifact_name": "missing"}), "references absent artifact"),
        (lambda r: r["artifact_references"][0].update({"record_count": -1}), "record_count mismatch"),
    ],
)
def test_view_reference_fail_closed(mutation, match):
    fixture = build_fixture(days=20)
    mutation(fixture["model_consumer_view_bundle"]["records"][0])
    _rehash(fixture["model_consumer_view_bundle"])
    with pytest.raises(ContractError, match=match):
        _catalog(fixture)


def test_blocking_and_degraded_gate_paths():
    blocked = build_fixture(days=20)
    blocked["p4_quality_gate_decision"]["records"][0]["decision"] = "BLOCK_HANDOFF"
    blocked["p4_quality_gate_decision"]["metadata"]["final_decision"] = "BLOCK_HANDOFF"
    blocked["phase5_feature_handoff_manifest"]["metadata"]["gate_decision"] = "BLOCK_HANDOFF"
    _rehash(blocked["p4_quality_gate_decision"]); _rehash(blocked["phase5_feature_handoff_manifest"])
    with pytest.raises(ContractError, match="handoff is blocked"):
        _catalog(blocked)

    degraded = build_fixture(days=20)
    degraded["p4_quality_gate_decision"]["records"].append({
        "gate_scope": "FAMILY", "scope_id": "F07", "decision": "PASS",
        "block_count": 0, "warn_count": 1, "reason_codes": ["WARN"],
    })
    degraded["model_consumer_view_manifest"]["metadata"]["blocked_families"] = []
    _rehash(degraded["p4_quality_gate_decision"]); _rehash(degraded["model_consumer_view_manifest"])
    degraded["phase5_feature_handoff_manifest"]["metadata"]["consumer_view_manifest_id"] = degraded["model_consumer_view_manifest"]["artifact_id"]
    degraded["phase5_feature_handoff_manifest"]["metadata"]["consumer_view_manifest_hash"] = degraded["model_consumer_view_manifest"]["content_hash"]
    _rehash(degraded["phase5_feature_handoff_manifest"])
    assert _catalog(degraded).gate_state.degraded_families == ("F07",)


def test_materialization_degraded_latent_and_bad_inputs():
    fixture = build_fixture(days=20)
    catalog = _catalog(fixture)
    views, compatibility = materialize_consumer_views(catalog)
    latent = next(view for view in views if view["view_id"] == "LATENT_FAMILY")
    assert latent["quality_state"] == "PASS_WITH_LIMITATIONS"
    assert any("PCA-only" in item for item in latent["limitations"])
    assert all(row["authorized"] for row in compatibility)

    broken = build_fixture(days=20)
    selected = broken["p4_artifact_catalog"]["underlying_feature_matrix_selected"]
    selected["metadata"]["feature_catalog"] = []
    _rehash(selected)
    for row in broken["phase5_feature_handoff_manifest"]["records"]:
        if row["artifact_name"] == "underlying_feature_matrix_selected":
            row["artifact_id"] = selected["artifact_id"]; row["content_hash"] = selected["content_hash"]
    for view in broken["model_consumer_view_bundle"]["records"]:
        for ref in view["artifact_references"]:
            if ref["artifact_name"] == "underlying_feature_matrix_selected":
                ref.update({"artifact_id": selected["artifact_id"], "content_hash": selected["content_hash"]})
    for view in broken["model_consumer_view_manifest"]["records"]:
        view["artifact_ids"] = [selected["artifact_id"] if aid.startswith("underlying_feature_matrix_selected:") else aid for aid in view["artifact_ids"]]
    _rehash(broken["model_consumer_view_manifest"]); _rehash(broken["model_consumer_view_bundle"])
    broken["phase5_feature_handoff_manifest"]["metadata"]["consumer_view_manifest_id"] = broken["model_consumer_view_manifest"]["artifact_id"]
    broken["phase5_feature_handoff_manifest"]["metadata"]["consumer_view_manifest_hash"] = broken["model_consumer_view_manifest"]["content_hash"]
    _rehash(broken["phase5_feature_handoff_manifest"])
    with pytest.raises(DataQualityError, match="feature_catalog"):
        materialize_consumer_views(_catalog(broken))


def test_policy_and_research_boundary_error_paths():
    for function in (primary_horizon_group, allowed_horizon_groups):
        with pytest.raises(ContractError):
            function("2D")
    with pytest.raises(ContractError):
        passport_target_scope("UNKNOWN")
    with pytest.raises(DataQualityError, match="must contain records"):
        plain_records([], "bad")
    with pytest.raises(DataQualityError, match="records must be objects"):
        plain_records({"records": [1]}, "bad")
    with pytest.raises(DataQualityError, match="unique IDs"):
        normalize_passports(
            {"records": [{"hypothesis_id": "H", "family_id": "F", "primary_horizon": "SHORT", "status": "APPROVED"}]},
            {"records": [{"hypothesis_id": "H", "limit": 1, "approved_count": 2}]},
            {"records": []},
        )
    with pytest.raises(DataQualityError, match="between zero and one"):
        normalize_conflicts({"records": [{
            "entity_id": "AAA", "decision_time": "2025-01-01T00:00:00Z", "group_id": "G",
            "horizon_group": "SHORT", "conflict_score": 2.0,
        }]})
    with pytest.raises(DataQualityError, match="nonnegative"):
        normalize_conflicts({"records": [{
            "entity_id": "AAA", "decision_time": "2025-01-01T00:00:00Z", "group_id": "G",
            "horizon_group": "SHORT", "dispersion_score": -1.0,
        }]})


def test_boundary_rejects_foreign_run_when_runtime_identity_is_supplied():
    fixture = build_fixture(days=20)
    with pytest.raises(ContractError, match="run_id differs"):
        build_boundary_catalog(
            handoff=fixture["phase5_feature_handoff_manifest"],
            view_manifest=fixture["model_consumer_view_manifest"],
            view_bundle=fixture["model_consumer_view_bundle"],
            quality_gate=fixture["p4_quality_gate_decision"],
            artifact_catalog=fixture["p4_artifact_catalog"],
            expected_cycle_id="cycle-001",
            p5_as_of_time=fixture["as_of_time"],
            p5_generated_at=fixture["generated_at"],
            expected_run_id="foreign-run",
        )

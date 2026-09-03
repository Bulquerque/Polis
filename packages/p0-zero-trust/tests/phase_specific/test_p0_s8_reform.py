from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S8_M01_version_compatibility_checker import run_module as run_m01
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S8_M02_release_manifest_builder import run_module as run_m02
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S8_M03_release_gate_decision_engine import run_module as run_m03

LINEAGE = "sha256:" + "a" * 64


def item(name, *, status="PASS", version="V14.1-RC4.1", release_blocking=False, **extra):
    return {
        "artifact_id": f"{name}-artifact",
        "pipeline_version": version,
        "lineage_id": LINEAGE,
        "status": status,
        "release_blocking": release_blocking,
        **extra,
    }


def registries():
    phases = item("phase-registry", phases=[{"phase_id": "P0", "phase_name": "Zero Trust"}])
    contracts = item(
        "contract-registry",
        contracts=[{"module_id": "P0.S8.M01", "inputs": ["a"], "outputs": ["b"]}],
    )
    schemas = item(
        "schema-registry",
        schemas=[{
            "schema_id": "demo.v1",
            "artifact_name": "demo",
            "required_fields": ["id"],
            "properties": {"id": {"type": "string"}},
        }],
    )
    return phases, contracts, schemas


def compatibility_inputs(previous=None):
    phase, contract, schema = registries()
    return {
        "validated_phase_registry": phase,
        "contract_registry": contract,
        "schema_registry": schema,
        "release_manifest_previous": previous or item("previous", version="V14.1-RC4.0"),
    }


def evidence_inputs(*, snapshot=None):
    compatibility = run_m01(compatibility_inputs(), {"created_at": "2026-07-22T00:00:00Z"})["outputs"]["version_compatibility_report"]
    extra = {"source_snapshot_digest": snapshot} if snapshot else {}
    return {
        "pipeline_health_report": item("health", **extra),
        "version_compatibility_report": compatibility | extra,
        "zero_trust_evidence_package": item(
            "evidence",
            evidence_complete=True,
            release_evidence_traceable=True,
            all_evidence_passing=True,
            **extra,
        ),
    }


def gate_inputs(*, phase_statuses=None, manifest_config=None):
    manifest = run_m02(
        evidence_inputs(),
        {"created_at": "2026-07-22T00:00:00Z", **(manifest_config or {})},
    )["outputs"]["release_manifest"]
    statuses = phase_statuses or {f"P{i}": "PASS" for i in range(10)}
    phases = [{"phase_id": f"P{i}", "status": statuses.get(f"P{i}", "PASS"), "findings": []} for i in range(10)]
    return {
        "release_manifest": manifest,
        "global_test_report": item("tests", critical_failed_tests=0, phases=phases),
        "forbidden_connection_report": item("connections", violation_count=0),
        "code_quality_report": item("quality"),
        "hash_integrity_report": item("hashes", hash_mismatch_count=0),
        "agent_package_validation_report": item(
            "agent-package",
            package_structure_valid=True,
            no_cache_in_zip=True,
            blocking=False,
        ),
    }


def test_m01_rejects_version_downgrade():
    previous = item("previous", version="V14.1-RC4.9")
    report = run_m01(compatibility_inputs(previous))["outputs"]["version_compatibility_report"]
    assert report["status"] == "FAIL"
    assert any(finding["code"] == "version_downgrade" for finding in report["findings"])


def test_m01_detects_breaking_schema_required_field_addition():
    first = run_m01(compatibility_inputs())["outputs"]["version_compatibility_report"]
    previous = item(
        "previous",
        version="V14.1-RC4.0",
        compatibility_baseline=first["current_inventory"],
    )
    inputs = compatibility_inputs(previous)
    inputs["schema_registry"]["schemas"][0]["required_fields"].append("new_required")
    inputs["schema_registry"]["schemas"][0]["properties"]["new_required"] = {"type": "string"}
    report = run_m01(inputs)["outputs"]["version_compatibility_report"]
    assert report["status"] == "FAIL"
    assert report["schema_version_compatible"] is False
    assert any(finding["code"] == "SCHEMA_REQUIRED_FIELD_ADDED" for finding in report["findings"])


def test_m01_classifies_optional_schema_extension_as_warning():
    first = run_m01(compatibility_inputs())["outputs"]["version_compatibility_report"]
    previous = item("previous", version="V14.1-RC4.0", compatibility_baseline=first["current_inventory"])
    inputs = compatibility_inputs(previous)
    inputs["schema_registry"]["schemas"][0]["properties"]["optional_new"] = {"type": "string"}
    report = run_m01(inputs)["outputs"]["version_compatibility_report"]
    assert report["status"] == "PASS"
    assert any(warning["code"] == "SCHEMA_COMPATIBLE_EXTENSION" for warning in report["warnings"])


def test_m02_release_fingerprint_is_deterministic_across_created_at():
    first = run_m02(evidence_inputs(), {"created_at": "2026-07-22T00:00:00Z"})["outputs"]["release_manifest"]
    second = run_m02(evidence_inputs(), {"created_at": "2026-07-23T00:00:00Z"})["outputs"]["release_manifest"]
    assert first["release_fingerprint"] == second["release_fingerprint"]


def test_m02_detects_mixed_source_snapshots():
    inputs = evidence_inputs()
    inputs["pipeline_health_report"]["source_snapshot_digest"] = "sha256:" + "1" * 64
    inputs["zero_trust_evidence_package"]["source_snapshot_digest"] = "sha256:" + "2" * 64
    manifest = run_m02(inputs)["outputs"]["release_manifest"]
    assert manifest["status"] == "BLOCKED"
    assert manifest["snapshot_coherence_status"] == "MISMATCH"
    assert "source_snapshot_coherence" in manifest["blocking_sources"]


def test_m02_records_explicit_qualification_bindings():
    bindings = [{"phase_id": "P0", "run_id": "p0-closure-abc", "status": "PHASE_QUALIFIED"}]
    manifest = run_m02(
        evidence_inputs(snapshot="sha256:" + "3" * 64),
        {"qualification_bindings": bindings, "release_scope": "P0_ONLY"},
    )["outputs"]["release_manifest"]
    assert manifest["qualification_status"] == "BOUND"
    assert manifest["qualification_bindings"] == bindings
    assert manifest["release_scope"] == "P0_ONLY"
    assert manifest["snapshot_coherence_status"] == "BOUND"


def test_m03_does_not_mark_every_phase_blocked_for_global_material_failure():
    inputs = gate_inputs()
    inputs["hash_integrity_report"]["hash_mismatch_count"] = 1
    report = run_m03(inputs)["outputs"]["release_gate_report"]
    assert report["decision"] == "FAIL"
    assert "HASH_MISMATCH" in report["reason_codes"]
    assert all(phase["readiness"] == "READY" for phase in report["phase_readiness"])


def test_m03_ignores_incomplete_downstream_phase_in_p0_scope():
    statuses = {f"P{i}": "PASS" for i in range(10)}
    statuses["P7"] = "NOT_STARTED"
    report = run_m03(gate_inputs(phase_statuses=statuses, manifest_config={"release_scope": "P0_TECHNICAL_CLOSURE"}))["outputs"]["release_gate_report"]
    p7 = next(phase for phase in report["phase_readiness"] if phase["phase_id"] == "P7")
    assert p7["readiness"] == "NOT_READY"
    assert "PHASE_NOT_READY" not in report["reason_codes"]
    assert report["status"] == "PASS"


def test_m03_p0_only_scope_ignores_unstarted_other_phases_for_readiness():
    statuses = {f"P{i}": "NOT_STARTED" for i in range(10)}
    statuses["P0"] = "PASS"
    report = run_m03(
        gate_inputs(phase_statuses=statuses, manifest_config={"release_scope": "P0_TECHNICAL_CLOSURE"})
    )["outputs"]["release_gate_report"]
    assert report["decision"] == "PASS"
    assert report["readiness_state"] == "READY"


def test_m03_keeps_production_policy_separate_from_technical_approval():
    report = run_m03(gate_inputs(), {"production_promotion_allowed": False})["outputs"]["release_gate_report"]
    assert report["decision"] == "PASS"
    assert report["production_promotion_allowed"] is False
    assert report["promotion_blocked"] is False


def test_m03_reports_qualification_binding_state():
    bindings = [{"phase_id": "P0", "run_id": "closure-1", "status": "PHASE_QUALIFIED"}]
    report = run_m03(
        gate_inputs(manifest_config={"qualification_bindings": bindings, "release_scope": "P0_ONLY"})
    )["outputs"]["release_gate_report"]
    assert report["qualification_evaluated"] is True
    assert report["validation_evidence_state"] == "QUALIFICATION_BOUND"

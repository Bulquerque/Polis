from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S8_M01_version_compatibility_checker import run_module as run_m01
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S8_M02_release_manifest_builder import run_module as run_m02
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S8_M03_release_gate_decision_engine import run_module as run_m03

LINEAGE = "sha256:" + "a" * 64


def item(name, *, status="PASS", release_blocking=False, version="V14.1-RC4.1", **extra):
    return {"artifact_id": f"{name}-artifact", "pipeline_version": version, "lineage_id": LINEAGE, "status": status, "release_blocking": release_blocking, **extra}


def m01_inputs():
    return {
        "validated_phase_registry": item("phase-registry"),
        "contract_registry": item("contract-registry"),
        "schema_registry": item("schema-registry"),
        "release_manifest_previous": item("previous-release", version="V14.1-RC4.0"),
    }


def m02_inputs():
    compatibility = run_m01(m01_inputs(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["version_compatibility_report"]
    return {"pipeline_health_report": item("health"), "version_compatibility_report": compatibility, "zero_trust_evidence_package": item("evidence", evidence_count=4, evidence_complete=True, release_evidence_traceable=True, all_evidence_passing=True)}


def m03_inputs():
    manifest = run_m02(m02_inputs(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["release_manifest"]
    phases = [{"phase_id": f"P{index}", "status": "PASS", "findings": []} for index in range(10)]
    return {
        "release_manifest": manifest,
        "global_test_report": item("tests", critical_failed_tests=0, phases=phases),
        "forbidden_connection_report": item("connections", violation_count=0),
        "code_quality_report": item("quality"),
        "hash_integrity_report": item("hashes", hash_mismatch_count=0),
        "agent_package_validation_report": item("agent-package", package_structure_valid=True, no_cache_in_zip=True, blocking=False),
    }


def test_m01_accepts_material_compatible_release_line():
    report = run_m01(m01_inputs(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["version_compatibility_report"]
    assert report["status"] == "PASS" and report["source_count"] == 4 and report["finding_count"] == 0


def test_m01_blocks_failed_registry():
    inputs = m01_inputs(); inputs["schema_registry"] = item("schemas", status="FAIL", release_blocking=True)
    report = run_m01(inputs)["outputs"]["version_compatibility_report"]
    assert report["status"] == "FAIL" and report["release_blocking"]


def test_m01_blocks_incompatible_previous_major_minor():
    inputs = m01_inputs(); inputs["release_manifest_previous"] = item("old", version="V13.9-RC9.9")
    report = run_m01(inputs)["outputs"]["version_compatibility_report"]
    assert any(f["code"] == "incompatible_release_line" for f in report["findings"])


def test_m01_propagates_previous_manifest_failure():
    inputs = m01_inputs(); inputs["release_manifest_previous"].update(status="BLOCKED", release_blocking=True)
    assert run_m01(inputs)["outputs"]["version_compatibility_report"]["status"] == "FAIL"


def test_m02_builds_traceable_material_manifest():
    manifest = run_m02(m02_inputs(), {"release_id": "candidate-1"})["outputs"]["release_manifest"]
    assert manifest["status"] == "PASS" and manifest["artifact_count"] == 3
    assert manifest["release_manifest_traceable"] and all(x["source_sha256"] for x in manifest["artifacts"])


def test_m02_propagates_upstream_blocking():
    inputs = m02_inputs(); inputs["pipeline_health_report"] = item("health", status="FAIL", release_blocking=True)
    manifest = run_m02(inputs)["outputs"]["release_manifest"]
    assert manifest["status"] == "BLOCKED" and manifest["blocking_sources"] == ["pipeline_health_report"]


def test_m03_approves_only_all_green_material_reports():
    report = run_m03(m03_inputs(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["release_gate_report"]
    assert report["decision"] == "PASS" and report["evaluated_artifact_count"] == 6 and not report["release_blocking"]


@pytest.mark.parametrize(
    ("name", "changes"),
    [
        ("global_test_report", {"critical_failed_tests": 1}),
        ("forbidden_connection_report", {"violation_count": 1}),
        ("hash_integrity_report", {"hash_mismatch_count": 1}),
        ("agent_package_validation_report", {"package_structure_valid": False}),
        ("code_quality_report", {"status": "FAIL", "release_blocking": True}),
    ],
)
def test_m03_blocks_each_critical_upstream_failure(name, changes):
    inputs = m03_inputs(); inputs[name].update(changes)
    report = run_m03(inputs)["outputs"]["release_gate_report"]
    assert report["decision"] == "FAIL" and report["release_blocking"]
    assert any(reason["artifact"] == name for reason in report["blocking_reasons"])


def test_rejects_weak_identity_and_forbidden_data():
    inputs = m03_inputs(); inputs["code_quality_report"].pop("lineage_id")
    with pytest.raises(ContractValidationError): run_m03(inputs)
    inputs = m01_inputs(); inputs["contract_registry"]["nested"] = {"trade_decision": "BUY"}
    with pytest.raises(ContractValidationError): run_m01(inputs)


def test_gate_rejects_non_material_reports():
    inputs = m03_inputs(); inputs["hash_integrity_report"].pop("hash_mismatch_count")
    with pytest.raises(ContractValidationError): run_m03(inputs)

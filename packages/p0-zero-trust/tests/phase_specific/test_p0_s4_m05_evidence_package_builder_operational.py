import pytest

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M05_evidence_package_builder import run_module


NAMES = ["global_test_report", "hash_integrity_report", "lineage_integrity_report", "code_quality_report"]


def payload(status="PASS"):
    return {
        name: {
            "artifact_id": name,
            "lineage_id": "sha256:" + str(i) * 64,
            "status": status,
            "release_blocking": status != "PASS",
        }
        for i, name in enumerate(NAMES)
    }


def test_builds_traceable_package_only_from_passing_evidence():
    package = run_module(payload(), {"created_at": "2026-01-01T00:00:00Z"})["outputs"]["zero_trust_evidence_package"]
    assert package["status"] == "PASS"
    assert package["evidence_complete"]
    assert package["release_evidence_traceable"]
    assert package["required_evidence_count"] == 4


def test_failed_evidence_is_fail_with_release_blocking():
    value = payload()
    value["code_quality_report"]["status"] = "FAIL"
    package = run_module(value)["outputs"]["zero_trust_evidence_package"]
    assert package["status"] == "FAIL"
    assert package["release_blocking"]


def test_supports_extended_zero_trust_evidence_without_changing_required_contract():
    value = payload()
    value["immutability_report"] = {
        "artifact_id": "immutability",
        "lineage_id": "sha256:" + "f" * 64,
        "status": "PASS",
        "release_blocking": False,
    }
    package = run_module(value)["outputs"]["zero_trust_evidence_package"]
    assert package["evidence_count"] == 5
    assert any(item["evidence_type"] == "immutability_report" for item in package["evidence"])


@pytest.mark.parametrize("mutation", ["missing", "lineage", "artifact", "forbidden"])
def test_rejects_evidence_gaps(mutation):
    value = payload()
    if mutation == "missing":
        value.pop("code_quality_report")
    elif mutation == "lineage":
        value["global_test_report"]["lineage_id"] = "fake"
    elif mutation == "artifact":
        value["global_test_report"].pop("artifact_id")
    else:
        value["target"] = "leak"
    with pytest.raises(ContractValidationError):
        run_module(value)

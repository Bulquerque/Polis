from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
GLOBAL_ROOT = (
    WORKSPACE_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
)
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import (
    ContractValidationError,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M03_module_registry_loader import (
    run_module as build_validated_module_registry,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S2_M01_contract_registry_builder import (
    run_module as build_contract_registry,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S3_M02_lineage_integrity_checker import (
    run_module,
)


CREATED_AT = "2026-07-19T00:00:00Z"


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _real_inputs():
    registry = _yaml(GLOBAL_ROOT / "source_of_truth" / "registries" / "module_registry.yaml")
    for entry in registry["modules"]:
        contract_path = WORKSPACE_ROOT / entry["contract_path"]
        entry["contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    phase_registry = _yaml(GLOBAL_ROOT / "source_of_truth" / "registries" / "phase_registry.yaml")
    subphase_registry = _yaml(
        GLOBAL_ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"
    )
    validated = build_validated_module_registry(
        {
            "validated_phase_registry": phase_registry,
            "validated_subphase_registry": subphase_registry,
            "module_registry_yaml": registry,
        },
        {"created_at": CREATED_AT},
    )["outputs"]["validated_module_registry"]
    contracts = build_contract_registry(
        {
            "contracts_all_phases": registry,
            "global_contracts": str(GLOBAL_ROOT / "contracts"),
        },
        {"created_at": CREATED_AT},
    )["outputs"]["contract_registry"]
    manifest = {
        "artifacts": [
            {"path": entry["contract_path"], "sha256": entry["contract_sha256"]}
            for entry in registry["modules"]
        ]
    }
    return {
        "artifact_manifest_all_phases": manifest,
        "validated_module_registry": validated,
        "contract_registry": contracts,
    }


@pytest.fixture(scope="module")
def real_inputs():
    return _real_inputs()


def _rehash_contract_registry(artifact):
    digest = hashlib.sha256(
        json.dumps(
            {
                "contracts": artifact["contracts"],
                "global_contracts": artifact["global_contracts"],
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    artifact["lineage_id"] = f"sha256:{digest}"
    artifact["artifact_id"] = f"contract-registry-{digest[:12]}"


def test_real_canonical_contract_lineage_is_exhaustively_checked(real_inputs):
    result = run_module(real_inputs, {"created_at": CREATED_AT})
    report = result["outputs"]["lineage_integrity_report"]

    assert result["module_id"] == "P0.S3.M02"
    assert report["module_count"] == real_inputs["contract_registry"]["contract_count"]
    assert report["artifact_count"] == len(report["artifact_checks"])
    assert len(report["checks"]) == report["module_count"]
    assert {item["module_id"] for item in report["checks"]} == {
        item["module_id"] for item in real_inputs["validated_module_registry"]["modules"]
    }
    assert report["contract_hashes_match"] is True
    assert report["manifest_provenance_complete"] is True
    assert report["failed_module_count"] + report["passed_module_count"] == report["module_count"]
    assert report["failed_artifact_count"] + report["passed_artifact_count"] == report["artifact_count"]
    assert report["release_blocking"] == (
        report["failed_module_count"] > 0 or report["failed_artifact_count"] > 0
    )
    assert report["promotion_blocked"] is True


def test_manifest_hash_disagreement_is_a_structured_release_blocker(real_inputs):
    inputs = deepcopy(real_inputs)
    inputs["artifact_manifest_all_phases"]["artifacts"][0]["sha256"] = "0" * 64
    report = run_module(inputs, {"created_at": CREATED_AT})["outputs"][
        "lineage_integrity_report"
    ]
    first_id = inputs["validated_module_registry"]["modules"][0]["module_id"]
    check = next(item for item in report["checks"] if item["module_id"] == first_id)
    assert "MANIFEST_HASH_MISMATCH" in check["codes"]
    assert report["manifest_provenance_complete"] is False
    assert report["status"] == "FAIL"
    assert report["severity"] == "CRITICAL"
    assert report["release_blocking"] is True


def test_missing_manifest_provenance_is_a_structured_release_blocker(real_inputs):
    inputs = deepcopy(real_inputs)
    removed = inputs["artifact_manifest_all_phases"]["artifacts"].pop()
    report = run_module(inputs, {"created_at": CREATED_AT})["outputs"][
        "lineage_integrity_report"
    ]
    check = next(
        item
        for item in report["checks"]
        if item["contract_path"] == removed["path"]
    )
    assert check["manifest_source"] == ""
    assert "MISSING_MANIFEST_PROVENANCE" in check["codes"]
    assert report["release_blocking"] is True


def test_tampered_upstream_lineage_is_rejected_fail_closed(real_inputs):
    inputs = deepcopy(real_inputs)
    inputs["validated_module_registry"]["lineage_id"] = "sha256:" + "0" * 64
    with pytest.raises(ContractValidationError, match="lineage_id does not match"):
        run_module(inputs, {"created_at": CREATED_AT})


def test_self_parent_cycle_is_detected_after_valid_upstream_rehash(real_inputs):
    inputs = deepcopy(real_inputs)
    contract = inputs["contract_registry"]["contracts"][0]
    contract["consumes_from"]["modules"].append(contract["module_id"])
    _rehash_contract_registry(inputs["contract_registry"])
    report = run_module(inputs, {"created_at": CREATED_AT})["outputs"][
        "lineage_integrity_report"
    ]
    check = next(item for item in report["checks"] if item["module_id"] == contract["module_id"])
    assert "SELF_PARENT_CYCLE" in check["codes"]
    assert report["parent_links_valid"] is False
    assert report["release_blocking"] is True


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda value: value.pop("contract_registry"), "missing required inputs"),
        (
            lambda value: value["artifact_manifest_all_phases"].update(
                {"metadata": {"portfolio_weight": 1}}
            ),
            "forbidden input fields",
        ),
        (
            lambda value: value.update({"validated_module_registry": "not-an-artifact"}),
            "artifact mapping",
        ),
    ],
)
def test_rejects_missing_malformed_and_forbidden_inputs(real_inputs, mutation, expected):
    inputs = deepcopy(real_inputs)
    mutation(inputs)
    with pytest.raises(ContractValidationError, match=expected):
        run_module(inputs, {"created_at": CREATED_AT})


def test_rejects_manifest_path_traversal(real_inputs):
    inputs = deepcopy(real_inputs)
    inputs["artifact_manifest_all_phases"]["artifacts"][0]["path"] = "../outside.yaml"
    with pytest.raises(ContractValidationError, match="path traversal"):
        run_module(inputs, {"created_at": CREATED_AT})


def test_local_and_global_schemas_are_identical_and_output_is_typed(real_inputs):
    local_path = ROOT / "schemas" / "lineage_integrity_report.schema.yaml"
    global_path = GLOBAL_ROOT / "schemas" / "lineage_integrity_report.schema.yaml"
    assert local_path.read_bytes() == global_path.read_bytes()
    schema = _yaml(local_path)
    report = run_module(real_inputs, {"created_at": CREATED_AT})["outputs"][
        "lineage_integrity_report"
    ]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(report) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["checks"]["items"]["additionalProperties"] is False
    assert schema["properties"]["artifact_checks"]["items"]["additionalProperties"] is False

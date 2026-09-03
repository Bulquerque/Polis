from pathlib import Path
import hashlib
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

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S3_M01_hash_policy_enforcer import (
    ContractValidationError,
    run_module,
)


HASH_POLICY = ROOT / "contracts" / "HASHING_CONTRACTS.yaml"
REAL_MANIFESTS = sorted(WORKSPACE_ROOT.glob("phase_*/**/MANIFESTO.csv")) + [
    GLOBAL_ROOT / "MANIFESTO.csv"
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inline_manifest(entries):
    return {"artifacts": entries}


def test_real_manifests_are_fully_checked_and_current_hashes_pass():
    result = run_module(
        {
            "artifact_manifest_all_phases": [str(path) for path in REAL_MANIFESTS],
            "hash_policy_yaml": str(HASH_POLICY),
        },
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    report = result["outputs"]["hash_integrity_report"]

    assert result["module_id"] == "P0.S3.M01"
    assert len(REAL_MANIFESTS) == 11
    assert report["manifest_source_count"] == 11
    expected_count = sum(len(path.read_text(encoding="utf-8").splitlines()) - 1 for path in REAL_MANIFESTS)
    assert report["artifact_count"] == expected_count
    assert report["passed_count"] + report["hash_mismatch_count"] == expected_count
    assert report["missing_file_count"] == 0
    assert report["missing_hash_count"] == 0
    assert report["disallowed_algorithm_count"] == 0
    assert report["hash_mismatch_count"] == 0
    assert report["status"] == "PASS"
    assert report["severity"] == "NONE"
    assert report["release_blocking"] is False
    assert report["every_artifact_has_hash"] is True
    assert report["hash_algorithm_allowed"] is True
    assert report["all_digests_match"] is True
    assert report["paths_internal"] is True
    assert all(check["check_id"].startswith("HC-") for check in report["checks"])


def test_clean_inline_manifest_passes_with_calculated_sha256():
    paths = [ROOT / "contracts" / "HASHING_CONTRACTS.yaml", ROOT / "README.md"]
    entries = [
        {"path": path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": sha256(path)}
        for path in paths
    ]
    report = run_module(
        {
            "artifact_manifest_all_phases": inline_manifest(entries),
            "hash_policy_yaml": {"algorithm": "sha256", "fail_on": ["missing_hash", "hash_mismatch"]},
        },
        {"created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["hash_integrity_report"]
    assert report["artifact_count"] == 2
    assert report["passed_count"] == 2
    assert report["status"] == "PASS"
    assert report["severity"] == "NONE"
    assert report["release_blocking"] is False
    assert report["every_artifact_has_hash"] is True
    assert report["hash_algorithm_allowed"] is True
    assert report["all_digests_match"] is True
    assert report["promotion_blocked"] is True


def test_report_counts_missing_mismatch_and_disallowed_checks_fail_closed():
    pass_path = ROOT / "contracts" / "HASHING_CONTRACTS.yaml"
    missing_hash_path = ROOT / "README.md"
    mismatch_path = ROOT / "MODULE_CATALOG.md"
    disallowed_path = ROOT / "MODULE_BREAKDOWN.md"
    missing_path = ROOT / "artifacts" / "not-produced.bin"
    entries = [
        {"path": pass_path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": sha256(pass_path)},
        {"path": missing_path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": "1" * 64},
        {"path": missing_hash_path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": ""},
        {"path": mismatch_path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": "0" * 64},
        {
            "path": disallowed_path.relative_to(WORKSPACE_ROOT).as_posix(),
            "hash": "2" * 64,
            "algorithm": "md5",
        },
    ]
    report = run_module(
        {
            "artifact_manifest_all_phases": inline_manifest(entries),
            "hash_policy_yaml": str(HASH_POLICY),
        },
        {},
    )["outputs"]["hash_integrity_report"]
    assert report["artifact_count"] == 5
    assert report["passed_count"] == 1
    assert report["missing_file_count"] == 1
    assert report["missing_hash_count"] == 1
    assert report["hash_mismatch_count"] == 1
    assert report["disallowed_algorithm_count"] == 1
    assert {check["code"] for check in report["checks"]} == {
        "PASS",
        "MISSING_FILE",
        "MISSING_HASH",
        "HASH_MISMATCH",
        "DISALLOWED_ALGORITHM",
    }
    assert report["release_blocking"] is True
    assert report["every_artifact_has_hash"] is False
    assert report["hash_algorithm_allowed"] is False
    assert report["all_digests_match"] is False


def test_rejects_duplicate_artifact_paths():
    path = ROOT / "README.md"
    entry = {"path": path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": sha256(path)}
    with pytest.raises(ContractValidationError, match="duplicate artifact path"):
        run_module(
            {
                "artifact_manifest_all_phases": inline_manifest([entry, dict(entry)]),
                "hash_policy_yaml": str(HASH_POLICY),
            },
            {},
        )


def test_rejects_path_traversal_and_external_absolute_path(tmp_path):
    with pytest.raises(ContractValidationError, match="path traversal"):
        run_module(
            {
                "artifact_manifest_all_phases": inline_manifest(
                    [{"path": "phase_00_zero_trust/../outside.txt", "sha256": "0" * 64}]
                ),
                "hash_policy_yaml": str(HASH_POLICY),
            },
            {},
        )
    external = tmp_path / "external.bin"
    external.write_bytes(b"external")
    with pytest.raises(ContractValidationError, match="escapes workspace"):
        run_module(
            {
                "artifact_manifest_all_phases": inline_manifest(
                    [{"path": str(external), "sha256": sha256(external)}]
                ),
                "hash_policy_yaml": str(HASH_POLICY),
            },
            {},
        )


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"artifacts": []},
        {"artifacts": ["not-a-record"]},
        {"artifacts": [{"sha256": "0" * 64}]},
    ],
)
def test_rejects_malformed_manifests(manifest):
    with pytest.raises(ContractValidationError, match="manifest|artifact path"):
        run_module(
            {
                "artifact_manifest_all_phases": manifest,
                "hash_policy_yaml": str(HASH_POLICY),
            },
            {},
        )


@pytest.mark.parametrize(
    "policy,expected",
    [
        ({"algorithm": "md5", "fail_on": ["missing_hash", "hash_mismatch"]}, "allow SHA-256"),
        ({"algorithm": "sha256", "fail_on": []}, "must fail on"),
        ({"allowed_algorithms": "sha256", "fail_on": ["missing_hash", "hash_mismatch"]}, "malformed"),
    ],
)
def test_rejects_malformed_or_unsafe_hash_policy(policy, expected):
    path = ROOT / "README.md"
    with pytest.raises(ContractValidationError, match=expected):
        run_module(
            {
                "artifact_manifest_all_phases": inline_manifest(
                    [{"path": path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": sha256(path)}]
                ),
                "hash_policy_yaml": policy,
            },
            {},
        )


def test_rejects_forbidden_fields_recursively_in_inputs_and_manifest():
    path = ROOT / "README.md"
    entry = {"path": path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": sha256(path)}
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(
            {
                "artifact_manifest_all_phases": {
                    "artifacts": [entry],
                    "metadata": {"nested": [{"portfolio_weight": 1}]},
                },
                "hash_policy_yaml": str(HASH_POLICY),
            },
            {},
        )
    entry["metadata"] = {"rank_score": 1}
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(
            {
                "artifact_manifest_all_phases": inline_manifest([entry]),
                "hash_policy_yaml": str(HASH_POLICY),
            },
            {},
        )


def test_local_and_global_report_schemas_are_identical_and_output_is_typed():
    local_schema_path = ROOT / "schemas" / "hash_integrity_report.schema.yaml"
    global_schema_path = GLOBAL_ROOT / "schemas" / "hash_integrity_report.schema.yaml"
    assert local_schema_path.read_bytes() == global_schema_path.read_bytes()
    schema = yaml.safe_load(local_schema_path.read_text(encoding="utf-8"))
    path = ROOT / "README.md"
    report = run_module(
        {
            "artifact_manifest_all_phases": inline_manifest(
                [{"path": path.relative_to(WORKSPACE_ROOT).as_posix(), "sha256": sha256(path)}]
            ),
            "hash_policy_yaml": str(HASH_POLICY),
        },
        {"created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["hash_integrity_report"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(report) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["checks"]["items"]["additionalProperties"] is False

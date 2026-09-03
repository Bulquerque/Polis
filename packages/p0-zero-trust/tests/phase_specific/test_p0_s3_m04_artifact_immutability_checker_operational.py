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

from quant_pipeline.phase_00_zero_trust_guardian.modules import (
    P0_S3_M04_artifact_immutability_checker as checker,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S3_M04_artifact_immutability_checker import (
    ContractValidationError,
    run_module,
)


REAL_MANIFESTS = sorted(WORKSPACE_ROOT.glob("phase_*/**/MANIFESTO.csv")) + [
    GLOBAL_ROOT / "MANIFESTO.csv"
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def record(path, **extra):
    return {"artifact_id": extra.pop("artifact_id", relative(path)), "path": relative(path), "sha256": digest(path), **extra}


def inputs(current_entries, history_entries=None, release_entries=None):
    history_entries = history_entries or [dict(current_entries[0])]
    release_entries = release_entries or [dict(current_entries[0])]
    return {
        "artifact_manifest_all_phases": {"artifacts": current_entries},
        "hash_history": {"history_id": "history-v1", "entries": history_entries},
        "release_manifest_previous": {
            "release_id": "release-v1",
            "artifacts": release_entries,
        },
    }


def report_for(current_entries, history_entries=None, release_entries=None):
    return run_module(inputs(current_entries, history_entries, release_entries), {})[
        "outputs"
    ]["immutability_report"]


def test_unchanged_artifact_with_consistent_history_and_release_passes():
    current = record(ROOT / "README.md")
    report = report_for([current])
    assert report["artifact_count"] == 1
    assert report["history_entry_count"] == 1
    assert report["previous_release_entry_count"] == 1
    assert report["checked_identity_count"] == 1
    assert report["findings"] == []
    assert report["status"] == "PASS"
    assert report["severity"] == "NONE"
    assert report["release_blocking"] is False
    assert report["no_raw_overwrite"] is True
    assert report["schema_change_requires_version_bump"] is True
    assert report["artifact_identity_stable"] is True
    assert report["history_present"] is True
    assert report["previous_release_present"] is True
    assert report["promotion_blocked"] is True


def test_raw_overwrite_is_detected_and_release_blocking():
    path = ROOT / "README.md"
    current = record(path, artifact_id="raw-snapshot", artifact_type="raw")
    previous = {
        **current,
        "sha256": "0" * 64,
    }
    report = report_for([current], [previous], [previous])
    finding = next(item for item in report["findings"] if item["code"] == "RAW_OVERWRITE")
    assert finding["artifact_identity"] == "raw-snapshot"
    assert finding["release_blocking"] is True
    assert report["raw_overwrite_count"] == 1
    assert report["no_raw_overwrite"] is False
    assert report["status"] == "FAIL"
    assert report["release_blocking"] is True


def test_schema_content_change_without_strict_version_bump_is_blocked():
    path = ROOT / "schemas" / "schema_registry.schema.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    current = record(path, artifact_id="schema-registry", schema_version=document["schema_version"])
    previous = {**current, "sha256": "0" * 64}
    report = report_for([current], [previous], [previous])
    assert report["schema_without_bump_count"] == 1
    assert report["schema_change_requires_version_bump"] is False
    assert {item["code"] for item in report["findings"]} == {
        "SCHEMA_VERSION_NOT_BUMPED"
    }


def test_strict_schema_version_bump_allows_changed_schema(monkeypatch):
    path = ROOT / "schemas" / "schema_registry.schema.yaml"
    current = record(path, artifact_id="schema-registry")
    previous = {**current, "sha256": "0" * 64, "schema_version": "v14.1-rc4.1"}
    original = checker._schema_version

    def bumped(record_value, path_value):
        if path_value == path:
            return "v14.1-rc4.2"
        return original(record_value, path_value)

    monkeypatch.setattr(checker, "_schema_version", bumped)
    report = report_for([current], [previous], [previous])
    assert report["schema_without_bump_count"] == 0
    assert report["schema_change_requires_version_bump"] is True
    assert report["status"] == "PASS"


def test_identity_reuse_on_existing_path_or_moved_identity_is_blocking():
    first = ROOT / "README.md"
    second = ROOT / "MODULE_CATALOG.md"
    current = record(first, artifact_id="new-identity")
    previous = record(first, artifact_id="old-identity")
    report = report_for([current], [previous], [previous])
    assert report["identity_reuse_count"] == 1
    assert report["artifact_identity_stable"] is False

    moved = record(second, artifact_id="stable-identity")
    old_location = record(first, artifact_id="stable-identity")
    report = report_for([moved], [old_location], [old_location])
    assert report["identity_reuse_count"] == 1
    assert report["release_blocking"] is True


def test_current_manifest_reusing_identity_is_reported():
    first = record(ROOT / "README.md", artifact_id="duplicated")
    second = record(ROOT / "MODULE_CATALOG.md", artifact_id="duplicated")
    report = report_for([first, second], [first], [first])
    assert report["identity_reuse_count"] == 1
    assert report["status"] == "FAIL"


def test_history_release_conflict_is_blocking():
    current = record(ROOT / "README.md", artifact_id="artifact-a")
    historic = dict(current)
    released = {**current, "sha256": "0" * 64}
    report = report_for([current], [historic], [released])
    assert report["historical_conflict_count"] == 1
    assert any(item["code"] == "HISTORY_RELEASE_CONFLICT" for item in report["findings"])
    assert report["release_blocking"] is True


def test_missing_file_missing_hash_and_current_mismatch_are_detailed():
    missing_path = ROOT / "artifacts" / "not-produced.bin"
    missing_file = {
        "artifact_id": "missing-file",
        "path": relative(missing_path),
        "sha256": "1" * 64,
    }
    missing_hash = {
        "artifact_id": "missing-hash",
        "path": relative(ROOT / "README.md"),
        "sha256": "",
    }
    mismatch = {
        "artifact_id": "mismatch",
        "path": relative(ROOT / "MODULE_CATALOG.md"),
        "sha256": "0" * 64,
    }
    baseline = record(ROOT / "MODULE_BREAKDOWN.md", artifact_id="baseline")
    report = report_for(
        [missing_file, missing_hash, mismatch, baseline], [baseline], [baseline]
    )
    codes = {item["code"] for item in report["findings"]}
    assert {"CURRENT_FILE_MISSING", "CURRENT_HASH_MISSING", "CURRENT_HASH_MISMATCH"}.issubset(codes)
    assert report["missing_current_file_count"] == 1
    assert report["missing_current_hash_count"] == 1
    assert report["current_hash_mismatch_count"] == 1
    assert report["release_blocking"] is True


def test_real_all_phase_manifests_are_checked_against_materialized_timeline():
    baseline_path = ROOT / "README.md"
    baseline = record(baseline_path)
    report = run_module(
        {
            "artifact_manifest_all_phases": [str(path) for path in REAL_MANIFESTS],
            "hash_history": {"entries": [baseline]},
            "release_manifest_previous": {
                "release_id": "release-v1",
                "artifacts": [baseline],
            },
        },
        {"created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["immutability_report"]
    assert len(REAL_MANIFESTS) == 11
    expected_count = sum(len(path.read_text(encoding="utf-8").splitlines()) - 1 for path in REAL_MANIFESTS)
    assert report["artifact_count"] == expected_count
    assert report["current_hash_mismatch_count"] == 0
    assert report["status"] == "PASS"
    assert report["release_blocking"] is False


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("hash_history", {}, "non-empty artifact entries"),
        ("release_manifest_previous", {}, "non-empty artifact entries"),
        ("release_manifest_previous", {"artifacts": [{"path": "README.md", "sha256": "0" * 64}]}, "release identity"),
    ],
)
def test_requires_materialized_history_and_previous_release(field, value, expected):
    current = record(ROOT / "README.md")
    data = inputs([current])
    data[field] = value
    with pytest.raises(ContractValidationError, match=expected):
        run_module(data, {})


def test_rejects_malformed_duplicate_timeline_and_schema_version_lie():
    current = record(ROOT / "README.md")
    duplicate = [dict(current), dict(current)]
    with pytest.raises(ContractValidationError, match="duplicate identity or path"):
        run_module(inputs([current], duplicate, [current]), {})

    schema_path = ROOT / "schemas" / "schema_registry.schema.yaml"
    schema_entry = record(schema_path, schema_version="v99")
    with pytest.raises(ContractValidationError, match="differs from file content"):
        run_module(inputs([schema_entry], [current], [current]), {})


def test_rejects_traversal_external_and_forbidden_recursive_inputs(tmp_path):
    traversal = {"artifact_id": "bad", "path": "../outside", "sha256": "0" * 64}
    with pytest.raises(ContractValidationError, match="path traversal"):
        run_module(inputs([traversal], [record(ROOT / "README.md")], [record(ROOT / "README.md")]), {})

    external = tmp_path / "external.bin"
    external.write_bytes(b"external")
    external_entry = {"artifact_id": "external", "path": str(external), "sha256": digest(external)}
    with pytest.raises(ContractValidationError, match="escapes workspace"):
        run_module(inputs([external_entry], [record(ROOT / "README.md")], [record(ROOT / "README.md")]), {})

    current = record(ROOT / "README.md")
    data = inputs([current])
    data["hash_history"]["metadata"] = {"nested": [{"trade_decision": "BUY"}]}
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(data, {})


def test_local_global_schemas_identical_and_output_is_typed():
    local_schema = ROOT / "schemas" / "immutability_report.schema.yaml"
    global_schema = GLOBAL_ROOT / "schemas" / "immutability_report.schema.yaml"
    assert local_schema.read_bytes() == global_schema.read_bytes()
    schema = yaml.safe_load(local_schema.read_text(encoding="utf-8"))
    current = record(ROOT / "README.md")
    report = run_module(
        inputs([current]), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["immutability_report"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(report) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["findings"]["items"]["additionalProperties"] is False

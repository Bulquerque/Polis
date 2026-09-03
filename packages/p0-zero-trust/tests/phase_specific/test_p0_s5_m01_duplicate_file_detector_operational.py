from copy import deepcopy
from importlib import import_module
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
module = import_module("quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S5_M01_duplicate_file_detector")


def _inputs():
    return {
        "source_tree_manifest": {"files": [{"path": "a.py", "size_bytes": 1}, {"path": "b.py", "size_bytes": 1}, {"path": "c.py", "size_bytes": 2}]},
        "file_hash_manifest": {"entries": [{"path": "a.py", "sha256": "a" * 64}, {"path": "b.py", "sha256": "a" * 64}, {"path": "c.py", "sha256": "b" * 64}]},
    }


def test_detects_unapproved_duplicate_and_blocks_release():
    report = module.run_module(_inputs(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["duplicate_file_report"]
    assert report["checked_file_count"] == 3
    assert report["duplicate_group_count"] == 1
    assert report["status"] == "FAIL"
    assert report["release_blocking"] is True
    assert report["duplicate_groups"][0]["paths"] == ["a.py", "b.py"]


def test_allowlisted_duplicate_is_audited_but_not_blocking():
    report = module.run_module(_inputs(), {"allowlisted_duplicate_groups": [["b.py", "a.py"]]})["outputs"]["duplicate_file_report"]
    assert report["duplicate_hashes_detected"] is True
    assert report["blocking_duplicate_group_count"] == 0
    assert report["status"] == "PASS"


def test_schema_duplicates_are_classified():
    data = _inputs()
    for index, path in enumerate(("x/a.schema.yaml", "y/a.schema.yaml")):
        data["source_tree_manifest"]["files"][index]["path"] = path
        data["file_hash_manifest"]["entries"][index]["path"] = path
    report = module.run_module(data, {})["outputs"]["duplicate_file_report"]
    assert report["schema_duplicate_group_count"] == 1


def test_no_duplicates_passes():
    data = _inputs()
    data["file_hash_manifest"]["entries"][1]["sha256"] = "c" * 64
    report = module.run_module(data, {})["outputs"]["duplicate_file_report"]
    assert report["duplicate_group_count"] == 0
    assert report["status"] == "PASS"


@pytest.mark.parametrize("field", ["source_tree_manifest", "file_hash_manifest"])
def test_rejects_placeholder(field):
    data = _inputs(); data[field] = {"source": field}
    with pytest.raises(ValueError, match="non-empty materialized"):
        module.run_module(data, {})


def test_rejects_coverage_mismatch_duplicate_paths_hashes_and_traversal():
    data = _inputs(); data["file_hash_manifest"]["entries"].pop()
    with pytest.raises(ValueError, match="coverage mismatch"): module.run_module(data, {})
    data = _inputs(); data["file_hash_manifest"]["entries"][1]["path"] = "a.py"
    with pytest.raises(ValueError, match="duplicate path"): module.run_module(data, {})
    data = _inputs(); data["source_tree_manifest"]["files"][0]["path"] = "../a.py"
    with pytest.raises(ValueError, match="escapes repository"): module.run_module(data, {})
    data = _inputs(); data["file_hash_manifest"]["entries"][0]["sha256"] = "bad"
    with pytest.raises(ValueError, match="sha256 is malformed"): module.run_module(data, {})


def test_rejects_forbidden_recursively_and_output_matches_schema():
    data = _inputs(); data["source_tree_manifest"]["metadata"] = {"nested": {"target": 1}}
    with pytest.raises(ValueError, match="forbidden input fields"): module.run_module(data, {})
    report = module.run_module(_inputs(), {})["outputs"]["duplicate_file_report"]
    schema = yaml.safe_load((ROOT / "schemas" / "duplicate_file_report.schema.yaml").read_text(encoding="utf-8"))
    assert set(report) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(report)

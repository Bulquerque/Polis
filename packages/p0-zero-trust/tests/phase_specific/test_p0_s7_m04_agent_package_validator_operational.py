from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from quant_pipeline.phase_00_zero_trust_guardian.modules import _p0_s7_utils
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S7_M04_agent_package_validator import run_module

def policy():
    return {"artifact_id": "agent-execution-policy-" + "c" * 12, "lineage_id": "sha256:" + "c" * 64, "pipeline_version": "V14.1-RC4.1", "status": "PASS", "release_blocking": False, "required_package_files": ["SKILL.md", "tests/test_skill.py"], "permissions": {"read": True}}

def make_zip(root, extra=None):
    path = root / "agent.zip"
    with zipfile.ZipFile(path, "w") as z: z.writestr("SKILL.md", "# Skill"); z.writestr("tests/test_skill.py", "def test_ok(): pass"); extra and z.writestr(extra, "bad")
    return path

def test_validates_structure_hashes_and_required_files(tmp_path, monkeypatch):
    monkeypatch.setattr(_p0_s7_utils, "REPOSITORY_ROOT", tmp_path); make_zip(tmp_path)
    out = run_module({"agent_execution_policy": policy(), "agent_phase_package_zip": "agent.zip"}, {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["agent_package_validation_report"]
    assert out["status"] == "PASS" and out["package_structure_valid"] and out["entry_count"] == 2

def test_blocks_cache_inside_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(_p0_s7_utils, "REPOSITORY_ROOT", tmp_path); make_zip(tmp_path, "__pycache__/x.pyc")
    out = run_module({"agent_execution_policy": policy(), "agent_phase_package_zip": "agent.zip"})["outputs"]["agent_package_validation_report"]
    assert out["status"] == "BLOCKED" and not out["no_cache_in_zip"]

def test_blocks_zip_slip(tmp_path, monkeypatch):
    monkeypatch.setattr(_p0_s7_utils, "REPOSITORY_ROOT", tmp_path); make_zip(tmp_path, "../escape.py")
    out = run_module({"agent_execution_policy": policy(), "agent_phase_package_zip": "agent.zip"})["outputs"]["agent_package_validation_report"]
    assert any(x["code"] == "unsafe_path" for x in out["findings"])

def test_never_passes_with_blocked_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(_p0_s7_utils, "REPOSITORY_ROOT", tmp_path); make_zip(tmp_path)
    blocked = policy(); blocked["status"] = "FAIL"; blocked["release_blocking"] = True
    import pytest
    with pytest.raises(Exception): run_module({"agent_execution_policy": blocked, "agent_phase_package_zip": "agent.zip"})

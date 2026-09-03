from pathlib import Path
import ast
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S3_M01_hash_policy_enforcer import run_module as run_hash
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S3_M03_artifact_manifest_auditor import run_module as run_manifest
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S3_M04_artifact_immutability_checker import run_module as run_immutability
from quant_pipeline.phase_00_zero_trust_guardian.modules._p0_s3_artifacts import ArtifactRecord
from quant_pipeline.phase_00_zero_trust_guardian.modules._p0_s3_lineage import runtime_lineage


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def record(path: Path, artifact_id: str, **extra):
    return {"artifact_id": artifact_id, "path": relative(path), "sha256": digest(path), **extra}


def test_m01_uses_streaming_hash_and_canonical_sources(monkeypatch):
    path = ROOT / "README.md"
    original = Path.read_bytes
    expected = digest(path)

    def forbidden_read_bytes(self):
        if self == path:
            raise AssertionError("artifact hashing must not use Path.read_bytes")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    report = run_hash(
        {
            "artifact_manifest_all_phases": {"artifacts": [{"path": relative(path), "sha256": expected}]},
            "hash_policy_yaml": str(ROOT / "contracts" / "HASHING_CONTRACTS.yaml"),
        },
        {"created_at": "2026-07-22T00:00:00Z"},
    )["outputs"]["hash_integrity_report"]
    assert report["status"] == "PASS"
    assert not report["policy_source"].startswith("/")
    assert all(not item["manifest_source"].startswith("/") for item in report["checks"])


def test_runtime_lineage_detects_unknown_producer_missing_parent_and_cycle():
    dummy = Path("/tmp/not-used")
    records = [
        ArtifactRecord("inline", "a", dummy, "sha256", "0" * 64, "A", "P0.S3.M01", ("B",), "", "REPLACEABLE", False, {"artifact_id": "A"}),
        ArtifactRecord("inline", "b", dummy, "sha256", "0" * 64, "B", "P99.S1.M01", ("A", "MISSING"), "", "REPLACEABLE", False, {"artifact_id": "B"}),
    ]
    checks, cycles, available = runtime_lineage(records, {"P0.S3.M01"})
    assert available is True
    assert cycles == [["A", "B"]]
    by_id = {item["artifact_id"]: item for item in checks}
    assert "RUNTIME_LINEAGE_CYCLE" in by_id["A"]["codes"]
    assert {"UNKNOWN_PRODUCER_MODULE", "MISSING_PARENT_ARTIFACT", "RUNTIME_LINEAGE_CYCLE"}.issubset(by_id["B"]["codes"])


def test_m03_distinguishes_critical_declared_from_materialized():
    missing = ROOT / "artifacts" / "never-created.bin"
    data = {
        "manifesto_all_packages": {"artifacts": [{"path": relative(missing), "sha256": "1" * 64}]},
        "artifact_registry": {"artifacts": [{"artifact_id": "critical", "path": relative(missing), "critical": True}]},
        "hash_integrity_report": {"status": "PASS", "release_blocking": False},
        "lineage_integrity_report": {"status": "PASS", "release_blocking": False},
    }
    outputs = run_manifest(data, {"created_at": "2026-07-22T00:00:00Z"})["outputs"]
    audit = outputs["artifact_manifest_audit_report"]
    integrity = outputs["artifact_integrity_report"]
    codes = {item["code"] for item in audit["findings"]}
    assert "CRITICAL_FILE_NOT_MATERIALIZED" in codes
    assert audit["critical_declared_count"] == 1
    assert audit["critical_materialized_count"] == 0
    assert integrity["component_statuses"]["manifest"] == "FAIL"
    assert integrity["integrity_summary"] == "FAIL"


def test_m04_supports_explicit_genesis_baseline():
    current = record(ROOT / "README.md", "readme")
    report = run_immutability(
        {
            "artifact_manifest_all_phases": {"artifacts": [current]},
            "hash_history": {"genesis": True, "entries": []},
            "release_manifest_previous": {"genesis": True, "release_id": "GENESIS", "artifacts": []},
        },
        {"created_at": "2026-07-22T00:00:00Z"},
    )["outputs"]["immutability_report"]
    assert report["genesis"] is True
    assert report["history_present"] is False
    assert report["previous_release_present"] is False
    assert report["history_chain_mode"] == "GENESIS"
    assert report["status"] == "PASS"


def test_m04_blocks_removal_of_immutable_artifact():
    current = record(ROOT / "README.md", "current")
    removed = record(ROOT / "MODULE_CATALOG.md", "immutable-old", artifact_type="raw", mutability_class="IMMUTABLE")
    baseline = [current, removed]
    report = run_immutability(
        {
            "artifact_manifest_all_phases": {"artifacts": [current]},
            "hash_history": {"entries": baseline},
            "release_manifest_previous": {"release_id": "r1", "artifacts": baseline},
        },
        {},
    )["outputs"]["immutability_report"]
    assert report["immutable_removed_count"] == 1
    assert report["immutable_artifacts_preserved"] is False
    assert any(item["code"] == "IMMUTABLE_ARTIFACT_REMOVED" for item in report["findings"])
    assert report["release_blocking"] is True


def test_m04_detects_broken_append_only_history_chain():
    current = record(ROOT / "README.md", "readme")
    chained = {**current, "previous_record_hash": "", "record_hash": "0" * 64}
    report = run_immutability(
        {
            "artifact_manifest_all_phases": {"artifacts": [current]},
            "hash_history": {"entries": [chained]},
            "release_manifest_previous": {"release_id": "r1", "artifacts": [current]},
        },
        {},
    )["outputs"]["immutability_report"]
    assert report["history_chain_valid"] is False
    assert report["history_chain_failure_count"] == 1
    assert any(item["code"] == "HISTORY_CHAIN_BROKEN" for item in report["findings"])


def test_s3_python_respects_clean_code_size_limits():
    module_dir = ROOT / "src" / "quant_pipeline" / "phase_00_zero_trust_guardian" / "modules"
    paths = sorted(module_dir.glob("P0_S3_M0*.py")) + sorted(module_dir.glob("_p0_s3_*.py"))
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 350, f"{path.name} has {len(lines)} lines"
        tree = ast.parse("\n".join(lines))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                assert length <= 60, f"{path.name}:{node.name} has {length} lines"

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import yaml


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def test_normative_authority_is_global_master_and_phase0_tree_is_mirror():
    root = workspace_root()
    p0 = root / "phase_00_zero_trust" / "phase_00_zero_trust_guardian_agent_package_RC4_1" / "source_of_truth"
    mirror = root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1" / "source_of_truth"
    assert p0.is_dir()
    assert mirror.is_dir()
    global_readme = (mirror / "README.md").read_text(encoding="utf-8")
    assert "current_master" in global_readme
    assert "single normative documentation master" in global_readme
    p0_readme = (p0 / "README.md").read_text(encoding="utf-8")
    assert "derived_mirror" in p0_readme
    assert "global_contracts_parallel_agents" in p0_readme

    harness = (root / "VALIDATION_HARNESS.md").read_text(encoding="utf-8")
    assert "global_contracts_parallel_agents" in harness
    assert "only normative contract tree" in harness
    assert "Phase 0 `source_of_truth` is a derived compatibility mirror" in harness


def test_provider_registry_tests_use_global_master():
    test_file = Path(__file__).with_name("test_provider_registries.py")
    text = test_file.read_text(encoding="utf-8")
    assert '"global_contracts_parallel_agents"' in text
    assert '"phase_00_zero_trust"' not in text


def test_all_phase_bindings_expose_point_in_time_policy():
    root = workspace_root()
    bindings = sorted(root.glob("phase_*/*_agent_package_RC4_1/SOURCE_OF_TRUTH.md"))
    assert len(bindings) == 10
    missing = [str(path) for path in bindings if "POINT_IN_TIME_AI_POLICY.md" not in path.read_text(encoding="utf-8")]
    assert not missing, missing


def test_global_mirror_has_no_registry_drift():
    root = workspace_root()
    p0 = root / "phase_00_zero_trust" / "phase_00_zero_trust_guardian_agent_package_RC4_1" / "source_of_truth" / "registries"
    mirror = root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1" / "source_of_truth" / "registries"
    p0_files = {path.name for path in p0.glob("*.yaml")}
    mirror_files = {path.name for path in mirror.glob("*.yaml")}
    assert p0_files == mirror_files
    for name in sorted(p0_files):
        assert (p0 / name).read_bytes() == (mirror / name).read_bytes(), name


def test_master_mirror_equality_with_only_registered_exceptions():
    root = workspace_root()
    master = root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1" / "source_of_truth"
    mirror = root / "phase_00_zero_trust" / "phase_00_zero_trust_guardian_agent_package_RC4_1" / "source_of_truth"
    registry = yaml.safe_load((master / "registries" / "canonical_doc_registry.yaml").read_text(encoding="utf-8"))
    policy = registry["derived_mirror"]
    assert registry["path_base"] == "workspace_root"
    assert policy["canonical_source"] == registry["canonical_source"]
    assert policy["generated"] is True
    assert policy["do_not_edit_locally"] is True
    exceptions = {item["path"] for item in policy["exceptions"]}
    assert exceptions == {"README.md"}

    def files(base: Path) -> set[str]:
        return {
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }

    master_files = files(master)
    mirror_files = files(mirror)
    assert master_files == mirror_files
    for rel in sorted(master_files - exceptions):
        assert (master / rel).read_bytes() == (mirror / rel).read_bytes(), rel
    assert exceptions <= master_files
    hierarchy = (mirror / "standards" / "DOCUMENTATION_HIERARCHY.md").read_text(encoding="utf-8")
    assert "master global" in hierarchy
    assert "ela não é autoridade normativa" in hierarchy
    assert "normativamente na Fase 0" not in hierarchy


def test_all_distributed_yaml_json_and_csv_parse():
    root = workspace_root()
    failures = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".codex" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            if path.suffix.lower() in {".yaml", ".yml"}:
                yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            elif path.suffix.lower() == ".json":
                raw = path.read_bytes()
                payload = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
                json.loads(payload.decode("utf-8-sig"))
            elif path.suffix.lower() == ".csv":
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.reader(handle))
                if rows:
                    width = len(rows[0])
                    assert all(len(row) == width for row in rows), "inconsistent CSV row width"
        except Exception as exc:  # pragma: no cover - assertion reports every bad path
            failures.append(f"{path.relative_to(root).as_posix()}: {exc}")
    assert not failures, failures


def test_release_builder_is_byte_reproducible(tmp_path):
    root = workspace_root()
    script = root / "tools" / "build_release_package.py"
    spec = importlib.util.spec_from_file_location("release_builder_under_test", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    roots = [tmp_path / "first_source", tmp_path / "second_source"]
    for source in roots:
        source.mkdir()
        (source / "README.md").write_text("deterministic\n", encoding="utf-8")
        (source / "nested").mkdir()
        (source / "nested" / "contract.yaml").write_text("status: pass\n", encoding="utf-8")
        (source / "Zeta.txt").write_text("upper\n", encoding="utf-8")
        (source / "alpha.txt").write_text("lower\n", encoding="utf-8")
    first = roots[0] / "release.zip"
    second = roots[1] / "release.zip"
    report_one = module.build(roots[0], first)
    report_two = module.build(roots[1], second)
    assert report_one["status"] == report_two["status"] == "pass"
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["alpha.txt", "nested/contract.yaml", "README.md", "Zeta.txt"]
        assert {item.compress_type for item in archive.infolist()} == {zipfile.ZIP_STORED}


def test_manifest_binds_final_documentary_audit_outputs():
    root = workspace_root()
    manifest = {
        row["path"]: row
        for row in csv.DictReader((root / "MANIFESTO_RC4_1.csv").open(encoding="utf-8"))
    }
    for rel in (
        "reports/documentation/audit_findings.json",
        "reports/documentation/audit_report.md",
        "reports/documentation/fix_list.md",
    ):
        data = (root / rel).read_bytes()
        assert manifest[rel]["sha256"] == hashlib.sha256(data).hexdigest()


def test_historical_state_tools_are_blocked_by_default_in_isolated_copy(tmp_path):
    root = workspace_root()
    isolated_tools = tmp_path / "tools"
    isolated_tools.mkdir()
    names = [
        "materialize_conservative_judge_verdicts.py",
        "materialize_module_status.py",
        "materialize_phase0_status.py",
        "reconcile_documentation_summary.py",
        "reconcile_local_status.py",
        "reopen_unproven_decisions.py",
    ]
    shutil.copy2(root / "tools" / "historical_tool_guard.py", isolated_tools)
    for name in names:
        target = isolated_tools / name
        shutil.copy2(root / "tools" / name, target)
        result = subprocess.run(
            [sys.executable, str(target)],
            cwd=tmp_path,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2, (name, result.stdout, result.stderr)
        assert '"document_status": "historical"' in result.stdout
    assert not (tmp_path / "PROJECT_STATE.json").exists()
    assert not (tmp_path / "GLOBAL_DECISIONS_NEEDED.csv").exists()
    assert not (tmp_path / "phases").exists()


def test_offline_ltr_producer_is_registered_in_the_global_master():
    root = workspace_root()
    registry = root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1" / "source_of_truth" / "registries" / "offline_training_pipeline_registry.yaml"
    text = registry.read_text(encoding="utf-8")
    assert "pipeline_id: offline_ltr_training_pipeline" in text
    assert "status: contract_surface_implemented" in text
    assert "phase_07_extracted/phase_07_ranking_agent_package_RC4_1/src/quant_pipeline/phase_07_ranking/offline_ltr_training_pipeline.py" in text


def test_workspace_contains_no_python_runtime_cache_artifacts():
    root = workspace_root()
    cache_directories = {"__pycache__", ".pytest_cache"}
    forbidden = []
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    ).stdout.decode().split("\0")
    for name in tracked:
        if not name:
            continue
        path = root / name
        if path.name in cache_directories or path.suffix.lower() in {".pyc", ".pyo"}:
            forbidden.append(name)
    assert not forbidden, f"runtime cache artifacts must be removed: {sorted(forbidden)}"

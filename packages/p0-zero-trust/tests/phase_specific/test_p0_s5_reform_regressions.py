from importlib import import_module
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def mod(number, name):
    return import_module(f"quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S5_M{number:02d}_{name}")


M01 = mod(1, "duplicate_file_detector")
M02 = mod(2, "monolith_code_detector")
M03 = mod(3, "forbidden_import_detector")
M04 = mod(4, "hidden_global_state_detector")
M05 = mod(5, "module_contract_coverage_checker")
M06 = mod(6, "code_style_quality_reporter")


def tree(path="phase_03_extracted/pkg/a.py", content="def ok():\n    return 1\n"):
    return {"files": [{"path": path, "content": content}]}


def canonical_policy(**overrides):
    policy = {
        "max_python_file_lines": 350,
        "max_function_lines": 60,
        "max_class_lines": 180,
        "max_module_public_functions": 12,
        "max_cyclomatic_complexity": 10,
        "allowed_module_globals": [],
    }
    policy.update(overrides)
    return policy


def test_m02_honors_canonical_max_python_file_lines_key():
    report = M02.run_module({
        "source_tree_manifest": tree(content="x = 1\ny = 2\nz = 3\n"),
        "code_quality_policy_yaml": canonical_policy(max_python_file_lines=2),
    })["outputs"]["monolith_report"]
    assert any(item["kind"] == "FILE_TOO_LONG" for item in report["findings"])


def test_m02_detects_class_size_public_function_count_and_complexity():
    code = "\n".join([
        "def complex_fn(x):",
        "    if x:",
        "        if x > 1:",
        "            return 1",
        "    return 0",
        "",
        "def second(): return 2",
        "class Big:",
        "    def a(self): return 1",
        "    def b(self): return 2",
    ])
    report = M02.run_module({
        "source_tree_manifest": tree(content=code),
        "code_quality_policy_yaml": canonical_policy(
            max_class_lines=2,
            max_module_public_functions=1,
            max_cyclomatic_complexity=2,
        ),
    })["outputs"]["monolith_report"]
    kinds = {item["kind"] for item in report["findings"]}
    assert {"CLASS_TOO_LONG", "TOO_MANY_PUBLIC_FUNCTIONS", "CYCLOMATIC_COMPLEXITY"} <= kinds


def test_m02_requires_reason_for_exception():
    report = M02.run_module({
        "source_tree_manifest": tree(path="phase_00_zero_trust/pkg/runner.py", content="x=1\ny=2\nz=3\n"),
        "code_quality_policy_yaml": canonical_policy(max_python_file_lines=2),
    }, {"quality_exceptions": [{"path": "phase_00_zero_trust/pkg/runner.py", "reason": "generated orchestration boundary"}]})["outputs"]["monolith_report"]
    assert report["status"] == "PASS"


def test_m03_detects_dynamic_import_literal():
    report = M03.run_module({
        "source_tree_manifest": tree(content="import importlib\nimportlib.import_module('phase_09.learning')\n"),
        "forbidden_import_policy_yaml": {"forbidden_imports": ["phase_09.*"]},
    })["outputs"]["forbidden_import_report"]
    assert report["violations"][0]["kind"] == "DYNAMIC_IMPORT"


def test_m03_detects_cross_phase_internal_import_when_path_identifies_phase():
    report = M03.run_module({
        "source_tree_manifest": tree(
            path="phase_03_extracted/pkg/a.py",
            content="from quant_pipeline.phase_08_portfolio_backtest.foo import bar\n",
        ),
        "forbidden_import_policy_yaml": {"forbidden_imports": ["never.match"], "enforce_phase_boundaries": True},
    })["outputs"]["forbidden_import_report"]
    assert report["release_blocking"] is True
    assert "CROSS_PHASE_INTERNAL_IMPORT" in report["violations"][0]["matched_rule"]


def test_m03_allows_common_dependency():
    report = M03.run_module({
        "source_tree_manifest": tree(content="from quant_pipeline.common.hashing import stable_digest\n"),
        "forbidden_import_policy_yaml": {"forbidden_imports": ["never.match"]},
    })["outputs"]["forbidden_import_report"]
    assert report["status"] == "PASS"


def test_m04_detects_global_statement_and_module_level_mutation():
    code = "CACHE = {}\nCACHE.update({'x': 1})\nVALUE = 0\ndef change():\n    global VALUE\n    VALUE += 1\n"
    report = M04.run_module({
        "source_tree_manifest": tree(content=code),
        "code_quality_policy_yaml": canonical_policy(),
    })["outputs"]["hidden_global_state_report"]
    kinds = {item["kind"] for item in report["violations"]}
    assert {"MUTABLE_MODULE_GLOBAL", "MODULE_LEVEL_MUTATION", "GLOBAL_STATEMENT_MUTATION"} <= kinds


def test_m04_env_variable_name_constant_is_not_secret():
    report = M04.run_module({
        "source_tree_manifest": tree(content="API_KEY_ENV_NAME = 'NVIDIA_API_KEY'\n"),
        "code_quality_policy_yaml": canonical_policy(),
    })["outputs"]["hidden_global_state_report"]
    assert report["status"] == "PASS"


def test_m04_detects_stateful_client_at_import_time():
    report = M04.run_module({
        "source_tree_manifest": tree(content="CLIENT = Client()\n"),
        "code_quality_policy_yaml": canonical_policy(),
    })["outputs"]["hidden_global_state_report"]
    assert report["violations"][0]["kind"] == "IMPORT_TIME_STATEFUL_OBJECT"


def test_m01_classifies_common_utility_duplicate_as_blocking():
    inputs = {
        "source_tree_manifest": {"files": [
            {"path": "phase_01/pkg/contracts.py", "size_bytes": 1},
            {"path": "phase_02/pkg/contracts.py", "size_bytes": 1},
        ]},
        "file_hash_manifest": {"entries": [
            {"path": "phase_01/pkg/contracts.py", "sha256": "a" * 64},
            {"path": "phase_02/pkg/contracts.py", "sha256": "a" * 64},
        ]},
    }
    report = M01.run_module(inputs)["outputs"]["duplicate_file_report"]
    assert report["duplicate_groups"][0]["classification"] == "DUPLICATED_COMMON_UTILITY"
    assert report["release_blocking"] is True


def test_m01_package_marker_duplicate_is_nonblocking():
    inputs = {
        "source_tree_manifest": {"files": [
            {"path": "phase_01/pkg/__init__.py"},
            {"path": "phase_02/pkg/__init__.py"},
        ]},
        "file_hash_manifest": {"entries": [
            {"path": "phase_01/pkg/__init__.py", "sha256": "0" * 64},
            {"path": "phase_02/pkg/__init__.py", "sha256": "0" * 64},
        ]},
    }
    report = M01.run_module(inputs)["outputs"]["duplicate_file_report"]
    assert report["duplicate_groups"][0]["classification"] == "PACKAGE_MARKER"
    assert report["status"] == "PASS"


def coverage_inputs(with_source=True):
    inputs = {
        "validated_module_registry": {"modules": [{"module_id": "P0.S5.M01"}, {"module_id": "P0.S5.M02"}]},
        "modules_yaml_all_phases": {"entries": [
            {"module_id": "P0.S5.M01", "path": "modules/P0_S5_M01_x.yaml"},
            {"module_id": "P0.S5.M02", "path": "modules/P0_S5_M02_x.yaml"},
        ]},
        "tests_all_phases": {"entries": [
            {"module_id": "P0.S5.M01", "path": "tests/P0_S5_M01_x.py"},
            {"module_id": "P0.S5.M02", "path": "tests/P0_S5_M02_x.py"},
        ]},
    }
    if with_source:
        inputs["source_tree_manifest"] = {"files": [
            {"path": "src/P0_S5_M01_duplicate_file_detector.py", "content": ""},
        ]}
    return inputs


def test_m05_optionally_detects_missing_python_implementation():
    report = M05.run_module(coverage_inputs())["outputs"]["module_contract_coverage_report"]
    assert {item["kind"] for item in report["findings"]} == {"MISSING_IMPLEMENTATION"}
    assert report["findings"][0]["module_id"] == "P0.S5.M02"


def _base_report(name, status="PASS", **extra):
    value = {
        "artifact_id": name,
        "lineage_id": "sha256:" + "a" * 64,
        "status": status,
        "release_blocking": status == "FAIL",
        "promotion_blocked": True,
    }
    value.update(extra)
    return value


def test_m06_attributes_local_problem_only_to_affected_phase():
    reports = {
        "duplicate_file_report": _base_report("dup"),
        "monolith_report": _base_report("mono", "FAIL", findings=[{
            "path": "phase_04_extracted/pkg/a.py", "symbol": "x", "kind": "FUNCTION_TOO_LONG", "line_count": 70, "limit": 60,
        }]),
        "forbidden_import_report": _base_report("imp"),
        "hidden_global_state_report": _base_report("state"),
        "module_contract_coverage_report": _base_report("cov"),
    }
    report = M06.run_module(reports)["outputs"]["code_quality_report"]
    statuses = {item["phase_id"]: item["status"] for item in report["phases"]}
    assert statuses["P4"] == "FAIL"
    assert all(statuses[f"P{i}"] == "PASS" for i in range(10) if i != 4)

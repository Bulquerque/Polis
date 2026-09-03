from copy import deepcopy
from importlib import import_module
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def mod(number, name):
    return import_module(f"quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S5_M{number:02d}_{name}")


M02 = mod(2, "monolith_code_detector")
M03 = mod(3, "forbidden_import_detector")
M04 = mod(4, "hidden_global_state_detector")
M05 = mod(5, "module_contract_coverage_checker")
M06 = mod(6, "code_style_quality_reporter")


def tree(content="def ok():\n    return 1\n"):
    return {"files": [{"path": "pkg/a.py", "content": content}]}


def test_m02_detects_file_and_function_monoliths_and_passes_clean_source():
    policy = {"max_file_lines": 4, "max_function_lines": 2}
    clean = M02.run_module({"source_tree_manifest": tree(), "code_quality_policy_yaml": policy})["outputs"]["monolith_report"]
    assert clean["status"] == "PASS"
    bad = M02.run_module({"source_tree_manifest": tree("def big():\n    x=1\n    y=2\n    return x+y\n# tail\n"), "code_quality_policy_yaml": policy})["outputs"]["monolith_report"]
    assert bad["status"] == "FAIL" and {x["kind"] for x in bad["findings"]} == {"FILE_TOO_LONG", "FUNCTION_TOO_LONG"}


def test_m03_uses_ast_and_policy_not_comments():
    policy = {"forbidden_imports": ["phase_09.*", "dashboard.business_logic"]}
    clean = M03.run_module({"source_tree_manifest": tree("# import phase_09.bad\nimport json\n"), "forbidden_import_policy_yaml": policy})["outputs"]["forbidden_import_report"]
    assert clean["status"] == "PASS"
    bad = M03.run_module({"source_tree_manifest": tree("from phase_09.learning import leak\n"), "forbidden_import_policy_yaml": policy})["outputs"]["forbidden_import_report"]
    assert bad["violations"][0]["import_name"] == "phase_09.learning" and bad["release_blocking"]


def test_m04_detects_mutable_global_secret_and_absolute_path():
    policy = {"allowed_module_globals": ["SAFE_CACHE"]}
    clean = M04.run_module({"source_tree_manifest": tree("SAFE_CACHE = {}\nVALUE = 1\n"), "code_quality_policy_yaml": policy})["outputs"]["hidden_global_state_report"]
    assert clean["status"] == "PASS"
    bad = M04.run_module({"source_tree_manifest": tree("CACHE = {}\nAPI_KEY = 'abc'\nCONFIG = '/etc/private'\n"), "code_quality_policy_yaml": policy})["outputs"]["hidden_global_state_report"]
    assert bad["violation_count"] == 3 and bad["release_blocking"]


def coverage_inputs():
    registry = {"modules": [{"module_id": "P0.S5.M01"}, {"module_id": "P0.S5.M02"}]}
    contracts = {"entries": [{"module_id": x, "path": f"modules/{x}.yaml"} for x in ("P0.S5.M01", "P0.S5.M02")]}
    tests = {"entries": [{"module_id": x, "path": f"tests/{x}.py"} for x in ("P0.S5.M01", "P0.S5.M02")]}
    return {"validated_module_registry": registry, "modules_yaml_all_phases": contracts, "tests_all_phases": tests}


def test_m05_exact_coverage_passes_and_missing_test_blocks():
    report = M05.run_module(coverage_inputs())["outputs"]["module_contract_coverage_report"]
    assert report["status"] == "PASS" and report["uncovered_module_count"] == 0
    data = coverage_inputs(); data["tests_all_phases"]["entries"].pop()
    report = M05.run_module(data)["outputs"]["module_contract_coverage_report"]
    assert report["findings"] == [{"module_id": "P0.S5.M02", "kind": "MISSING_EXPECTED_TEST", "missing_artifact": "test"}]


def reports(status="PASS"):
    result = {}
    for name in ("duplicate_file_report", "monolith_report", "forbidden_import_report", "hidden_global_state_report", "module_contract_coverage_report"):
        result[name] = {"artifact_id": name, "lineage_id": "sha256:" + "a" * 64, "status": status, "release_blocking": status == "FAIL", "promotion_blocked": True}
    return result


def test_m06_integrates_all_five_reports_and_propagates_block():
    report = M06.run_module(reports())["outputs"]["code_quality_report"]
    assert report["quality_status"] == "PASS" and report["source_report_count"] == 5
    data = reports(); data["forbidden_import_report"]["status"] = "FAIL"; data["forbidden_import_report"]["release_blocking"] = True
    report = M06.run_module(data)["outputs"]["code_quality_report"]
    assert report["quality_status"] == "FAIL" and report["blocking_reports"] == ["forbidden_import_report"]


@pytest.mark.parametrize("module,inputs", [
    (M02, {"source_tree_manifest": {"source": "x"}, "code_quality_policy_yaml": {"max_file_lines": 1, "max_function_lines": 1}}),
    (M03, {"source_tree_manifest": tree(), "forbidden_import_policy_yaml": {"source": "x"}}),
    (M04, {"source_tree_manifest": tree(), "code_quality_policy_yaml": {"source": "x"}}),
    (M05, {"validated_module_registry": {"source": "x"}, "modules_yaml_all_phases": [], "tests_all_phases": []}),
    (M06, {name: {"source": name} for name in reports()}),
])
def test_modules_reject_symbolic_placeholders(module, inputs):
    with pytest.raises(ValueError):
        module.run_module(inputs)


def test_recursive_forbidden_fields_rejected_and_schemas_are_exact():
    data = {"source_tree_manifest": tree(), "code_quality_policy_yaml": {"max_file_lines": 10, "max_function_lines": 10, "nested": {"target": 1}}}
    with pytest.raises(ValueError, match="forbidden input fields"):
        M02.run_module(data)
    cases = [(M02, {"source_tree_manifest": tree(), "code_quality_policy_yaml": {"max_file_lines": 10, "max_function_lines": 10}}, "monolith_report"), (M03, {"source_tree_manifest": tree(), "forbidden_import_policy_yaml": {"forbidden_imports": ["bad.*"]}}, "forbidden_import_report"), (M04, {"source_tree_manifest": tree(), "code_quality_policy_yaml": {"allowed_module_globals": []}}, "hidden_global_state_report"), (M05, coverage_inputs(), "module_contract_coverage_report"), (M06, reports(), "code_quality_report")]
    for module, inputs, output in cases:
        artifact = module.run_module(inputs)["outputs"][output]
        schema = yaml.safe_load((ROOT / "schemas" / f"{output}.schema.yaml").read_text(encoding="utf-8"))
        assert set(artifact) == set(schema["properties"]) == set(schema["required_fields"])

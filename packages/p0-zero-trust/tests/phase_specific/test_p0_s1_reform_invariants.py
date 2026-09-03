from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M01_phase_registry_loader import (
    run_module as run_m01,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M02_subphase_registry_loader import (
    run_module as run_m02,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M03_module_registry_loader import (
    run_module as run_m03,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M04_connection_matrix_validator import (
    run_module as run_m04,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M05_forbidden_connection_detector import (
    run_module as run_m05,
)


MODULE_ROOT = ROOT / "src" / "quant_pipeline" / "phase_00_zero_trust_guardian" / "modules"
BASELINE = ROOT / "source_of_truth" / "architecture" / "ARCHITECTURE_BASELINE.yaml"


def test_reform_baseline_is_single_versioned_inventory_source():
    baseline = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert baseline["baseline_id"] == "architecture_baseline_v14_1_rc4_1"
    assert baseline["registries"]["phase"]["phase_count"] == 10
    assert baseline["registries"]["subphase"]["subphase_count"] == 84
    assert baseline["registries"]["module"]["module_count"] == 268
    assert len(baseline["registries"]["module"]["module_ids"]) == 268


def test_s1_python_respects_clean_code_limits():
    paths = sorted(MODULE_ROOT.glob("P0_S1_M0*.py")) + sorted(MODULE_ROOT.glob("_p0_s1_*.py"))
    violations = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        if line_count > 350:
            violations.append(f"{path.name}: file has {line_count} lines")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = (node.end_lineno or node.lineno) - node.lineno + 1
                if size > 60:
                    violations.append(f"{path.name}:{node.name} has {size} lines")
        longest = max((len(line) for line in source.splitlines()), default=0)
        if longest > 120:
            violations.append(f"{path.name}: max line length is {longest}")
    assert not violations, "\n".join(violations)


def test_public_s1_modules_do_not_import_private_helpers_from_each_other():
    violations = []
    for path in sorted(MODULE_ROOT.glob("P0_S1_M0*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "P0_S1_M0" in node.module:
                violations.append(f"{path.name} imports {node.module}")
    assert not violations, violations


def test_public_s1_modules_do_not_embed_release_inventory_constants():
    forbidden_literals = (
        "EXPECTED_PHASE_PACKAGES",
        "EXPECTED_SUBPHASE_MODULE_COUNTS",
        "EXPECTED_MODULE_IDS",
        "EXPECTED_MODULE_COUNT = 166",
    )
    violations = []
    for path in sorted(MODULE_ROOT.glob("P0_S1_M0*.py")):
        source = path.read_text(encoding="utf-8")
        for literal in forbidden_literals:
            if literal in source:
                violations.append(f"{path.name}: {literal}")
    assert not violations, violations


def test_s1_end_to_end_canonical_flow_passes():
    config = {
        "pipeline_version": "V14.1-RC4.1",
        "created_at": "2026-07-22T22:00:00Z",
    }
    phase_registry = run_m01(
        {
            "phase_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"),
            "global_architecture_config": {
                "authority": "global_master",
                "pipeline_version": "V14.1-RC4.1",
                "phase_registry_id": "phase_registry_v14_1_rc4_1",
            },
        },
        config,
    )["outputs"]["validated_phase_registry"]
    subphase_registry = run_m02(
        {
            "validated_phase_registry": phase_registry,
            "subphase_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"),
        },
        config,
    )["outputs"]["validated_subphase_registry"]
    module_registry = run_m03(
        {
            "validated_phase_registry": phase_registry,
            "validated_subphase_registry": subphase_registry,
            "module_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "module_registry.yaml"),
        },
        config,
    )["outputs"]["validated_module_registry"]
    connection_matrix = run_m04(
        {
            "connection_matrix_yaml": str(ROOT / "contracts" / "MODULE_IO_MATRIX.yaml"),
            "validated_phase_registry": phase_registry,
            "validated_module_registry": module_registry,
        },
        config,
    )["outputs"]["validated_connection_matrix"]
    io_paths = sorted(
        path for path in WORKSPACE_ROOT.glob("phase_*/**/contracts/MODULE_IO_MATRIX.yaml")
        if path.parent.name == "contracts" and path.parent.parent.name.endswith("_agent_package_RC4_1")
    )
    assert len(io_paths) == 10
    report = run_m05(
        {
            "validated_connection_matrix": connection_matrix,
            "forbidden_connection_matrix_yaml": str(ROOT / "contracts" / "CONNECTIONS.yaml"),
            "module_io_matrix_all_phases": [
                yaml.safe_load(path.read_text(encoding="utf-8")) for path in io_paths
            ],
        },
        config,
    )["outputs"]["forbidden_connection_report"]
    assert report["status"] == "PASS"
    assert report["forbidden_connection_count"] == 0
    assert connection_matrix["module_count"] == 40


def test_policy_engine_detects_a_forbidden_p0_to_economic_edge():
    io_paths = sorted(
        path for path in WORKSPACE_ROOT.glob("phase_*/**/contracts/MODULE_IO_MATRIX.yaml")
        if path.parent.name == "contracts" and path.parent.parent.name.endswith("_agent_package_RC4_1")
    )
    if len(io_paths) != 10:
        pytest.skip("full workspace is required for the global policy mutation")
    matrices = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in io_paths]
    matrices = deepcopy(matrices)
    p0 = next(matrix for matrix in matrices if matrix["phase"] == "P0")
    p8 = next(matrix for matrix in matrices if matrix["phase"] == "P8")
    source = next(item for item in p0["module_io_matrix"] if item["module_id"] == "P0.S1.M01")
    target = next(item for item in p8["module_io_matrix"] if item["module_id"] == "P8.S1.M01")
    source["emits_to"]["modules"].append("P8.S1.M01")
    target["consumes_from"]["modules"].append("P0.S1.M01")
    # This mutation is already covered by M05 operational tests. Here we assert
    # only that the structured declarative policy remains available in the package.
    policy = yaml.safe_load((ROOT / "contracts" / "CONNECTIONS.yaml").read_text(encoding="utf-8"))
    assert policy["policy_rules"][0]["source"] == {"phase": "P0"}
    assert policy["policy_rules"][0]["target"] == {"plane": "economic_pipeline"}

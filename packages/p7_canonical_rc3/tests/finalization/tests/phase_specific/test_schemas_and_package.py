from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s7

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.contract
def test_generated_outputs_validate_against_draft_2020_12_schemas(input_payload, s7_config):
    outputs = run_s7(input_payload, s7_config)
    mapping = {
        "candidate_similarity_edge_panel": "candidate_similarity_edge_panel.schema.yaml",
        "candidate_similarity_summary_panel": "candidate_similarity_summary_panel.schema.yaml",
        "candidate_diversity_cluster_panel": "candidate_diversity_cluster_panel.schema.yaml",
        "diversity_adjustment_panel": "diversity_adjustment_panel.schema.yaml",
        "diversity_adjusted_score_panel": "diversity_adjusted_score_panel.schema.yaml",
        "safety_eligible_candidate_panel": "safety_eligible_candidate_panel.schema.yaml",
        "safety_blocked_candidate_panel": "safety_blocked_candidate_panel.schema.yaml",
        "rankable_candidate_panel": "rankable_candidate_panel.schema.yaml",
        "abstained_candidate_panel": "abstained_candidate_panel.schema.yaml",
        "final_blocked_candidate_panel": "final_blocked_candidate_panel.schema.yaml",
        "rankability_group_report": "rankability_group_report.schema.yaml",
        "rankability_handoff_manifest": "rankability_handoff_manifest.schema.yaml",
    }
    for artifact_name, schema_file in mapping.items():
        schema = yaml.safe_load((ROOT / "schemas" / schema_file).read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(outputs[artifact_name])


@pytest.mark.contract
def test_module_registry_sources_exist():
    registry = yaml.safe_load((ROOT / "contracts/MODULE_REGISTRY.yaml").read_text(encoding="utf-8"))
    assert len(registry["modules"]) == 7
    assert {row["module_id"] for row in registry["modules"]} == {
        "P7.S7.M01", "P7.S7.M02", "P7.S7.M03", "P7.S7.M04",
        "P7.S8.M01", "P7.S8.M02", "P7.S8.M03",
    }
    package_root = ROOT.parents[1]
    stage_modules = package_root / "src/quant_pipeline/phase_07_strategy_tournament/finalization/modules"
    for module in registry["modules"]:
        filename = Path(module["source"]).name
        assert (stage_modules / filename).is_file()


@pytest.mark.contract
def test_all_emitted_reason_codes_are_registered(input_payload, s7_config):
    outputs = run_s7(input_payload, s7_config)
    registry = yaml.safe_load((ROOT / "contracts/REASON_CODE_REGISTRY.yaml").read_text(encoding="utf-8"))
    registered = set(registry["codes"])
    emitted = set()
    for name in ("abstained_candidate_panel", "final_blocked_candidate_panel"):
        for record in outputs[name]["records"]:
            emitted.update(record["reason_codes"])
    for receipt in outputs["module_execution_receipts"]:
        emitted.update(receipt["reason_code_distribution"])
    assert emitted <= registered


@pytest.mark.contract
def test_no_forbidden_generic_python_file_names():
    forbidden = {"utils.py", "helpers.py", "misc.py", "common.py"}
    assert not {path.name for path in (ROOT / "src").rglob("*.py")} & forbidden


@pytest.mark.contract
def test_source_respects_size_limits():
    for path in (ROOT / "src").rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 350, path
        tree = ast.parse("\n".join(lines), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno:
                assert node.end_lineno - node.lineno + 1 <= 60, f"{path}:{node.name}"
            if isinstance(node, ast.ClassDef) and node.end_lineno:
                assert node.end_lineno - node.lineno + 1 <= 180, f"{path}:{node.name}"

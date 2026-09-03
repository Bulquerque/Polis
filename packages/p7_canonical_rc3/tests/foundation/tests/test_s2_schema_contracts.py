from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s2

ROOT = Path(__file__).resolve().parents[1]


def test_all_s2_schemas_are_valid_draft_2020_12():
    paths = sorted(ROOT.joinpath("schemas").glob("*.schema.json"))
    assert paths
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_policy_documents_validate_against_generated_schemas():
    pairs = {
        "eligibility_policy_registry.yaml": "eligibility_policy_registry.schema.json",
        "comparison_group_policy.yaml": "comparison_group_policy_registry.schema.json",
        "metric_semantics_registry.yaml": "metric_semantics_registry.schema.json",
        "objective_family_registry.yaml": "objective_family_registry.schema.json",
    }
    for config_name, schema_name in pairs.items():
        instance = yaml.safe_load(ROOT.joinpath("configs", config_name).read_text(encoding="utf-8"))
        schema = json.loads(ROOT.joinpath("schemas", schema_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(instance)


def test_s2_output_records_validate_against_record_schemas(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    result = run_subphase_s2(
        temporally_safe_candidate_bundle=bundle,
        ranking_feedback_context=feedback,
        eligibility_policy_registry=registries["eligibility"],
        comparison_group_policy=registries["comparison"],
        metric_semantics_registry=registries["metrics"],
        objective_family_registry=registries["objectives"],
        module_config=module_config,
    )
    bindings = yaml.safe_load(ROOT.joinpath("contracts", "SCHEMA_BINDINGS.yaml").read_text(encoding="utf-8"))["bindings"]
    for artifact_name, binding in bindings.items():
        if artifact_name == "temporally_safe_candidate_bundle":
            artifact = bundle
        else:
            artifact = result["outputs"].get(artifact_name)
        if artifact is None:
            continue
        schema = json.loads(ROOT.joinpath("schemas", binding["record"]).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for record in artifact["records"]:
            validator.validate(record)

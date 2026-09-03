from copy import deepcopy
from pathlib import Path
import hashlib
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S2_M04_forbidden_field_scanner import (
    ContractValidationError,
    _validate_artifact,
    run_module,
)


LINEAGE = "sha256:" + "a" * 64
POLICY = {
    "forbidden_fields": [
        "future_return",
        "target",
        "signal_direction",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "realized_pnl",
        "trade_decision",
        "execution_price",
        "position_size",
    ]
}


def _schema_entry(
    schema_id: str,
    phase_id: str,
    document: dict,
    *,
    mode: str = "inference",
) -> dict:
    return {
        "schema_id": schema_id,
        "artifact_name": schema_id.rsplit(".v", 1)[0],
        "schema_version": "v14.1-rc4.1",
        "path": f"inline:{schema_id}",
        "phase_id": phase_id,
        "mode": mode,
        "document": document,
    }


def valid_inputs() -> dict:
    schema_registry = {
        "artifact_id": "schema-registry-0123456789ab",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": LINEAGE,
        "schemas": [
            _schema_entry(
                "online_feature_panel.v1",
                "P6",
                {
                    "type": "object",
                    "properties": {"feature_value": {"type": "number"}},
                    "forbidden_fields": ["target", "rank_score"],
                },
            ),
            _schema_entry(
                "ranking_panel.v1",
                "P7",
                {
                    "type": "object",
                    "properties": {
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required_fields": ["rank_score"],
                            },
                        }
                    },
                },
            ),
            _schema_entry(
                "offline_training_labels.v1",
                "P5",
                {
                    "metadata": {"mode": "training"},
                    "columns": [[{"field_name": "target"}]],
                },
                mode="training",
            ),
        ],
        "mirrors": [],
        "promotion_blocked": True,
    }
    artifact_registry = {
        "artifacts": [
            {
                "artifact_id": "P7-ranking-runtime-panel",
                "phase_id": "P7",
                "path": "inline:P7-ranking-runtime-panel",
                "payload": {
                    "batches": [
                        {"fields": [{"name": "rank_score"}], "records": [{"score": 0.7}]}
                    ]
                },
            },
            {
                "artifact_id": "P4-clean-feature-panel",
                "phase_id": "P4",
                "path": "inline:P4-clean-feature-panel",
                "payload": {"rows": [{"feature_value": 1.0}]},
            },
        ]
    }
    return {
        "schema_registry": schema_registry,
        "artifact_registry": artifact_registry,
        "forbidden_fields_yaml": POLICY,
    }


def _real_registry_inputs() -> dict:
    authority = (
        WORKSPACE_ROOT
        / "global_contracts_parallel_agents"
        / "v14_1_global_contracts_parallel_agents_RC4_1"
        / "schemas"
        / "underlying_feature_matrix_selected.schema.yaml"
    )
    mirror = next(
        (WORKSPACE_ROOT / "phase_04_extracted").rglob(
            "underlying_feature_matrix_selected.schema.yaml"
        )
    )
    document = yaml.safe_load(authority.read_text(encoding="utf-8"))
    authority_relative = authority.relative_to(WORKSPACE_ROOT).as_posix()
    module_contract = ROOT / "modules" / "P0_S2_M04_forbidden_field_scanner.yaml"
    return {
        "schema_registry": {
            "artifact_id": "schema-registry-fedcba987654",
            "pipeline_version": "V14.1-RC4.1",
            "lineage_id": LINEAGE,
            "schemas": [
                {
                    "schema_id": document.get(
                        "schema_id", "underlying_feature_matrix_selected.v1"
                    ),
                    "artifact_name": document.get(
                        "artifact_name", "underlying_feature_matrix_selected"
                    ),
                    "schema_version": document.get(
                        "schema_version", "v14.1-rc4.1"
                    ),
                    "path": authority_relative,
                    "sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
                }
            ],
            "mirrors": [
                {
                    "path": mirror.relative_to(WORKSPACE_ROOT).as_posix(),
                    "authority_path": authority_relative,
                }
            ],
            "promotion_blocked": True,
        },
        "artifact_registry": {
            "artifacts": [
                {
                    "artifact_id": "P0-S2-M04-module-contract",
                    "artifact_type": "contract",
                    "format": "yaml",
                    "path": module_contract.relative_to(WORKSPACE_ROOT).as_posix(),
                }
            ]
        },
        "forbidden_fields_yaml": str(ROOT / "contracts" / "FORBIDDEN_FIELDS.yaml"),
    }


def test_scans_nested_inline_maps_and_lists_with_allowed_exceptions():
    artifact = run_module(
        valid_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["forbidden_field_report"]

    assert artifact["status"] == "PASS"
    assert artifact["release_blocking"] is False
    assert artifact["violation_count"] == 0
    assert artifact["field_occurrence_count"] == 3
    assert artifact["allowed_exception_count"] == 3
    assert artifact["scanned_schema_count"] == 3
    assert artifact["scanned_artifact_count"] == 2
    assert artifact["target_not_in_inference"] is True
    assert artifact["rank_score_not_before_phase7"] is True
    assert artifact["recursive_scan_complete"] is True


def test_scans_real_schema_and_artifact_paths_without_treating_policy_as_payload():
    artifact = run_module(
        _real_registry_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["forbidden_field_report"]

    assert artifact["status"] == "PASS"
    assert artifact["violation_count"] == 0
    assert artifact["scanned_schema_count"] == 1
    assert artifact["scanned_artifact_count"] == 1
    assert artifact["field_occurrence_count"] == 0


def test_target_in_inference_and_rank_score_before_p7_are_blocking():
    inputs = valid_inputs()
    inputs["schema_registry"]["schemas"][0]["document"] = {
        "type": "object",
        "properties": {
            "nested": {
                "type": "array",
                "items": {
                    "type": "object",
                    "fields": ["target", {"name": "rank_score"}],
                },
            }
        },
    }
    artifact = run_module(inputs, {"created_at": "2026-07-19T00:00:00Z"})[
        "outputs"
    ]["forbidden_field_report"]

    assert artifact["status"] == "FAIL"
    assert artifact["severity"] == "CRITICAL"
    assert artifact["release_blocking"] is True
    assert artifact["violation_count"] == 2
    assert artifact["target_inference_violation_count"] == 1
    assert artifact["rank_score_pre_p7_violation_count"] == 1
    assert artifact["target_not_in_inference"] is False
    assert artifact["rank_score_not_before_phase7"] is False
    assert {item["code"] for item in artifact["violations"]} == {
        "TARGET_IN_INFERENCE",
        "RANK_SCORE_BEFORE_P7",
    }
    assert all(item["phase_id"] == "P6" for item in artifact["violations"])
    assert all(item["source_kind"] == "schema" for item in artifact["violations"])
    assert all(item["release_blocking"] is True for item in artifact["violations"])


def test_rank_score_is_allowed_in_p7_but_rejected_in_p6_artifact():
    inputs = valid_inputs()
    inputs["artifact_registry"]["artifacts"][1] = {
        "artifact_id": "P6-candidate-panel",
        "phase_id": "P6",
        "path": "inline:P6-candidate-panel",
        "payload": {"rows": [{"metrics": {"rank_score": 0.5}}]},
    }
    artifact = run_module(inputs, {})["outputs"]["forbidden_field_report"]

    assert artifact["rank_score_pre_p7_violation_count"] == 1
    assert artifact["allowed_exception_count"] == 3
    violation = artifact["violations"][0]
    assert violation["field_name"] == "rank_score"
    assert violation["phase_id"] == "P6"
    assert violation["source_kind"] == "artifact"


def test_target_is_allowed_for_training_but_defaults_to_blocking_inference():
    inputs = valid_inputs()
    training = inputs["schema_registry"]["schemas"][2]
    training["mode"] = "inference"
    training["document"]["metadata"]["mode"] = "inference"
    artifact = run_module(inputs, {})["outputs"]["forbidden_field_report"]

    assert artifact["target_inference_violation_count"] == 1
    assert artifact["violations"][0]["code"] == "TARGET_IN_INFERENCE"
    assert artifact["violations"][0]["phase_id"] == "P5"


def test_other_forbidden_field_is_structured_and_release_blocking():
    inputs = valid_inputs()
    inputs["artifact_registry"]["artifacts"][1]["payload"] = {
        "groups": [[{"metrics": {"future_return": 0.4}}]]
    }
    artifact = run_module(inputs, {})["outputs"]["forbidden_field_report"]

    assert artifact["other_forbidden_violation_count"] == 1
    assert artifact["violations"][0]["code"] == "FORBIDDEN_FIELD_PRESENT"
    assert artifact["violations"][0]["location"].endswith(".future_return")
    assert artifact["release_blocking"] is True


@pytest.mark.parametrize(
    "input_name",
    ["schema_registry", "artifact_registry", "forbidden_fields_yaml"],
)
def test_rejects_symbolic_placeholders(input_name):
    inputs = valid_inputs()
    inputs[input_name] = {"source": input_name}
    with pytest.raises(ContractValidationError, match="placeholder|materialized mapping"):
        run_module(inputs, {})


def test_rejects_nested_symbolic_placeholder():
    inputs = valid_inputs()
    inputs["artifact_registry"]["artifacts"][0]["payload"] = {
        "nested": {"source": "future-artifact"}
    }
    with pytest.raises(ContractValidationError, match="symbolic placeholders"):
        run_module(inputs, {})


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda inputs: inputs["schema_registry"]["schemas"][0].update(schema_id="bad"), "invalid schema_id"),
        (lambda inputs: inputs["schema_registry"]["schemas"][0].update(phase_id="P10"), "invalid phase ID"),
        (lambda inputs: inputs["artifact_registry"]["artifacts"][0].update(phase_id="PX"), "invalid phase ID"),
        (lambda inputs: inputs["schema_registry"].update(lineage_id="symbolic"), "lineage_id is invalid"),
    ],
)
def test_rejects_malformed_schema_phase_and_lineage_ids(mutation, error):
    inputs = valid_inputs()
    mutation(inputs)
    with pytest.raises(ContractValidationError, match=error):
        run_module(inputs, {})


def test_rejects_duplicate_schema_and_artifact_ids():
    inputs = valid_inputs()
    inputs["schema_registry"]["schemas"].append(
        deepcopy(inputs["schema_registry"]["schemas"][0])
    )
    with pytest.raises(ContractValidationError, match="duplicate schema_id"):
        run_module(inputs, {})

    inputs = valid_inputs()
    inputs["artifact_registry"]["artifacts"].append(
        deepcopy(inputs["artifact_registry"]["artifacts"][0])
    )
    with pytest.raises(ContractValidationError, match="duplicate artifact_id"):
        run_module(inputs, {})


def test_rejects_policy_without_required_controls_and_duplicate_fields():
    inputs = valid_inputs()
    inputs["forbidden_fields_yaml"] = {"forbidden_fields": ["future_return"]}
    with pytest.raises(ContractValidationError, match="target and rank_score"):
        run_module(inputs, {})

    inputs = valid_inputs()
    inputs["forbidden_fields_yaml"] = {
        "forbidden_fields": ["target", "rank_score", "target"]
    }
    with pytest.raises(ContractValidationError, match="duplicate fields"):
        run_module(inputs, {})


def test_lineage_is_deterministic_and_binds_scanned_content():
    inputs = valid_inputs()
    first = run_module(inputs, {"created_at": "2026-07-19T00:00:00Z"})["outputs"][
        "forbidden_field_report"
    ]
    second = run_module(inputs, {"created_at": "2026-07-20T00:00:00Z"})["outputs"][
        "forbidden_field_report"
    ]
    assert first["lineage_id"] == second["lineage_id"]

    changed = deepcopy(inputs)
    changed["artifact_registry"]["artifacts"][1]["payload"]["rows"][0][
        "feature_value"
    ] = 2.0
    third = run_module(changed, {"created_at": "2026-07-19T00:00:00Z"})["outputs"][
        "forbidden_field_report"
    ]
    assert third["lineage_id"] != first["lineage_id"]


def test_policy_named_subtree_cannot_hide_forbidden_payload():
    inputs = valid_inputs()
    inputs["artifact_registry"]["artifacts"][0]["payload"]["forbidden_fields"] = {
        "nested": {"target": "leak", "rank_score": 1}
    }
    report = run_module(inputs, {})["outputs"]["forbidden_field_report"]
    assert report["release_blocking"] is True
    assert "target" in {item["field_name"] for item in report["violations"]}


def test_output_conforms_to_schema_and_rejects_invalid_output():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "forbidden_field_report.schema.yaml").read_text(
            encoding="utf-8"
        )
    )
    artifact = run_module(
        valid_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["forbidden_field_report"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(artifact) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    invalid = deepcopy(artifact)
    invalid["unexpected"] = True
    with pytest.raises(ContractValidationError, match="output schema extra fields"):
        _validate_artifact(invalid)


def test_rejects_missing_inputs_non_mapping_config_and_bad_runtime_version():
    with pytest.raises(ContractValidationError, match="missing required inputs"):
        run_module({}, {})
    with pytest.raises(ContractValidationError, match="config must be a dict"):
        run_module(valid_inputs(), [])
    with pytest.raises(ContractValidationError, match="pipeline version is incompatible"):
        run_module(valid_inputs(), {"pipeline_version": "V15"})


def test_phase_specific_policy_blocks_p9_direct_code_patch():
    inputs = valid_inputs()
    inputs["artifact_registry"]["artifacts"][1] = {
        "artifact_id": "P9-audit-learning-output",
        "phase_id": "P9",
        "path": "inline:P9-audit-learning-output",
        "payload": {"recommendation": {"direct_code_patch": "unsafe"}},
    }
    report = run_module(inputs, {})["outputs"]["forbidden_field_report"]
    violation = next(
        item for item in report["violations"]
        if item["field_name"] == "direct_code_patch"
    )
    assert violation["phase_id"] == "P9"
    assert violation["code"] == "FORBIDDEN_FIELD_PRESENT"
    assert report["release_blocking"] is True


def test_explicit_conflicting_execution_context_fails_closed():
    inputs = valid_inputs()
    entry = inputs["schema_registry"]["schemas"][0]
    entry["mode"] = "inference"
    entry["document"]["metadata"] = {"mode": "training"}
    with pytest.raises(ContractValidationError, match="conflicting execution context"):
        run_module(inputs, {})
